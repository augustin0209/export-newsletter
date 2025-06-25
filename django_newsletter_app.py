

cd C:\newsletter_django
django-admin startproject newsletter_project
cd newsletter_project
python manage.py startapp newsletters

# ✅ Etape 3 : Enregistrer l'application dans les paramètres du projet
# Ouvre le fichier newsletter_project/settings.py et ajoute 'newsletters' dans INSTALLED_APPS

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'newsletters',  # Ajoute cette ligne
]

# ✅ Etape 4 : Créer le modèle Newsletter
# Dans newsletters/models.py

from django.db import models
from django.utils import timezone

class Newsletter(models.Model):
    title = models.CharField(max_length=255)
    content_html = models.TextField()
    scheduled_date = models.DateTimeField()
    sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_ready_to_send(self):
        return not self.sent and self.scheduled_date <= timezone.now()

    def __str__(self):
        return self.title

# ✅ Etape 5 : Créer les migrations de base de données
python manage.py makemigrations
python manage.py migrate

# ✅ Etape 6 : Créer un formulaire simple
# Dans newsletters/forms.py

from django import forms
from .models import Newsletter

class NewsletterForm(forms.ModelForm):
    class Meta:
        model = Newsletter
        fields = ['title', 'content_html', 'scheduled_date']
        widgets = {
            'scheduled_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

# ✅ Etape 7 : Créer une vue pour créer une newsletter
# Dans newsletters/views.py

from django.shortcuts import render, redirect
from .forms import NewsletterForm

def create_newsletter(request):
    if request.method == "POST":
        form = NewsletterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("/success")
    else:
        form = NewsletterForm()
    return render(request, "create_newsletter.html", {"form": form})

# ✅ Etape 8 : Configurer les URLs
# Dans newsletter_project/urls.py ajoute :

from django.contrib import admin
from django.urls import path
from newsletters.views import create_newsletter

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', create_newsletter, name='create_newsletter'),
    path('success/', lambda request: HttpResponse("Newsletter créée !")),
]

# ✅ Etape 9 : Créer le template HTML
# Crée le dossier : newsletters/templates
# Puis crée : newsletters/templates/create_newsletter.html

<!DOCTYPE html>
<html>
<head>
    <title>Créer une newsletter</title>
</head>
<body>
    <h1>Créer une newsletter</h1>
    <form method="post">
        {% csrf_token %}
        {{ form.as_p }}
        <button type="submit">Programmer l'envoi</button>
    </form>
</body>
</html>

# ✅ Etape 10 : Créer la commande de planification d'envoi
# Crée le dossier : newsletters/management/commands/
# Puis crée : newsletters/management/commands/send_newsletters.py

from django.core.management.base import BaseCommand
from newsletters.models import Newsletter
from django.core.mail import EmailMessage
from django.conf import settings

class Command(BaseCommand):
    help = "Envoie les newsletters planifiées"

    def handle(self, *args, **kwargs):
        newsletters = Newsletter.objects.filter(sent=False)
        for newsletter in newsletters:
            if newsletter.is_ready_to_send():
                msg = EmailMessage(
                    newsletter.title,
                    newsletter.content_html,
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_FROM_EMAIL],  # à adapter avec la liste d'abonnés
                )
                msg.content_subtype = "html"
                msg.send()
                newsletter.sent = True
                newsletter.save()
                self.stdout.write(f"Newsletter '{newsletter.title}' envoyée.")

# ✅ Etape 11 : Configurer l'e-mail dans settings.py
# Dans newsletter_project/settings.py ajoute :

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'tonemail@gmail.com'
EMAIL_HOST_PASSWORD = 'ton_mot_de_passe'
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# ✅ Etape 12 : Programmer une tâche planifiée (CRON / Windows Task Scheduler)
# Pour lancer la commande automatiquement :
# python manage.py send_newsletters
# toutes les X minutes pour vérifier les envois prévus.

# Tu peux tester manuellement déjà avec :
python manage.py send_newsletters
