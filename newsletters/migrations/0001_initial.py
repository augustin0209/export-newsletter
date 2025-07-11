# Generated by Django 5.2.3 on 2025-06-12 16:25

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Newsletter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titre', models.CharField(max_length=255)),
                ('objet', models.CharField(max_length=255)),
                ('contenu_html', models.TextField()),
                ('contenu_text', models.TextField()),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('date_envoi', models.DateTimeField(blank=True, null=True)),
                ('date_envoi_planifie', models.DateTimeField(blank=True, null=True)),
                ('statut', models.CharField(default='brouillon', max_length=20)),
                ('police', models.CharField(default='Arial', max_length=50)),
                ('destinataires_cc', models.TextField(blank=True, null=True)),
                ('destinataires_cci', models.TextField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Subscriber',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('nom', models.CharField(blank=True, max_length=100, null=True)),
                ('prenom', models.CharField(blank=True, max_length=100, null=True)),
                ('date_inscription', models.DateTimeField(auto_now_add=True)),
                ('statut', models.CharField(default='actif', max_length=20)),
                ('token_desabonnement', models.CharField(max_length=32, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Envoi',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_envoi', models.DateTimeField(auto_now_add=True)),
                ('statut', models.CharField(max_length=20)),
                ('newsletter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='newsletters.newsletter')),
                ('subscriber', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='newsletters.subscriber')),
            ],
            options={
                'unique_together': {('newsletter', 'subscriber')},
            },
        ),
    ]
