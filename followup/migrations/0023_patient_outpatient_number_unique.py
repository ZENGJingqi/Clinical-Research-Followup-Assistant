from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0022_patient_outpatient_number"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="patient",
            constraint=models.UniqueConstraint(
                condition=models.Q(("outpatient_number", ""), _negated=True),
                fields=("outpatient_number",),
                name="uniq_patient_outpatient_number_non_blank",
            ),
        ),
        migrations.AddIndex(
            model_name="patient",
            index=models.Index(fields=["outpatient_number"], name="idx_patient_outpatient_number"),
        ),
    ]
