from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("fm", "0012_exames_prenatal")]
    operations = [migrations.AddField(model_name="perfil", name="origem", field=models.CharField(default="local", max_length=10))]
