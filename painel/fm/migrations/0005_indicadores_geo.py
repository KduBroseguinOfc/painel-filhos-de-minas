from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fm", "0004_alerta_canais")]
    operations = [
        migrations.AddField("gestante", "primeira_consulta", models.DateTimeField(null=True)),
        migrations.AddField("gestante", "semanas_na_captacao", models.IntegerField(null=True)),
        migrations.AddField("gestante", "consultas", models.IntegerField(default=0)),
        migrations.AddField("gestante", "dias_sem_consulta", models.IntegerField(null=True)),
        migrations.AddField("gestante", "risco_hipertensao", models.BooleanField(default=False)),
        migrations.AddField("gestante", "risco_diabetes", models.BooleanField(default=False)),
        migrations.AddField("gestante", "gestacao_multipla", models.BooleanField(default=False)),
        migrations.AddField("gestante", "cep", models.CharField(blank=True, max_length=8)),
        migrations.AddField("gestante", "logradouro", models.CharField(blank=True, max_length=200)),
        migrations.AddField("gestante", "numero", models.CharField(blank=True, max_length=10)),
        migrations.AddField("gestante", "bairro_end", models.CharField(blank=True, max_length=100)),
        migrations.AddField("gestante", "lat", models.FloatField(null=True)),
        migrations.AddField("gestante", "lon", models.FloatField(null=True)),
        migrations.AddField("gestante", "geo_precisao", models.CharField(blank=True, max_length=12)),
        migrations.AddField("gestante", "geo_em", models.DateTimeField(null=True)),
        migrations.AddField("unidade", "lat", models.FloatField(null=True)),
        migrations.AddField("unidade", "lon", models.FloatField(null=True)),
        migrations.AddField("unidade", "geo_em", models.DateTimeField(null=True)),
        migrations.CreateModel(
            name="GeoCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("chave", models.CharField(max_length=200, unique=True)),
                ("lat", models.FloatField(null=True)),
                ("lon", models.FloatField(null=True)),
                ("precisao", models.CharField(blank=True, max_length=12)),
                ("fonte", models.CharField(blank=True, max_length=20)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
