from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("followup", "0007_extended_reference_and_scale_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_patients",
                to=settings.AUTH_USER_MODEL,
                verbose_name="录入人",
            ),
        ),
        migrations.AddField(
            model_name="patient",
            name="updated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="最近修改时间"),
        ),
        migrations.AddField(
            model_name="patient",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_patients",
                to=settings.AUTH_USER_MODEL,
                verbose_name="最近修改人",
            ),
        ),
        migrations.AddField(
            model_name="treatment",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_treatments",
                to=settings.AUTH_USER_MODEL,
                verbose_name="录入人",
            ),
        ),
        migrations.AddField(
            model_name="treatment",
            name="updated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="最近修改时间"),
        ),
        migrations.AddField(
            model_name="treatment",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_treatments",
                to=settings.AUTH_USER_MODEL,
                verbose_name="最近修改人",
            ),
        ),
        migrations.AddField(
            model_name="followup",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_followups",
                to=settings.AUTH_USER_MODEL,
                verbose_name="录入人",
            ),
        ),
        migrations.AddField(
            model_name="followup",
            name="updated_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="最近修改时间"),
        ),
        migrations.AddField(
            model_name="followup",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_followups",
                to=settings.AUTH_USER_MODEL,
                verbose_name="最近修改人",
            ),
        ),
        migrations.RemoveField(
            model_name="treatment",
            name="recorded_by",
        ),
        migrations.RemoveField(
            model_name="followup",
            name="recorded_by",
        ),
    ]
