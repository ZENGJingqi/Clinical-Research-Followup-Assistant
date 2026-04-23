from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0009_scale_template_item_field_type_and_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scaletemplateitem",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("group", "分组"),
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
            name="group_key",
            field=models.CharField(blank=True, max_length=50, verbose_name="所属分组"),
        ),
        migrations.AddField(
            model_name="scaletemplateitem",
            name="item_key",
            field=models.CharField(blank=True, max_length=50, verbose_name="条目编码"),
        ),
        migrations.AddField(
            model_name="scaletemplateitem",
            name="parent_key",
            field=models.CharField(blank=True, max_length=50, verbose_name="父题编码"),
        ),
    ]
