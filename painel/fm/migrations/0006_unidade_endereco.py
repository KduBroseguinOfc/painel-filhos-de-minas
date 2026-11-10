from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fm", "0005_indicadores_geo")]
    operations = [
        migrations.AddField("unidade", "endereco", models.CharField(blank=True, max_length=250)),
        migrations.AddField("unidade", "cep", models.CharField(blank=True, max_length=8)),
    ]
