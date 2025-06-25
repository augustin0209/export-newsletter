from django.db import models
from django.utils import timezone
import hashlib
from datetime import datetime

class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    nom = models.CharField(max_length=100, null=True, blank=True)
    prenom = models.CharField(max_length=100, null=True, blank=True)
    date_inscription = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, default='actif')
    token_desabonnement = models.CharField(max_length=32, unique=True)

    def save(self, *args, **kwargs):
        if not self.token_desabonnement:
            self.token_desabonnement = self.generate_unsubscribe_token()
        super().save(*args, **kwargs)

    def generate_unsubscribe_token(self):
        return hashlib.sha256(f"{self.email}_{datetime.now().isoformat()}".encode()).hexdigest()[:32]

    def __str__(self):
        return self.email

class Newsletter(models.Model):
    titre = models.CharField(max_length=200)
    objet = models.CharField(max_length=200)
    contenu_html = models.TextField()
    contenu_text = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_envoi = models.DateTimeField(null=True, blank=True)
    date_envoi_planifie = models.DateTimeField(null=True, blank=True)
    statut = models.CharField(
        max_length=20,
        choices=[
            ('brouillon', 'Brouillon'),
            ('planifie', 'Planifié'),
            ('en_cours', 'En cours d\'envoi'),
            ('envoye', 'Envoyé'),
            ('envoye_partiel', 'Envoyé partiellement'),
            ('erreur', 'Erreur')
        ],
        default='brouillon'
    )
    police = models.CharField(max_length=50, default='Arial')
    couleur_texte = models.CharField(max_length=7, default='#000000')
    ajouter_signature = models.BooleanField(default=False)
    ajouter_social = models.BooleanField(default=False)
    destinataires_cc = models.TextField(blank=True, null=True)
    destinataires_cci = models.TextField(blank=True, null=True)
    destinataires_planifies = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.titre

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Newsletter'
        verbose_name_plural = 'Newsletters'

class Envoi(models.Model):
    newsletter = models.ForeignKey(Newsletter, on_delete=models.CASCADE)
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE)
    date_envoi = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20)
    log = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('newsletter', 'subscriber')

    def __str__(self):
        return f"Envoi de {self.newsletter.titre} à {self.subscriber.email}" 