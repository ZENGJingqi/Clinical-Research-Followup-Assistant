from django.db import migrations, models


def normalize_project_enrollment_markers(apps, schema_editor):
    ProjectEnrollment = apps.get_model("followup", "ProjectEnrollment")
    alias_values = {
        "protocol_violation",
        "adverse_event",
        "death",
        "transfer",
        "project_terminated",
    }
    ProjectEnrollment.objects.filter(marker_status__in=alias_values).update(marker_status="withdrawn")


class Migration(migrations.Migration):
    dependencies = [
        ("followup", "0016_project_enrollment_marker_fields"),
    ]

    operations = [
        migrations.RunPython(normalize_project_enrollment_markers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="projectenrollment",
            name="marker_status",
            field=models.CharField(
                choices=[
                    ("in", "在组"),
                    ("completed", "完成"),
                    ("withdrawn", "退出"),
                    ("lost", "脱落"),
                ],
                default="in",
                max_length=30,
                verbose_name="标记状态",
            ),
        ),
    ]
