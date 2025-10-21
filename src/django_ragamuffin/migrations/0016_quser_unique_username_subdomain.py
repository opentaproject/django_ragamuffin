from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_ragamuffin", "0015_quser_subdomain"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="quser",
            constraint=models.UniqueConstraint(
                fields=("username", "subdomain"),
                name="unique_quser_username_subdomain",
            ),
        ),
    ]

