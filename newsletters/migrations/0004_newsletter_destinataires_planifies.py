# Generated by Django 5.2.3 on 2025-06-19 13:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('newsletters', '0003_alter_newsletter_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='newsletter',
            name='destinataires_planifies',
            field=models.TextField(blank=True, null=True),
        ),
    ]
