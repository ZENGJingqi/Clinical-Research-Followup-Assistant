from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from followup.models import FollowUp, Patient, ProjectEnrollment, ResearchProject, Treatment


class Command(BaseCommand):
    help = "写入随访系统示例测试数据"

    def _planned_count(self, total_weeks, interval_days):
        if interval_days <= 0 or total_weeks <= 0:
            return 0
        return max(1, (total_weeks * 7) // interval_days)

    def _build_followups(self, start_date, interval_days, total_weeks, status, next_in_days=None):
        planned_count = self._planned_count(total_weeks, interval_days)
        if status == "new":
            return []

        if status in {"today", "soon", "overdue", "closed"}:
            count = min(2, max(planned_count, 1))
        elif status == "light":
            count = 1
        else:
            count = planned_count

        followups = []
        today = timezone.localdate()
        for visit_number in range(1, count + 1):
            followup_date = start_date + timedelta(days=interval_days * visit_number)
            planned_next = followup_date + timedelta(days=interval_days)
            if visit_number == count:
                if status == "today":
                    planned_next = today
                elif status == "soon":
                    planned_next = today + timedelta(days=next_in_days or 3)
                elif status == "overdue":
                    planned_next = today - timedelta(days=next_in_days or 3)
                elif status == "closed":
                    planned_next = today + timedelta(days=next_in_days or 5)
                elif status == "completed":
                    planned_next = None
                elif status == "light":
                    planned_next = today + timedelta(days=next_in_days or interval_days)

            followups.append(
                {
                    "visit_number": visit_number,
                    "followup_date": followup_date,
                    "planned_next_followup_date": planned_next,
                    "symptoms": f"第{visit_number}次随访：症状较前平稳。",
                    "medication_adherence": "良好" if visit_number % 2 else "一般",
                    "adverse_events": "" if visit_number % 3 else "轻度乏力",
                    "notes": "样例随访数据",
                }
            )
        return followups

    def _treatment_spec(
        self,
        *,
        treatment_name,
        group_name,
        western_disease,
        tcm_disease,
        chief_complaint,
        start_days_ago,
        total_weeks,
        interval_days,
        status,
        next_in_days=None,
        closed_days_ago=0,
    ):
        today = timezone.localdate()
        start_date = today - timedelta(days=start_days_ago)
        followups = self._build_followups(
            start_date=start_date,
            interval_days=interval_days,
            total_weeks=total_weeks,
            status=status,
            next_in_days=next_in_days,
        )
        closed = status == "closed"
        return {
            "treatment": {
                "group_name": group_name,
                "treatment_name": treatment_name,
                "start_date": start_date,
                "total_weeks": total_weeks,
                "followup_interval_days": interval_days,
                "followup_closed": closed,
                "followup_closed_at": today - timedelta(days=closed_days_ago) if closed else None,
                "chief_complaint": chief_complaint,
                "present_illness": f"近阶段主要围绕{chief_complaint}进行诊疗与随访。",
                "past_history": f"既往有{western_disease}相关病史。",
                "personal_history": "生活作息不够规律，样例数据。",
                "marital_history": "已婚或未婚信息仅用于演示。",
                "allergy_history": "否认明确药物过敏史。",
                "family_history": f"家族中有{western_disease}相关病史。",
                "tongue_diagnosis": "舌淡红，苔薄。",
                "pulse_diagnosis": "脉弦细。",
                "tcm_disease": tcm_disease,
                "western_disease": western_disease,
                "treatment_principle": "辨证施治，分阶段评估疗效。",
                "prescription": "基础方加减，具体处方为样例占位。",
                "notes": f"样例状态：{status}",
            },
            "followups": followups,
        }

    def handle(self, *args, **options):
        sample_ids = []
        patients = [
            {
                "patient": {
                    "patient_id": "TEST001",
                    "name": "张建国",
                    "gender": "male",
                    "birth_date": date(1968, 5, 12),
                    "ethnicity": "汉族",
                    "phone": "13800001001",
                    "address": "上海市浦东新区张江镇 18 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="高血压初诊调压",
                        group_name="治疗组",
                        western_disease="高血压病",
                        tcm_disease="眩晕",
                        chief_complaint="反复头晕头胀 3 月",
                        start_days_ago=98,
                        total_weeks=12,
                        interval_days=14,
                        status="completed",
                    ),
                    self._treatment_spec(
                        treatment_name="高血压巩固治疗",
                        group_name="治疗组",
                        western_disease="高血压病",
                        tcm_disease="眩晕恢复期",
                        chief_complaint="血压稳定后继续巩固",
                        start_days_ago=3,
                        total_weeks=8,
                        interval_days=14,
                        status="new",
                    ),
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST002",
                    "name": "李秀兰",
                    "gender": "female",
                    "birth_date": date(1979, 8, 3),
                    "ethnicity": "汉族",
                    "phone": "13800001002",
                    "address": "江苏省苏州市姑苏区养育巷 52 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="糖代谢调理",
                        group_name="对照组",
                        western_disease="2型糖尿病",
                        tcm_disease="消渴",
                        chief_complaint="口干多饮半年",
                        start_days_ago=42,
                        total_weeks=12,
                        interval_days=14,
                        status="today",
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST003",
                    "name": "王海峰",
                    "gender": "male",
                    "birth_date": date(1963, 1, 18),
                    "ethnicity": "回族",
                    "phone": "13800001003",
                    "address": "浙江省杭州市西湖区文三路 66 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="冠心病稳定期方案",
                        group_name="治疗组",
                        western_disease="冠心病",
                        tcm_disease="胸痹",
                        chief_complaint="胸闷胸痛反复发作",
                        start_days_ago=42,
                        total_weeks=12,
                        interval_days=14,
                        status="overdue",
                        next_in_days=4,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST004",
                    "name": "陈美玲",
                    "gender": "female",
                    "birth_date": date(1991, 11, 2),
                    "ethnicity": "汉族",
                    "phone": "13800001004",
                    "address": "安徽省合肥市蜀山区潜山路 120 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="偏头痛调理方案",
                        group_name="观察组",
                        western_disease="偏头痛",
                        tcm_disease="头痛",
                        chief_complaint="反复偏头痛 1 年",
                        start_days_ago=2,
                        total_weeks=8,
                        interval_days=14,
                        status="new",
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST005",
                    "name": "马依娜",
                    "gender": "female",
                    "birth_date": date(1988, 9, 14),
                    "ethnicity": "维吾尔族",
                    "phone": "13800001005",
                    "address": "新疆乌鲁木齐市天山区青年路 89 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="失眠调理方案",
                        group_name="观察组",
                        western_disease="慢性失眠",
                        tcm_disease="不寐",
                        chief_complaint="入睡困难伴多梦 4 月",
                        start_days_ago=35,
                        total_weeks=10,
                        interval_days=14,
                        status="soon",
                        next_in_days=3,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST006",
                    "name": "赵国梁",
                    "gender": "male",
                    "birth_date": date(1959, 2, 6),
                    "ethnicity": "满族",
                    "phone": "13800001006",
                    "address": "北京市朝阳区安立路 101 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="腰痛康复方案",
                        group_name="治疗组",
                        western_disease="腰椎间盘突出症",
                        tcm_disease="腰痛",
                        chief_complaint="腰部酸痛反复 2 年",
                        start_days_ago=28,
                        total_weeks=6,
                        interval_days=14,
                        status="light",
                        next_in_days=10,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST007",
                    "name": "孙晓梅",
                    "gender": "female",
                    "birth_date": date(1976, 6, 25),
                    "ethnicity": "汉族",
                    "phone": "13800001007",
                    "address": "湖北省武汉市武昌区中北路 77 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="甲状腺结节随访",
                        group_name="观察组",
                        western_disease="甲状腺结节",
                        tcm_disease="瘿瘤",
                        chief_complaint="颈前异物感间断出现",
                        start_days_ago=40,
                        total_weeks=12,
                        interval_days=14,
                        status="closed",
                        next_in_days=6,
                        closed_days_ago=1,
                    ),
                    self._treatment_spec(
                        treatment_name="甲状腺结节复诊",
                        group_name="观察组",
                        western_disease="甲状腺结节",
                        tcm_disease="瘿瘤",
                        chief_complaint="再次门诊复查",
                        start_days_ago=6,
                        total_weeks=8,
                        interval_days=14,
                        status="today",
                    ),
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST008",
                    "name": "周子涵",
                    "gender": "male",
                    "birth_date": date(1985, 10, 9),
                    "ethnicity": "汉族",
                    "phone": "13800001008",
                    "address": "湖南省长沙市开福区芙蓉北路 208 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="脂肪肝干预",
                        group_name="治疗组",
                        western_disease="脂肪肝",
                        tcm_disease="胁痛",
                        chief_complaint="右胁不适伴乏力",
                        start_days_ago=90,
                        total_weeks=12,
                        interval_days=14,
                        status="completed",
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST009",
                    "name": "吴振峰",
                    "gender": "male",
                    "birth_date": date(1972, 12, 19),
                    "ethnicity": "土家族",
                    "phone": "13800001009",
                    "address": "重庆市渝中区大坪正街 40 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="慢阻肺稳定期管理",
                        group_name="对照组",
                        western_disease="慢性阻塞性肺疾病",
                        tcm_disease="肺胀",
                        chief_complaint="活动后气短半年",
                        start_days_ago=50,
                        total_weeks=12,
                        interval_days=14,
                        status="overdue",
                        next_in_days=6,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST010",
                    "name": "郑丽娟",
                    "gender": "female",
                    "birth_date": date(1994, 3, 7),
                    "ethnicity": "汉族",
                    "phone": "13800001010",
                    "address": "四川省成都市高新区天府大道 399 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="月经不调调理",
                        group_name="观察组",
                        western_disease="月经不调",
                        tcm_disease="月经后期",
                        chief_complaint="经期紊乱伴小腹隐痛",
                        start_days_ago=35,
                        total_weeks=12,
                        interval_days=14,
                        status="soon",
                        next_in_days=5,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST011",
                    "name": "冯志强",
                    "gender": "male",
                    "birth_date": date(1965, 7, 30),
                    "ethnicity": "汉族",
                    "phone": "13800001011",
                    "address": "河北省石家庄市长安区建华大街 18 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="前列腺症状管理",
                        group_name="治疗组",
                        western_disease="前列腺增生",
                        tcm_disease="癃闭",
                        chief_complaint="夜尿频多",
                        start_days_ago=44,
                        total_weeks=12,
                        interval_days=14,
                        status="closed",
                        next_in_days=7,
                        closed_days_ago=2,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST012",
                    "name": "朱慧敏",
                    "gender": "female",
                    "birth_date": date(1982, 2, 15),
                    "ethnicity": "汉族",
                    "phone": "13800001012",
                    "address": "福建省厦门市思明区湖滨南路 88 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="乳腺结节随访",
                        group_name="对照组",
                        western_disease="乳腺结节",
                        tcm_disease="乳癖",
                        chief_complaint="乳房胀痛反复",
                        start_days_ago=42,
                        total_weeks=12,
                        interval_days=14,
                        status="today",
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST013",
                    "name": "胡文博",
                    "gender": "male",
                    "birth_date": date(1990, 1, 11),
                    "ethnicity": "汉族",
                    "phone": "13800001013",
                    "address": "广东省广州市天河区黄埔大道 302 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="胃炎调理",
                        group_name="治疗组",
                        western_disease="慢性胃炎",
                        tcm_disease="胃脘痛",
                        chief_complaint="餐后胃脘胀满",
                        start_days_ago=5,
                        total_weeks=8,
                        interval_days=14,
                        status="new",
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST014",
                    "name": "郭雪宁",
                    "gender": "female",
                    "birth_date": date(1987, 4, 16),
                    "ethnicity": "蒙古族",
                    "phone": "13800001014",
                    "address": "内蒙古呼和浩特市赛罕区大学东街 19 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="桥本甲状腺炎观察",
                        group_name="观察组",
                        western_disease="桥本甲状腺炎",
                        tcm_disease="瘿病",
                        chief_complaint="乏力伴咽部不适",
                        start_days_ago=28,
                        total_weeks=12,
                        interval_days=14,
                        status="light",
                        next_in_days=7,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST015",
                    "name": "何家林",
                    "gender": "male",
                    "birth_date": date(1958, 9, 21),
                    "ethnicity": "汉族",
                    "phone": "13800001015",
                    "address": "云南省昆明市五华区青年路 177 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="帕金森症状干预",
                        group_name="治疗组",
                        western_disease="帕金森病",
                        tcm_disease="颤证",
                        chief_complaint="肢体震颤伴动作迟缓",
                        start_days_ago=90,
                        total_weeks=12,
                        interval_days=14,
                        status="completed",
                    ),
                    self._treatment_spec(
                        treatment_name="帕金森加做巩固随访",
                        group_name="治疗组",
                        western_disease="帕金森病",
                        tcm_disease="颤证",
                        chief_complaint="症状稳定后复诊",
                        start_days_ago=32,
                        total_weeks=8,
                        interval_days=14,
                        status="closed",
                        next_in_days=10,
                        closed_days_ago=1,
                    ),
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST016",
                    "name": "高雅琴",
                    "gender": "female",
                    "birth_date": date(1974, 5, 5),
                    "ethnicity": "汉族",
                    "phone": "13800001016",
                    "address": "江西省南昌市东湖区八一大道 66 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="骨质疏松调理",
                        group_name="对照组",
                        western_disease="骨质疏松",
                        tcm_disease="骨痿",
                        chief_complaint="腰膝酸软",
                        start_days_ago=48,
                        total_weeks=12,
                        interval_days=14,
                        status="overdue",
                        next_in_days=5,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST017",
                    "name": "林卓然",
                    "gender": "male",
                    "birth_date": date(1992, 6, 2),
                    "ethnicity": "汉族",
                    "phone": "13800001017",
                    "address": "广西南宁市青秀区民族大道 260 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="肠易激综合征调理",
                        group_name="观察组",
                        western_disease="肠易激综合征",
                        tcm_disease="泄泻",
                        chief_complaint="腹痛腹泻反复",
                        start_days_ago=35,
                        total_weeks=10,
                        interval_days=14,
                        status="soon",
                        next_in_days=6,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST018",
                    "name": "罗春燕",
                    "gender": "female",
                    "birth_date": date(1989, 12, 8),
                    "ethnicity": "苗族",
                    "phone": "13800001018",
                    "address": "贵州省贵阳市南明区花果园 12 栋",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="焦虑状态干预",
                        group_name="治疗组",
                        western_disease="焦虑状态",
                        tcm_disease="郁证",
                        chief_complaint="心烦易醒",
                        start_days_ago=4,
                        total_weeks=8,
                        interval_days=14,
                        status="new",
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST019",
                    "name": "梁世杰",
                    "gender": "male",
                    "birth_date": date(1981, 7, 17),
                    "ethnicity": "汉族",
                    "phone": "13800001019",
                    "address": "天津市河西区友谊路 59 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="高尿酸血症管理",
                        group_name="对照组",
                        western_disease="高尿酸血症",
                        tcm_disease="痹证",
                        chief_complaint="足趾关节酸胀",
                        start_days_ago=30,
                        total_weeks=12,
                        interval_days=14,
                        status="light",
                        next_in_days=14,
                    )
                ],
            },
            {
                "patient": {
                    "patient_id": "TEST020",
                    "name": "谢雨桐",
                    "gender": "female",
                    "birth_date": date(1996, 1, 23),
                    "ethnicity": "汉族",
                    "phone": "13800001020",
                    "address": "陕西省西安市雁塔区科技路 88 号",
                },
                "treatments": [
                    self._treatment_spec(
                        treatment_name="多囊卵巢综合征调理",
                        group_name="治疗组",
                        western_disease="多囊卵巢综合征",
                        tcm_disease="月经失调",
                        chief_complaint="月经后期伴痤疮",
                        start_days_ago=42,
                        total_weeks=12,
                        interval_days=14,
                        status="today",
                    )
                ],
            },
        ]

        for item in patients:
            sample_ids.append(item["patient"]["patient_id"])
            patient, _ = Patient.objects.update_or_create(
                patient_id=item["patient"]["patient_id"],
                defaults=item["patient"],
            )

            keep_treatments = []
            for bundle in item["treatments"]:
                treatment_data = bundle["treatment"]
                treatment, _ = Treatment.objects.update_or_create(
                    patient=patient,
                    treatment_name=treatment_data["treatment_name"],
                    start_date=treatment_data["start_date"],
                    defaults=treatment_data,
                )
                keep_treatments.append(treatment.pk)

                keep_numbers = []
                for followup_data in bundle["followups"]:
                    keep_numbers.append(followup_data["visit_number"])
                    FollowUp.objects.update_or_create(
                        treatment=treatment,
                        visit_number=followup_data["visit_number"],
                        defaults=followup_data,
                    )
                treatment.followups.exclude(visit_number__in=keep_numbers).delete()

            patient.treatments.exclude(pk__in=keep_treatments).delete()

        project_specs = [
            {
                "name": "胃癌前病变真实世界",
                "principal_investigator": "刘老师",
                "status": ResearchProject.STATUS_ACTIVE,
                "target_enrollment": 120,
                "assignments": [
                    ("TEST001", "治疗组A", ProjectEnrollment.MARKER_IN, ""),
                    ("TEST002", "治疗组A", ProjectEnrollment.MARKER_COMPLETED, "已完成末次访视"),
                    ("TEST003", "对照组B", ProjectEnrollment.MARKER_WITHDRAWN, "患者主动退出"),
                    ("TEST004", "对照组B", ProjectEnrollment.MARKER_LOST, "连续失访"),
                    ("TEST005", "治疗组A", ProjectEnrollment.MARKER_IN, ""),
                    ("TEST006", "观察组C", ProjectEnrollment.MARKER_COMPLETED, "方案完成"),
                ],
            },
            {
                "name": "脾胃病门诊连续随访",
                "principal_investigator": "王老师",
                "status": ResearchProject.STATUS_ACTIVE,
                "target_enrollment": 80,
                "assignments": [
                    ("TEST007", "观察组", ProjectEnrollment.MARKER_IN, ""),
                    ("TEST008", "观察组", ProjectEnrollment.MARKER_IN, ""),
                    ("TEST009", "治疗组", ProjectEnrollment.MARKER_WITHDRAWN, "不良反应后停研"),
                    ("TEST010", "治疗组", ProjectEnrollment.MARKER_LOST, "电话无法接通"),
                    ("TEST011", "对照组", ProjectEnrollment.MARKER_COMPLETED, "已结题"),
                ],
            },
            {
                "name": "内分泌代谢整合管理队列",
                "principal_investigator": "陈老师",
                "status": ResearchProject.STATUS_PAUSED,
                "target_enrollment": 60,
                "assignments": [
                    ("TEST012", "代谢组", ProjectEnrollment.MARKER_IN, ""),
                    ("TEST013", "代谢组", ProjectEnrollment.MARKER_IN, ""),
                    ("TEST014", "对照组", ProjectEnrollment.MARKER_COMPLETED, "完成全年随访"),
                    ("TEST015", "对照组", ProjectEnrollment.MARKER_WITHDRAWN, "依从性差退出"),
                ],
            },
            {
                "name": "慢病管理结题项目",
                "principal_investigator": "赵老师",
                "status": ResearchProject.STATUS_COMPLETED,
                "target_enrollment": 40,
                "assignments": [
                    ("TEST016", "一期组", ProjectEnrollment.MARKER_COMPLETED, "已完成随访"),
                    ("TEST017", "一期组", ProjectEnrollment.MARKER_COMPLETED, "已完成随访"),
                    ("TEST018", "二期组", ProjectEnrollment.MARKER_COMPLETED, "已完成随访"),
                    ("TEST019", "二期组", ProjectEnrollment.MARKER_LOST, "末次失访"),
                    ("TEST020", "二期组", ProjectEnrollment.MARKER_IN, ""),
                ],
            },
        ]
        managed_project_ids = []
        for spec in project_specs:
            project, _ = ResearchProject.objects.update_or_create(
                name=spec["name"],
                defaults={
                    "principal_investigator": spec["principal_investigator"],
                    "status": spec["status"],
                    "target_enrollment": spec["target_enrollment"],
                    "notes": "seed_sample_data 自动生成测试项目",
                },
            )
            managed_project_ids.append(project.id)
            keep_patient_ids = []
            for patient_id, group_name, marker_status, marker_note in spec["assignments"]:
                patient = Patient.objects.filter(patient_id=patient_id).first()
                if not patient:
                    continue
                keep_patient_ids.append(patient.id)
                marker_date = timezone.localdate() if marker_status != ProjectEnrollment.MARKER_IN else None
                marker_by = None
                marker_updated_at = timezone.now() if marker_status != ProjectEnrollment.MARKER_IN else None
                ProjectEnrollment.objects.update_or_create(
                    project=project,
                    patient=patient,
                    defaults={
                        "group_name": group_name,
                        "enrollment_date": timezone.localdate() - timedelta(days=30),
                        "notes": "seed_sample_data 自动生成",
                        "marker_status": marker_status,
                        "marker_date": marker_date,
                        "marker_note": marker_note,
                        "marker_by": marker_by,
                        "marker_updated_at": marker_updated_at,
                    },
                )
            ProjectEnrollment.objects.filter(project=project).exclude(patient_id__in=keep_patient_ids).delete()

        Patient.objects.filter(patient_id__startswith="TEST").exclude(patient_id__in=sample_ids).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(sample_ids)} 条示例患者数据与 {len(managed_project_ids)} 个测试项目已写入。"
            )
        )

