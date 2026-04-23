from datetime import date, timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, models
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone


class Patient(models.Model):
    GENDER_CHOICES = [
        ("male", "男"),
        ("female", "女"),
        ("other", "其他"),
    ]

    patient_id = models.CharField("患者编号", max_length=30, unique=True, blank=True)
    outpatient_number = models.CharField("门诊号", max_length=50, blank=True)
    name = models.CharField("姓名", max_length=50)
    gender = models.CharField("性别", max_length=10, choices=GENDER_CHOICES)
    birth_date = models.DateField("出生日期", null=True, blank=True)
    ethnicity = models.CharField("民族", max_length=30, blank=True)
    age = models.PositiveIntegerField("年龄", default=0, blank=True)
    phone = models.CharField("电话", max_length=20, blank=True)
    address = models.CharField("住址", max_length=255, blank=True)
    group_name = models.CharField("分组", max_length=50, blank=True)
    diagnosis = models.CharField("诊断", max_length=100, blank=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_patients",
        verbose_name="录入人",
    )
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_patients",
        verbose_name="最近修改人",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField("最近修改时间", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "患者"
        verbose_name_plural = "患者"
        constraints = [
            models.UniqueConstraint(
                fields=["outpatient_number"],
                condition=~models.Q(outpatient_number=""),
                name="uniq_patient_outpatient_number_non_blank",
            ),
        ]
        indexes = [
            models.Index(fields=["outpatient_number"], name="idx_patient_outpatient_number"),
        ]

    def __str__(self):
        return f"{self.name} ({self.patient_id})"

    @classmethod
    def generate_patient_id(cls, target_date=None):
        target_date = target_date or timezone.localdate()
        prefix = target_date.strftime("%Y%m%d")
        latest_id = (
            cls.objects.filter(patient_id__startswith=prefix)
            .order_by("-patient_id")
            .values_list("patient_id", flat=True)
            .first()
        )
        sequence = 1
        if latest_id and latest_id[-4:].isdigit():
            sequence = int(latest_id[-4:]) + 1

        candidate = f"{prefix}{sequence:04d}"
        while cls.objects.filter(patient_id=candidate).exists():
            sequence += 1
            candidate = f"{prefix}{sequence:04d}"
        return candidate

    @property
    def current_age(self):
        if self.birth_date:
            today = timezone.localdate()
            age_value = today.year - self.birth_date.year
            if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
                age_value -= 1
            return max(age_value, 0)
        return self.age or None

    def save(self, *args, **kwargs):
        if self.birth_date:
            self.age = self.current_age or 0
        if self.patient_id:
            super().save(*args, **kwargs)
            return

        last_error = None
        for _ in range(10):
            self.patient_id = self.generate_patient_id()
            try:
                super().save(*args, **kwargs)
                return
            except IntegrityError as exc:
                last_error = exc
                self.patient_id = ""
        if last_error:
            raise last_error

    @property
    def latest_treatment(self):
        cached_treatment = getattr(self, "_latest_treatment_cache", None)
        if cached_treatment is not None:
            return cached_treatment
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("treatments")
        if prefetched is not None:
            if not prefetched:
                return None
            latest_treatment = sorted(
                prefetched,
                key=lambda item: (item.start_date or date.min, item.created_at),
                reverse=True,
            )[0]
            self._latest_treatment_cache = latest_treatment
            return latest_treatment
        latest_treatment = self.treatments.order_by("-start_date", "-created_at").first()
        self._latest_treatment_cache = latest_treatment
        return latest_treatment


class Treatment(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="treatments",
        verbose_name="患者",
    )
    group_name = models.CharField("就诊单位", max_length=50, blank=True)
    treatment_name = models.CharField("治疗方案", max_length=100)
    start_date = models.DateField("治疗开始日期")
    admission_date = models.DateField("入院日期", null=True, blank=True)
    discharge_date = models.DateField("出院日期", null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_treatments",
        verbose_name="录入人",
    )
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_treatments",
        verbose_name="最近修改人",
    )
    total_weeks = models.PositiveIntegerField("总随访周数", default=12)
    followup_interval_days = models.PositiveIntegerField("随访间隔（天）", default=14)
    followup_closed = models.BooleanField("已结束回访", default=False)
    followup_closed_at = models.DateField("结束回访日期", null=True, blank=True)
    chief_complaint = models.TextField("主诉", blank=True)
    present_illness = models.TextField("现病史", blank=True)
    past_history = models.TextField("既往史", blank=True)
    personal_history = models.TextField("个人史", blank=True)
    marital_history = models.TextField("婚育史", blank=True)
    allergy_history = models.TextField("过敏史", blank=True)
    family_history = models.TextField("家族史", blank=True)
    tongue_diagnosis = models.TextField("舌诊", blank=True)
    pulse_diagnosis = models.TextField("脉诊", blank=True)
    tcm_disease = models.CharField("中医疾病", max_length=100, blank=True)
    western_disease = models.CharField("西医疾病", max_length=100, blank=True)
    treatment_principle = models.TextField("治则治法", blank=True)
    pathogenesis = models.TextField("病因病机", blank=True)
    symptom_syndrome = models.TextField("症状/证候", blank=True)
    prescription = models.TextField("处方", blank=True)
    prescription_usage_method = models.TextField("用药方式", blank=True)
    auxiliary_exam_results = models.TextField("辅助检查", blank=True)
    notes = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField("最近修改时间", null=True, blank=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]
        verbose_name = "诊疗"
        verbose_name_plural = "诊疗"
        indexes = [
            models.Index(fields=["patient", "-start_date", "-created_at"], name="idx_treat_patient_latest"),
        ]

    def __str__(self):
        return f"{self.patient.name} - {self.treatment_name}"

    @property
    def prescription_items_display(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("prescription_items")
        items = prefetched if prefetched is not None else self.prescription_items.all()
        return [item.display_text for item in items]

    def _prefetched_followups(self):
        cached_followups = getattr(self, "_sorted_prefetched_followups", None)
        if cached_followups is not None:
            return cached_followups
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("followups")
        if prefetched is None:
            return None
        sorted_followups = sorted(prefetched, key=lambda item: (item.visit_number, item.followup_date))
        self._sorted_prefetched_followups = sorted_followups
        return sorted_followups

    def close_followup(self):
        self.followup_closed = True
        self.followup_closed_at = timezone.localdate()
        self.save(update_fields=["followup_closed", "followup_closed_at"])

    def reopen_followup(self):
        self.followup_closed = False
        self.followup_closed_at = None
        self.save(update_fields=["followup_closed", "followup_closed_at"])

    @property
    def display_visit_unit(self):
        return self.group_name or self.patient.group_name

    @property
    def display_group_name(self):
        # 兼容旧调用，统一映射到“就诊单位”。
        return self.display_visit_unit

    @property
    def display_western_disease(self):
        return self.western_disease or self.patient.diagnosis

    @property
    def planned_followup_count(self):
        if self.followup_interval_days <= 0 or self.total_weeks <= 0:
            return 0
        return max(1, (self.total_weeks * 7) // self.followup_interval_days)

    @property
    def completed_followup_count(self):
        prefetched = self._prefetched_followups()
        if prefetched is not None:
            return len(prefetched)
        return self.followups.count()

    @property
    def followup_count(self):
        return self.completed_followup_count

    @property
    def latest_visit_number(self):
        prefetched = self._prefetched_followups()
        if prefetched is not None:
            return prefetched[-1].visit_number if prefetched else 0
        latest = (
            self.followups.order_by("-visit_number")
            .values_list("visit_number", flat=True)
            .first()
        )
        return latest or 0

    @property
    def progress_percent(self):
        total = self.planned_followup_count
        if total == 0:
            return 0
        return min(100, int(self.completed_followup_count / total * 100))

    @property
    def next_followup_number(self):
        return self.latest_visit_number + 1

    @property
    def next_followup_date(self):
        if self.followup_closed:
            return None
        if self.completed_followup_count >= self.planned_followup_count:
            return None
        prefetched = self._prefetched_followups()
        latest_followup = prefetched[-1] if prefetched else None
        if latest_followup is None:
            latest_followup = self.followups.order_by("-visit_number", "-followup_date").first()
        if latest_followup:
            if latest_followup.planned_next_followup_date:
                return latest_followup.planned_next_followup_date
            return latest_followup.followup_date + timedelta(days=self.followup_interval_days)
        return self.start_date + timedelta(days=self.followup_interval_days)

    @property
    def is_due_today(self):
        next_date = self.next_followup_date
        return bool(next_date and next_date == timezone.localdate())

    @property
    def is_overdue(self):
        next_date = self.next_followup_date
        return bool(next_date and next_date < timezone.localdate())

    @property
    def status_label(self):
        if self.followup_closed:
            return "已完成"
        if self.completed_followup_count >= self.planned_followup_count:
            return "已完成"
        if self.is_due_today:
            return "今日回访"
        if self.is_overdue:
            return "已逾期"
        return "随访中"

    def sync_prescription_text(self):
        self.prescription = "\n".join(self.prescription_items_display)


class FollowUp(models.Model):
    TYPE_PHONE = "phone"
    TYPE_OUTPATIENT = "outpatient"
    TYPE_CHOICES = [
        (TYPE_PHONE, "电话/线上随访"),
        (TYPE_OUTPATIENT, "门诊复诊"),
    ]

    treatment = models.ForeignKey(
        Treatment,
        on_delete=models.CASCADE,
        related_name="followups",
        verbose_name="诊疗",
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_followups",
        verbose_name="录入人",
    )
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_followups",
        verbose_name="最近修改人",
    )
    visit_number = models.PositiveIntegerField("第几次随访")
    followup_type = models.CharField(
        "随访类别",
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_PHONE,
    )
    followup_date = models.DateField("随访日期", default=timezone.localdate)
    planned_next_followup_date = models.DateField(
        "下次建议随访日期",
        null=True,
        blank=True,
        help_text="默认按本次随访后 14 天生成，也可以手动调整。",
    )
    symptoms = models.TextField("症状变化", blank=True)
    medication_adherence = models.CharField("用药依从性", max_length=100, blank=True)
    adverse_events = models.TextField("不良反应", blank=True)
    chief_complaint = models.TextField("主诉", blank=True)
    present_illness = models.TextField("现病史", blank=True)
    tongue_diagnosis = models.TextField("舌诊", blank=True)
    pulse_diagnosis = models.TextField("脉诊", blank=True)
    treatment_principle = models.TextField("治则治法", blank=True)
    prescription_summary = models.TextField("处方摘要", blank=True)
    auxiliary_exam_results = models.TextField("辅助检查", blank=True)
    notes = models.TextField("备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField("最近修改时间", null=True, blank=True)

    class Meta:
        ordering = ["visit_number", "followup_date"]
        verbose_name = "随访记录"
        verbose_name_plural = "随访记录"
        constraints = [
            models.UniqueConstraint(
                fields=["treatment", "visit_number"], name="unique_followup_visit_number"
            )
        ]
        indexes = [
            models.Index(fields=["treatment", "-visit_number", "-followup_date"], name="idx_followup_latest"),
        ]

    def __str__(self):
        return f"{self.treatment.patient.name} - 第{self.visit_number}次随访"


def _auxiliary_attachment_upload_to(instance, filename):
    today = timezone.localdate().strftime("%Y%m%d")
    if instance.followup_id:
        return f"auxiliary/followups/{instance.followup_id}/{today}_{filename}"
    if instance.treatment_id:
        return f"auxiliary/treatments/{instance.treatment_id}/{today}_{filename}"
    return f"auxiliary/unbound/{today}_{filename}"


class AuxiliaryExamAttachment(models.Model):
    treatment = models.ForeignKey(
        Treatment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="auxiliary_attachments",
        verbose_name="诊疗",
    )
    followup = models.ForeignKey(
        FollowUp,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="auxiliary_attachments",
        verbose_name="随访",
    )
    file = models.FileField("附件文件", upload_to=_auxiliary_attachment_upload_to)
    original_name = models.CharField("原始文件名", max_length=255, blank=True)
    note = models.CharField("附件备注", max_length=120, blank=True)
    uploaded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_auxiliary_attachments",
        verbose_name="上传人",
    )
    created_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "辅助检查附件"
        verbose_name_plural = "辅助检查附件"

    def __str__(self):
        owner = self.followup or self.treatment
        return f"{self.original_name or self.file.name} - {owner}"


class ResearchProject(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "进行中"),
        (STATUS_PAUSED, "暂停"),
        (STATUS_COMPLETED, "已完成"),
    ]

    name = models.CharField("项目名称", max_length=120, unique=True)
    principal_investigator = models.CharField("负责人", max_length=50, blank=True)
    status = models.CharField("项目状态", max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    target_enrollment = models.PositiveIntegerField("目标例数", default=0)
    notes = models.TextField("项目备注", blank=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_research_projects",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField("最近修改时间", auto_now=True)

    class Meta:
        ordering = ["-created_at", "name"]
        verbose_name = "研究项目"
        verbose_name_plural = "研究项目"

    def __str__(self):
        return self.name

    @property
    def enrollment_count(self):
        return self.enrollments.count()


class ProjectEnrollment(models.Model):
    MARKER_IN = "in"
    MARKER_COMPLETED = "completed"
    MARKER_WITHDRAWN = "withdrawn"
    MARKER_LOST = "lost"
    # legacy values kept for compatibility/migration
    MARKER_PROTOCOL = "protocol_violation"
    MARKER_ADVERSE = "adverse_event"
    MARKER_DEATH = "death"
    MARKER_TRANSFER = "transfer"
    MARKER_PROJECT_END = "project_terminated"
    MARKER_CHOICES = [
        (MARKER_IN, "在组"),
        (MARKER_COMPLETED, "完成"),
        (MARKER_WITHDRAWN, "退出"),
        (MARKER_LOST, "脱落"),
    ]

    project = models.ForeignKey(
        ResearchProject,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="研究项目",
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="project_enrollments",
        verbose_name="患者",
    )
    group_name = models.CharField("项目分组", max_length=60, blank=True)
    enrollment_date = models.DateField("入组日期", default=timezone.localdate)
    notes = models.TextField("入组备注", blank=True)
    marker_status = models.CharField(
        "标记状态",
        max_length=30,
        choices=MARKER_CHOICES,
        default=MARKER_IN,
    )
    marker_date = models.DateField("标记日期", null=True, blank=True)
    marker_note = models.CharField("标记说明", max_length=200, blank=True)
    marker_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_project_enrollment_markers",
        verbose_name="标记人",
    )
    marker_updated_at = models.DateTimeField("标记更新时间", null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_project_enrollments",
        verbose_name="录入人",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-enrollment_date", "-created_at"]
        verbose_name = "项目入组记录"
        verbose_name_plural = "项目入组记录"
        constraints = [
            models.UniqueConstraint(
                fields=["project", "patient"],
                name="unique_project_patient_enrollment",
            )
        ]

    def __str__(self):
        return f"{self.project.name} - {self.patient.name}"


class UserProfile(models.Model):
    ROLE_ROOT = "root"
    ROLE_ADMIN = "admin"
    ROLE_NORMAL = "normal"
    ROLE_CHOICES = [
        (ROLE_ROOT, "Root"),
        (ROLE_ADMIN, "管理员"),
        (ROLE_NORMAL, "普通"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField("角色", max_length=20, choices=ROLE_CHOICES, default=ROLE_NORMAL)
    modify_window_days = models.PositiveIntegerField(
        "可修改/删除历史数据天数",
        null=True,
        blank=True,
        help_text="管理员默认 365 天，普通账号默认 3 天。",
    )
    allowed_projects = models.ManyToManyField(
        ResearchProject,
        blank=True,
        related_name="authorized_user_profiles",
        verbose_name="可管理项目",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "账号角色"
        verbose_name_plural = "账号角色"

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @classmethod
    def default_modify_window_days(cls, role):
        if role == cls.ROLE_ADMIN:
            return 365
        if role == cls.ROLE_NORMAL:
            return 3
        return None

    @property
    def effective_modify_window_days(self):
        if self.role == self.ROLE_ROOT:
            return None
        return self.modify_window_days or self.default_modify_window_days(self.role)

    def save(self, *args, **kwargs):
        if self.role != self.ROLE_ROOT and not self.modify_window_days:
            self.modify_window_days = self.default_modify_window_days(self.role)
        super().save(*args, **kwargs)


class ClinicalTerm(models.Model):
    CATEGORY_HERB = "herb"
    CATEGORY_TCM_DISEASE = "tcm_disease"
    CATEGORY_WESTERN_DISEASE = "western_disease"
    CATEGORY_TREATMENT_PRINCIPLE = "treatment_principle"
    CATEGORY_PATHOGENESIS = "pathogenesis"
    CATEGORY_SYMPTOM = "symptom"
    CATEGORY_CHOICES = [
        (CATEGORY_HERB, "中药饮片"),
        (CATEGORY_TCM_DISEASE, "中医疾病"),
        (CATEGORY_WESTERN_DISEASE, "西医疾病"),
        (CATEGORY_TREATMENT_PRINCIPLE, "治则治法"),
        (CATEGORY_PATHOGENESIS, "病因病机"),
        (CATEGORY_SYMPTOM, "症状/证候"),
    ]

    category = models.CharField("术语分类", max_length=50, choices=CATEGORY_CHOICES)
    name = models.CharField("术语名称", max_length=100)
    alias = models.CharField("别名/关键词", max_length=255, blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "sort_order", "name"]
        verbose_name = "专业术语"
        verbose_name_plural = "专业术语"
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="unique_clinical_term")
        ]

    def __str__(self):
        return f"{self.get_category_display()} - {self.name}"


class PrescriptionTemplate(models.Model):
    name = models.CharField("模板名称", max_length=100, unique=True)
    usage_method = models.CharField("用药方式", max_length=255, blank=True)
    notes = models.TextField("模板备注", blank=True)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "处方模板"
        verbose_name_plural = "处方模板"

    def __str__(self):
        return self.name


class PrescriptionTemplateItem(models.Model):
    template = models.ForeignKey(
        PrescriptionTemplate,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="处方模板",
    )
    herb_name = models.CharField("饮片名称", max_length=100)
    dosage = models.CharField("剂量", max_length=30, blank=True)
    unit = models.CharField("单位", max_length=20, default="g", blank=True)
    usage = models.CharField("脚注", max_length=100, blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "处方模板明细"
        verbose_name_plural = "处方模板明细"

    def __str__(self):
        return self.herb_name


class PrescriptionItem(models.Model):
    treatment = models.ForeignKey(
        Treatment,
        on_delete=models.CASCADE,
        related_name="prescription_items",
        verbose_name="诊疗",
    )
    herb_name = models.CharField("饮片名称", max_length=100)
    dosage = models.CharField("剂量", max_length=30, blank=True)
    unit = models.CharField("单位", max_length=20, default="g", blank=True)
    usage = models.CharField("脚注", max_length=100, blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "处方明细"
        verbose_name_plural = "处方明细"

    def __str__(self):
        return self.display_text

    @property
    def display_text(self):
        parts = [self.herb_name]
        dose_text = "".join(filter(None, [self.dosage, self.unit]))
        if dose_text:
            parts.append(dose_text)
        if self.usage:
            parts.append(self.usage)
        return " ".join(part for part in parts if part)


class ScaleTemplate(models.Model):
    name = models.CharField("量表名称", max_length=100, unique=True)
    description = models.TextField("量表说明", blank=True)
    is_active = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "量表模板"
        verbose_name_plural = "量表模板"

    def __str__(self):
        return self.name


class ScaleTemplateItem(models.Model):
    FIELD_GROUP = "group"
    FIELD_SCORE = "score"
    FIELD_NUMBER = "number"
    FIELD_TEXT = "text"
    FIELD_TEXTAREA = "textarea"
    FIELD_SELECT = "select"
    FIELD_TYPE_CHOICES = [
        (FIELD_GROUP, "分组"),
        (FIELD_SCORE, "评分"),
        (FIELD_NUMBER, "数值"),
        (FIELD_TEXT, "单行文本"),
        (FIELD_TEXTAREA, "多行文本"),
        (FIELD_SELECT, "单选"),
    ]

    template = models.ForeignKey(
        ScaleTemplate,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="量表模板",
    )
    label = models.CharField("条目名称", max_length=100)
    field_type = models.CharField("题型", max_length=20, choices=FIELD_TYPE_CHOICES, default=FIELD_SCORE)
    item_key = models.CharField("条目编码", max_length=50, blank=True)
    group_key = models.CharField("所属分组", max_length=50, blank=True)
    parent_key = models.CharField("父题编码", max_length=50, blank=True)
    help_text = models.CharField("提示", max_length=255, blank=True)
    score_min = models.PositiveSmallIntegerField("最小分", default=0)
    score_max = models.PositiveSmallIntegerField("最大分", default=6)
    options_text = models.CharField("选项定义", max_length=255, blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "量表条目"
        verbose_name_plural = "量表条目"

    def __str__(self):
        return f"{self.template.name} - {self.label}"


class ScaleRecord(models.Model):
    treatment = models.ForeignKey(
        Treatment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scale_records",
        verbose_name="诊疗",
    )
    followup = models.ForeignKey(
        FollowUp,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scale_records",
        verbose_name="随访",
    )
    template = models.ForeignKey(
        ScaleTemplate,
        on_delete=models.PROTECT,
        related_name="records",
        verbose_name="量表模板",
    )
    answers_json = models.JSONField("评分结果", default=list, blank=True)
    total_score = models.DecimalField("总分", max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.TextField("量表备注", blank=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_scale_records",
        verbose_name="录入人",
    )
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_scale_records",
        verbose_name="最近修改人",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField("最近修改时间", null=True, blank=True)

    class Meta:
        ordering = ["template__name", "id"]
        verbose_name = "量表记录"
        verbose_name_plural = "量表记录"

    def __str__(self):
        owner = self.treatment or self.followup
        return f"{self.template.name} - {owner}"


class MymopAssessment(models.Model):
    treatment = models.OneToOneField(
        Treatment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="mymop_assessment",
        verbose_name="诊疗",
    )
    followup = models.OneToOneField(
        FollowUp,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="mymop_assessment",
        verbose_name="随访",
    )
    symptom_1 = models.CharField("主要症状 1", max_length=100, blank=True)
    symptom_1_score = models.PositiveSmallIntegerField("主要症状 1 评分", null=True, blank=True)
    symptom_2 = models.CharField("主要症状 2", max_length=100, blank=True)
    symptom_2_score = models.PositiveSmallIntegerField("主要症状 2 评分", null=True, blank=True)
    activity = models.CharField("受影响活动", max_length=100, blank=True)
    activity_score = models.PositiveSmallIntegerField("活动评分", null=True, blank=True)
    wellbeing_score = models.PositiveSmallIntegerField("总体状态评分", null=True, blank=True)
    notes = models.TextField("量表备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "MYMOP 量表"
        verbose_name_plural = "MYMOP 量表"

    def __str__(self):
        if self.followup_id:
            return f"随访 MYMOP - {self.followup}"
        if self.treatment_id:
            return f"初诊 MYMOP - {self.treatment}"
        return "MYMOP 量表"

    @property
    def profile_score(self):
        scores = [
            score
            for score in [
                self.symptom_1_score,
                self.symptom_2_score,
                self.activity_score,
                self.wellbeing_score,
            ]
            if score is not None
        ]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)


@receiver(pre_delete, sender=ScaleTemplate)
def prevent_delete_used_scale_template(sender, instance, **kwargs):
    if instance.records.exists():
        raise ProtectedError(
            "该量表已被录入使用，数据库已有数据，不能删除。",
            protected_objects=instance.records.all(),
        )
