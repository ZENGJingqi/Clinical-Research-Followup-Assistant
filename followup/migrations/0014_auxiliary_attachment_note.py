from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0013_scale_record_audit_and_auxiliary_attachment"),
    ]

    operations = [
        migrations.AddField(
            model_name="auxiliaryexamattachment",
            name="note",
            field=models.CharField(blank=True, max_length=120, verbose_name="附件备注"),
        ),
    ]
