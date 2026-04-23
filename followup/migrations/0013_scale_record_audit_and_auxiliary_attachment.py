from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import followup.models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0012_treatment_admission_discharge_dates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="scalerecord",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_scale_records",
                to=settings.AUTH_USER_MODEL,
                verbose_name="录入人",
            ),
        ),
        migrations.AddField(
            model_name="scalerecord",
            name="updated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="最近修改时间"),
        ),
        migrations.AddField(
            model_name="scalerecord",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_scale_records",
                to=settings.AUTH_USER_MODEL,
                verbose_name="最近修改人",
            ),
        ),
        migrations.CreateModel(
            name="AuxiliaryExamAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=followup.models._auxiliary_attachment_upload_to, verbose_name="附件文件")),
                ("original_name", models.CharField(blank=True, max_length=255, verbose_name="原始文件名")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="上传时间")),
                (
                    "followup",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auxiliary_attachments",
                        to="followup.followup",
                        verbose_name="随访",
                    ),
                ),
                (
                    "treatment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auxiliary_attachments",
                        to="followup.treatment",
                        verbose_name="诊疗",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_auxiliary_attachments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="上传人",
                    ),
                ),
            ],
            options={
                "verbose_name": "辅助检查附件",
                "verbose_name_plural": "辅助检查附件",
                "ordering": ["created_at", "id"],
            },
        ),
    ]
