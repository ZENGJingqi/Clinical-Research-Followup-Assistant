from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0021_alter_scalerecord_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="outpatient_number",
            field=models.CharField(blank=True, max_length=50, verbose_name="门诊号"),
        ),
    ]

