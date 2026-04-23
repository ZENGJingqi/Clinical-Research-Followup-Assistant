import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from followup.models import FollowUp, Patient, ProjectEnrollment, ResearchProject, Treatment


class Command(BaseCommand):
    help = "生成中等规模项目测试数据（项目、分组、标记、患者、诊疗、随访）。"

    def add_arguments(self, parser):
        parser.add_argument("--patients", type=int, default=300, help="生成患者数量，默认 300")
        parser.add_argument("--projects", type=int, default=8, help="生成项目数量，默认 8")
        parser.add_argument(
            "--prefix",
            type=str,
            default="LOAD",
            help="测试患者编号前缀，默认 LOAD",
        )
        parser.add_argument(
            "--project-prefix",
            type=str,
            default="压测项目",
            help="测试项目名称前缀，默认 压测项目",
        )

    def handle(self, *args, **options):
        patient_count = max(1, int(options["patients"]))
        project_count = max(1, int(options["projects"]))
        prefix = (options["prefix"] or "LOAD").strip().upper()
        project_prefix = (options["project_prefix"] or "压测项目").strip()
        today = timezone.localdate()

        random.seed(20260414)
        family_names = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜")
        given_names = ["嘉宁", "博文", "子涵", "一鸣", "海峰", "雅琴", "思远", "晨曦", "知远", "安宁"]
        ethnicities = ["汉族", "回族", "满族", "苗族", "壮族", "维吾尔族", "土家族"]
        groups = ["治疗A组", "治疗B组", "对照组", "观察组", "随访强化组"]
        marker_values = [
            ProjectEnrollment.MARKER_IN,
            ProjectEnrollment.MARKER_COMPLETED,
            ProjectEnrollment.MARKER_WITHDRAWN,
            ProjectEnrollment.MARKER_LOST,
        ]
        marker_notes = {
            ProjectEnrollment.MARKER_COMPLETED: "已按计划完成随访",
            ProjectEnrollment.MARKER_WITHDRAWN: "患者主动退出项目",
            ProjectEnrollment.MARKER_LOST: "连续失联，判定脱落",
        }

        projects = []
        for index in range(1, project_count + 1):
            status = (
                ResearchProject.STATUS_ACTIVE
                if index % 3 == 1
                else ResearchProject.STATUS_PAUSED
                if index % 3 == 2
                else ResearchProject.STATUS_COMPLETED
            )
            project, _ = ResearchProject.objects.update_or_create(
                name=f"{project_prefix}{index:02d}",
                defaults={
                    "principal_investigator": f"PI-{index:02d}",
                    "status": status,
                    "target_enrollment": max(40, patient_count // 2),
                    "notes": "seed_project_load_data 自动生成",
                },
            )
            projects.append(project)

        created_patients = 0
        for index in range(1, patient_count + 1):
            patient_id = f"{prefix}{index:04d}"
            name = random.choice(family_names) + random.choice(given_names)
            gender = "male" if index % 2 else "female"
            birth_year = 1965 + (index % 35)
            birth_month = 1 + (index % 12)
            birth_day = 1 + (index % 27)
            patient, created = Patient.objects.update_or_create(
                patient_id=patient_id,
                defaults={
                    "name": name,
                    "gender": gender,
                    "birth_date": timezone.datetime(birth_year, birth_month, birth_day).date(),
                    "ethnicity": random.choice(ethnicities),
                    "phone": f"139{index:08d}"[-11:],
                    "address": f"测试地址 {index:03d} 号",
                },
            )
            if created:
                created_patients += 1

            start_days_ago = 3 + (index % 120)
            treatment, _ = Treatment.objects.update_or_create(
                patient=patient,
                treatment_name=f"测试诊疗方案{(index % 9) + 1}",
                start_date=today - timedelta(days=start_days_ago),
                defaults={
                    "group_name": f"门诊{(index % 4) + 1}组",
                    "total_weeks": 12,
                    "followup_interval_days": 14,
                    "chief_complaint": "用于项目联调与压测的测试主诉",
                    "present_illness": "测试现病史",
                    "tcm_disease": "胃脘痛",
                    "western_disease": "慢性胃炎",
                    "treatment_principle": "健脾和胃",
                    "prescription": "测试处方",
                    "notes": "seed_project_load_data 自动生成",
                },
            )

            followup_total = 1 + (index % 3)
            keep_visits = []
            for visit in range(1, followup_total + 1):
                keep_visits.append(visit)
                fdate = treatment.start_date + timedelta(days=visit * treatment.followup_interval_days)
                FollowUp.objects.update_or_create(
                    treatment=treatment,
                    visit_number=visit,
                    defaults={
                        "followup_date": fdate,
                        "planned_next_followup_date": fdate + timedelta(days=treatment.followup_interval_days),
                        "symptoms": "测试随访症状记录",
                        "medication_adherence": "良好" if visit % 2 else "一般",
                        "adverse_events": "" if visit != followup_total else "偶发轻微不适",
                        "notes": "seed_project_load_data 自动生成",
                    },
                )
            treatment.followups.exclude(visit_number__in=keep_visits).delete()

            # 每个患者归入 1~2 个项目，形成分组和标记测试面
            assign_projects = [projects[index % project_count]]
            if index % 5 == 0:
                assign_projects.append(projects[(index + 2) % project_count])

            keep_project_ids = []
            for project in assign_projects:
                keep_project_ids.append(project.id)
                marker_status = random.choice(marker_values)
                marker_date = today - timedelta(days=index % 45) if marker_status != ProjectEnrollment.MARKER_IN else None
                marker_note = marker_notes.get(marker_status, "")
                ProjectEnrollment.objects.update_or_create(
                    project=project,
                    patient=patient,
                    defaults={
                        "group_name": random.choice(groups),
                        "enrollment_date": today - timedelta(days=30 + (index % 180)),
                        "notes": "seed_project_load_data 自动生成",
                        "marker_status": marker_status,
                        "marker_date": marker_date,
                        "marker_note": marker_note,
                        "marker_updated_at": timezone.now() if marker_status != ProjectEnrollment.MARKER_IN else None,
                    },
                )
            ProjectEnrollment.objects.filter(patient=patient, project__name__startswith=project_prefix).exclude(
                project_id__in=keep_project_ids
            ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"生成完成：患者 {patient_count} 条（新增 {created_patients}），项目 {project_count} 个。"
            )
        )
