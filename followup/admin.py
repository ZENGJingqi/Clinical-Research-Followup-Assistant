from django.contrib import admin

from .models import (
    AuxiliaryExamAttachment,
    ClinicalTerm,
    FollowUp,
    MymopAssessment,
    Patient,
    PrescriptionItem,
    PrescriptionTemplate,
    PrescriptionTemplateItem,
    ProjectEnrollment,
    ResearchProject,
    ScaleRecord,
    ScaleTemplate,
    ScaleTemplateItem,
    Treatment,
    UserProfile,
)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("outpatient_number", "patient_id", "name", "gender", "birth_date", "current_age_display", "ethnicity")
    search_fields = ("outpatient_number", "patient_id", "name", "phone", "ethnicity")

    @admin.display(description="当前年龄")
    def current_age_display(self, obj):
        return obj.current_age or "-"


@admin.register(Treatment)
class TreatmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "treatment_name", "group_name", "start_date", "total_weeks", "created_by")
    list_filter = ("start_date", "group_name")


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("treatment", "visit_number", "followup_date", "created_by")
    list_filter = ("followup_date",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "modify_window_days", "created_at")
    list_filter = ("role",)


class PrescriptionTemplateItemInline(admin.TabularInline):
    model = PrescriptionTemplateItem
    extra = 1


@admin.register(PrescriptionTemplate)
class PrescriptionTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "usage_method", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "usage_method")
    inlines = [PrescriptionTemplateItemInline]


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = ("treatment", "herb_name", "dosage", "unit", "usage", "sort_order")
    list_filter = ("unit",)
    search_fields = ("herb_name", "treatment__patient__name")


class ScaleTemplateItemInline(admin.TabularInline):
    model = ScaleTemplateItem
    extra = 1


@admin.register(ScaleTemplate)
class ScaleTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = [ScaleTemplateItemInline]

    def has_change_permission(self, request, obj=None):
        # 已被使用的量表不允许在 admin 中继续编辑，避免历史记录语义漂移。
        if obj is not None and obj.records.exists():
            return False
        return super().has_change_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None):
        # admin 侧统一禁用删除，避免误触发级联删除历史量表记录。
        return False


@admin.register(ScaleRecord)
class ScaleRecordAdmin(admin.ModelAdmin):
    list_display = (
        "template",
        "treatment",
        "followup",
        "total_score",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    list_filter = ("template",)


@admin.register(AuxiliaryExamAttachment)
class AuxiliaryExamAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "note", "treatment", "followup", "uploaded_by", "created_at")
    list_filter = ("created_at",)


@admin.register(ClinicalTerm)
class ClinicalTermAdmin(admin.ModelAdmin):
    list_display = ("category", "name", "alias", "sort_order", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "alias")


@admin.register(MymopAssessment)
class MymopAssessmentAdmin(admin.ModelAdmin):
    list_display = ("treatment", "followup", "profile_score", "created_at")


@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "principal_investigator", "status", "target_enrollment", "created_by")
    list_filter = ("status",)
    search_fields = ("name", "principal_investigator")


@admin.register(ProjectEnrollment)
class ProjectEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("project", "patient", "group_name", "enrollment_date", "created_by")
    list_filter = ("project", "enrollment_date")
    search_fields = ("project__name", "patient__name", "patient__outpatient_number", "patient__patient_id", "group_name")
