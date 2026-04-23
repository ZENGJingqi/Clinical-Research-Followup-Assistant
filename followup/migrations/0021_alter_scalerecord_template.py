from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0020_alter_userprofile_modify_window_days_help_text"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scalerecord",
            name="template",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="records",
                to="followup.scaletemplate",
                verbose_name="量表模板",
            ),
        ),
    ]

