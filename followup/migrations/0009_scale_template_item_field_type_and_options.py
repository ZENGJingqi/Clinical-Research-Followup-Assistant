from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0008_audit_fields_and_field_alignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="scaletemplateitem",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("score", "评分"),
                    ("number", "数值"),
                    ("text", "单行文本"),
                    ("textarea", "多行文本"),
                    ("select", "单选"),
                ],
                default="score",
                max_length=20,
                verbose_name="题型",
            ),
        ),
        migrations.AddField(
            model_name="scaletemplateitem",
            name="options_text",
            field=models.CharField(blank=True, max_length=255, verbose_name="选项定义"),
        ),
    ]
