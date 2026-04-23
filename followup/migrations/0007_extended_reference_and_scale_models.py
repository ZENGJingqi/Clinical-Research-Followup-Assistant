from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0006_userprofile_modify_window_days"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="treatment",
            name="recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="recorded_treatments",
                to=settings.AUTH_USER_MODEL,
                verbose_name="录入者",
            ),
        ),
        migrations.AddField(
            model_name="treatment",
            name="prescription_usage_method",
            field=models.TextField(blank=True, verbose_name="用药方式"),
        ),
        migrations.AddField(
            model_name="treatment",
            name="auxiliary_exam_results",
            field=models.TextField(blank=True, verbose_name="辅助检查"),
        ),
        migrations.AddField(
            model_name="followup",
            name="recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="recorded_followups",
                to=settings.AUTH_USER_MODEL,
                verbose_name="录入者",
            ),
        ),
        migrations.AddField(
            model_name="followup",
            name="followup_type",
            field=models.CharField(
                choices=[("phone", "电话/线上随访"), ("outpatient", "门诊复诊")],
                default="phone",
                max_length=20,
                verbose_name="随访类别",
            ),
        ),
        migrations.AddField(
            model_name="followup",
            name="chief_complaint",
            field=models.TextField(blank=True, verbose_name="主诉"),
        ),
        migrations.AddField(
            model_name="followup",
            name="present_illness",
            field=models.TextField(blank=True, verbose_name="现病史"),
        ),
        migrations.AddField(
            model_name="followup",
            name="tongue_diagnosis",
            field=models.TextField(blank=True, verbose_name="舌诊"),
        ),
        migrations.AddField(
            model_name="followup",
            name="pulse_diagnosis",
            field=models.TextField(blank=True, verbose_name="脉诊"),
        ),
        migrations.AddField(
            model_name="followup",
            name="treatment_principle",
            field=models.TextField(blank=True, verbose_name="治则治法"),
        ),
        migrations.AddField(
            model_name="followup",
            name="prescription_summary",
            field=models.TextField(blank=True, verbose_name="处方摘要"),
        ),
        migrations.AddField(
            model_name="followup",
            name="auxiliary_exam_results",
            field=models.TextField(blank=True, verbose_name="辅助检查"),
        ),
        migrations.CreateModel(
            name="ClinicalTerm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(choices=[("herb", "中药饮片"), ("tcm_disease", "中医疾病"), ("western_disease", "西医疾病"), ("treatment_principle", "治则治法"), ("symptom", "症状/证候")], max_length=50, verbose_name="术语分类")),
                ("name", models.CharField(max_length=100, verbose_name="术语名称")),
                ("alias", models.CharField(blank=True, max_length=255, verbose_name="别名/关键词")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="排序")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "专业术语",
                "verbose_name_plural": "专业术语",
                "ordering": ["category", "sort_order", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="clinicalterm",
            constraint=models.UniqueConstraint(fields=("category", "name"), name="unique_clinical_term"),
        ),
        migrations.CreateModel(
            name="PrescriptionTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="模板名称")),
                ("usage_method", models.CharField(blank=True, max_length=255, verbose_name="用药方式")),
                ("notes", models.TextField(blank=True, verbose_name="模板备注")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "处方模板",
                "verbose_name_plural": "处方模板",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="PrescriptionTemplateItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("herb_name", models.CharField(max_length=100, verbose_name="饮片名称")),
                ("dosage", models.CharField(blank=True, max_length=30, verbose_name="剂量")),
                ("unit", models.CharField(blank=True, default="g", max_length=20, verbose_name="单位")),
                ("usage", models.CharField(blank=True, max_length=100, verbose_name="脚注")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="排序")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="followup.prescriptiontemplate", verbose_name="处方模板")),
            ],
            options={
                "verbose_name": "处方模板明细",
                "verbose_name_plural": "处方模板明细",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="PrescriptionItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("herb_name", models.CharField(max_length=100, verbose_name="饮片名称")),
                ("dosage", models.CharField(blank=True, max_length=30, verbose_name="剂量")),
                ("unit", models.CharField(blank=True, default="g", max_length=20, verbose_name="单位")),
                ("usage", models.CharField(blank=True, max_length=100, verbose_name="脚注")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="排序")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("treatment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="prescription_items", to="followup.treatment", verbose_name="诊疗")),
            ],
            options={
                "verbose_name": "处方明细",
                "verbose_name_plural": "处方明细",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="ScaleTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="量表名称")),
                ("description", models.TextField(blank=True, verbose_name="量表说明")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "量表模板",
                "verbose_name_plural": "量表模板",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ScaleTemplateItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=100, verbose_name="条目名称")),
                ("help_text", models.CharField(blank=True, max_length=255, verbose_name="提示")),
                ("score_min", models.PositiveSmallIntegerField(default=0, verbose_name="最小分")),
                ("score_max", models.PositiveSmallIntegerField(default=6, verbose_name="最大分")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="排序")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="followup.scaletemplate", verbose_name="量表模板")),
            ],
            options={
                "verbose_name": "量表条目",
                "verbose_name_plural": "量表条目",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="ScaleRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("answers_json", models.JSONField(blank=True, default=list, verbose_name="评分结果")),
                ("total_score", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="总分")),
                ("notes", models.TextField(blank=True, verbose_name="量表备注")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("followup", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="scale_records", to="followup.followup", verbose_name="随访")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="records", to="followup.scaletemplate", verbose_name="量表模板")),
                ("treatment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="scale_records", to="followup.treatment", verbose_name="诊疗")),
            ],
            options={
                "verbose_name": "量表记录",
                "verbose_name_plural": "量表记录",
                "ordering": ["template__name", "id"],
            },
        ),
        migrations.CreateModel(
            name="MymopAssessment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("symptom_1", models.CharField(blank=True, max_length=100, verbose_name="主要症状 1")),
                ("symptom_1_score", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="主要症状 1 评分")),
                ("symptom_2", models.CharField(blank=True, max_length=100, verbose_name="主要症状 2")),
                ("symptom_2_score", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="主要症状 2 评分")),
                ("activity", models.CharField(blank=True, max_length=100, verbose_name="受影响活动")),
                ("activity_score", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="活动评分")),
                ("wellbeing_score", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="总体状态评分")),
                ("notes", models.TextField(blank=True, verbose_name="量表备注")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("followup", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="mymop_assessment", to="followup.followup", verbose_name="随访")),
                ("treatment", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="mymop_assessment", to="followup.treatment", verbose_name="诊疗")),
            ],
            options={
                "verbose_name": "MYMOP 量表",
                "verbose_name_plural": "MYMOP 量表",
            },
        ),
    ]
