from django.db import migrations, models


def para_flags(apps, schema_editor):
    Alerta = apps.get_model("fm", "Alerta")
    for a in Alerta.objects.all():
        a.por_email = a.canal == "email"
        a.por_telegram = a.canal == "telegram"
        a.save(update_fields=["por_email", "por_telegram"])


def para_canal(apps, schema_editor):
    Alerta = apps.get_model("fm", "Alerta")
    for a in Alerta.objects.all():
        a.canal = "telegram" if a.por_telegram and not a.por_email else "email"
        a.save(update_fields=["canal"])


class Migration(migrations.Migration):
    dependencies = [("fm", "0003_telegram_canal")]
    operations = [
        migrations.AddField(model_name="alerta", name="por_email", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="alerta", name="por_telegram", field=models.BooleanField(default=False)),
        migrations.RunPython(para_flags, para_canal),
        migrations.RemoveField(model_name="alerta", name="canal"),
        migrations.AlterField(model_name="alerta", name="frequencia", field=models.CharField(choices=[("hora", "Na hora (após cada coleta, de hora em hora)"), ("dia", "Resumo diário às 08:00")], default="hora", max_length=5)),
    ]
