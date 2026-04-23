from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0010_scale_template_item_grouping_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="treatment",
            name="pathogenesis",
            field=models.TextField(blank=True, verbose_name="病因病机"),
        ),
        migrations.AddField(
            model_name="treatment",
            name="symptom_syndrome",
            field=models.TextField(blank=True, verbose_name="症状/证候"),
        ),
    ]
