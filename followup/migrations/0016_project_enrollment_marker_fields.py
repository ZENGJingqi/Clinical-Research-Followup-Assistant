from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0015_alter_clinicalterm_category_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="projectenrollment",
            name="marker_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_project_enrollment_markers",
                to=settings.AUTH_USER_MODEL,
                verbose_name="标记人",
            ),
        ),
        migrations.AddField(
            model_name="projectenrollment",
            name="marker_date",
            field=models.DateField(blank=True, null=True, verbose_name="标记日期"),
        ),
        migrations.AddField(
            model_name="projectenrollment",
            name="marker_note",
            field=models.CharField(blank=True, max_length=200, verbose_name="标记说明"),
        ),
        migrations.AddField(
            model_name="projectenrollment",
            name="marker_status",
            field=models.CharField(
                choices=[
                    ("in", "在组随访"),
                    ("completed", "已完成随访"),
                    ("withdrawn", "主动退出"),
                    ("lost", "失访"),
                    ("protocol_violation", "方案违背出组"),
                    ("adverse_event", "不良事件出组"),
                    ("death", "死亡"),
                    ("transfer", "转院/转诊"),
                    ("project_terminated", "研究终止"),
                ],
                default="in",
                max_length=30,
                verbose_name="标记状态",
            ),
        ),
        migrations.AddField(
            model_name="projectenrollment",
            name="marker_updated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="标记更新时间"),
        ),
    ]
