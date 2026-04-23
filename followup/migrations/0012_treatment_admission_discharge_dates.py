from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0011_treatment_pathogenesis_and_symptom_syndrome"),
    ]

    operations = [
        migrations.AddField(
            model_name="treatment",
            name="admission_date",
            field=models.DateField(blank=True, null=True, verbose_name="入院日期"),
        ),
        migrations.AddField(
            model_name="treatment",
            name="discharge_date",
            field=models.DateField(blank=True, null=True, verbose_name="出院日期"),
        ),
    ]
