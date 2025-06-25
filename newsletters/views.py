from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import EmailMessage, send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import Newsletter, Subscriber, Envoi
from .forms import NewsletterForm, SubscriberForm, ImportSubscribersForm, CustomLoginForm
import pandas as pd
import json
from datetime import datetime
import re
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.http import HttpResponse
import csv
from django.contrib.auth.views import LoginView
import hashlib
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import logout
from new import NewsletterManager
import threading
import time
import os

logger = logging.getLogger(__name__)
newsletter_manager = NewsletterManager()

def home(request):
    return render(request, 'newsletters/home.html')

@login_required
def newsletter_list(request):
    """Vue pour lister les newsletters"""
    newsletters = Newsletter.objects.all().order_by('-date_creation')
    return render(request, 'newsletters/newsletter_list.html', {
        'newsletters': newsletters
    })

def convert_text_to_html(text):
    """Convertit le texte en HTML"""
    if not text:
        return ""
    
    # Remplacer les sauts de ligne par des paragraphes
    paragraphs = text.split('\n\n')
    html_content = []
    
    for paragraph in paragraphs:
        if paragraph.strip():
            # Convertir les liens
            paragraph = re.sub(
                r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
                r'<a href="\g<0>">\g<0></a>',
                paragraph
            )
            # Convertir le texte en gras
            paragraph = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', paragraph)
            # Convertir le texte en italique
            paragraph = re.sub(r'\*(.*?)\*', r'<em>\1</em>', paragraph)
            html_content.append(f'<p>{paragraph}</p>')
    
    return '\n'.join(html_content)

@login_required
def newsletter_create(request):
    """Vue pour créer une nouvelle newsletter"""
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            titre = request.POST.get('titre')
            objet = request.POST.get('objet')
            contenu_html = request.POST.get('contenu_html')
            contenu_text = request.POST.get('contenu_text')
            police = request.POST.get('police', 'Arial')
            couleur_texte = request.POST.get('couleur_texte', '#000000')
            ajouter_signature = request.POST.get('ajouter_signature') == 'on'
            ajouter_social = request.POST.get('ajouter_social') == 'on'

            # Créer la newsletter
            newsletter = Newsletter.objects.create(
                titre=titre,
                objet=objet,
                contenu_html=contenu_html,
                contenu_text=contenu_text,
                police=police,
                couleur_texte=couleur_texte,
                ajouter_signature=ajouter_signature,
                ajouter_social=ajouter_social
            )

            messages.success(request, 'Newsletter créée avec succès')
            return redirect('newsletter_detail', pk=newsletter.pk)
        except Exception as e:
            messages.error(request, f'Erreur lors de la création de la newsletter: {str(e)}')
            return redirect('newsletter_create')

    return render(request, 'newsletters/newsletter_form.html')

@login_required
def newsletter_detail(request, pk):
    """Vue pour voir les détails d'une newsletter"""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    return render(request, 'newsletters/newsletter_detail.html', {
        'newsletter': newsletter
    })

def check_scheduled_newsletters():
    """Vérifie périodiquement les newsletters planifiées"""
    while True:
        try:
            current_time = timezone.now()
            logger.info(f"[PLANIF] Vérification à {current_time}")
            newsletters = Newsletter.objects.filter(
                statut='planifie',
                date_envoi_planifie__lte=current_time
            )
            logger.info(f"[PLANIF] Newsletters à traiter : {[n.pk for n in newsletters]}")
            for newsletter in newsletters:
                logger.info(f"[PLANIF] Newsletter {newsletter.pk} - statut: {newsletter.statut}, date_envoi_planifie: {newsletter.date_envoi_planifie}")
                # Sécurité : ne pas envoyer si la date planifiée est dans le futur
                if newsletter.date_envoi_planifie and newsletter.date_envoi_planifie > timezone.now():
                    logger.info(f"[PLANIF] Newsletter {newsletter.pk} planifiée pour le futur ({newsletter.date_envoi_planifie}), on attend.")
                    continue
                logger.info(f"[PLANIF] Envoi de la newsletter planifiée {newsletter.pk}")
                try:
                    # Récupérer la liste des destinataires planifiés (avec log et conversion sécurisée)
                    if newsletter.destinataires_planifies:
                        logger.info(f"[PLANIF] Destinataires planifiés pour la newsletter {newsletter.pk}: {newsletter.destinataires_planifies}")
                        destinataires_ids = json.loads(newsletter.destinataires_planifies)
                        destinataires_ids = [int(i) for i in destinataires_ids if str(i).isdigit()]
                        if destinataires_ids:
                            abonnes = Subscriber.objects.filter(id__in=destinataires_ids, statut='actif')
                        else:
                            abonnes = Subscriber.objects.none()
                    else:
                        abonnes = Subscriber.objects.none()
                    logger.info(f"[PLANIF] Nombre d'abonnés à envoyer : {abonnes.count()}")
                    if not abonnes.exists():
                        logger.warning(f"[PLANIF] Aucun abonné actif pour la newsletter {newsletter.pk}")
                        continue
                    
                    # Configuration SMTP
                    try:
                        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                        server.starttls()
                        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                        logger.info("Connexion SMTP réussie")
                    except Exception as e:
                        logger.error(f"Erreur de connexion SMTP: {e}")
                        newsletter.statut = 'erreur'
                        newsletter.save()
                        continue
                    
                    sent_count = 0
                    error_count = 0
                    
                    # Adresse par défaut en CCI
                    default_bcc = settings.DEFAULT_BCC_EMAIL if hasattr(settings, 'DEFAULT_BCC_EMAIL') else None
                    
                    # Liste des destinataires en CCI
                    bcc_list = [abonne.email for abonne in abonnes]
                    if default_bcc:
                        bcc_list.append(default_bcc)
                    
                    # Construire l'URL absolue du logo pour les envois planifiés
                    # Nous devons construire la base_url manuellement car il n'y a pas de request
                    # Idéalement, settings.SITE_URL devrait être configuré pour la prod
                    base_url = f"http://{settings.ALLOWED_HOSTS[0]}" if settings.ALLOWED_HOSTS else 'http://localhost:8000'
                    logo_relative_path = os.path.join(settings.STATIC_URL, 'images/logo.png')
                    logo_absolute_url = f"{base_url}{logo_relative_path}"

                    # Remplacer le placeholder du logo dans le contenu HTML de la newsletter
                    final_html_content = newsletter.contenu_html.replace(
                        '{%' + ' static "images/logo.png" %}',
                        logo_absolute_url
                    )

                    # --- Correction : envoi individuel à chaque abonné sélectionné avec gestion de l'unicité ---
                    for abonne in abonnes:
                        try:
                            envoi, created = Envoi.objects.get_or_create(
                                newsletter=newsletter,
                                subscriber=abonne,
                                defaults={'statut': 'en_cours'}
                            )
                            if not created and envoi.statut == 'envoye':
                                logger.info(f"Envoi déjà existant pour {abonne.email}, on saute.")
                                continue
                            try:
                                logger.info(f"Tentative d'envoi de la newsletter {newsletter.pk} à {abonne.email}")
                                send_newsletter_email(newsletter, abonne)
                                envoi.statut = 'envoye'
                                envoi.log = 'Envoyé avec succès'
                                envoi.save()
                                sent_count += 1
                                logger.info(f"Email envoyé avec succès à {abonne.email}")
                            except Exception as e:
                                error_count += 1
                                logger.error(f"Erreur lors de l'envoi à {abonne.email}: {e}")
                                envoi.statut = 'erreur'
                                envoi.log = str(e)
                                envoi.save()
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Erreur lors de l'envoi en masse: {str(e)}")
                    
                    # Mettre à jour le statut de la newsletter
                    if error_count > 0:
                        if sent_count == 0:
                            newsletter.statut = 'erreur'
                        else:
                            newsletter.statut = 'envoye_partiel'
                    else:
                        newsletter.statut = 'envoye'
                    
                    newsletter.date_envoi = current_time
                    newsletter.save()
                    
                    logger.info(f"Newsletter {newsletter.pk} envoyée : {sent_count} succès, {error_count} erreurs")
                    
                except Exception as e:
                    logger.error(f"Erreur lors de l'envoi de la newsletter {newsletter.pk}: {str(e)}")
                    newsletter.statut = 'erreur'
                    newsletter.save()
            
        except Exception as e:
            logger.error(f"Erreur dans le thread de vérification : {str(e)}")
        
        # Attendre 30 secondes avant la prochaine vérification
        time.sleep(30)

# Démarrer le thread de vérification au démarrage de l'application
check_thread = threading.Thread(target=check_scheduled_newsletters, daemon=True)
check_thread.start()

@login_required
def newsletter_send(request, pk):
    """Vue pour envoyer une newsletter"""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    
    # Récupérer tous les abonnés actifs
    abonnes = Subscriber.objects.filter(statut='actif').order_by('email')
    
    if request.method == 'POST':
        try:
            logger.info(f"Début de l'envoi de la newsletter {pk}")
            
            # Vérifier si c'est une planification
            if request.POST.get('planifier'):
                date_envoi = request.POST.get('date_envoi')
                destinataires = request.POST.getlist('destinataires')
                if date_envoi:
                    try:
                        date_envoi = datetime.strptime(date_envoi, '%Y-%m-%dT%H:%M')
                        date_envoi = timezone.make_aware(date_envoi)
                        newsletter.date_envoi_planifie = date_envoi
                        newsletter.statut = 'planifie'
                        if 'tous' in destinataires:
                            destinataires_ids = list(Subscriber.objects.filter(statut='actif').values_list('id', flat=True))
                        else:
                            destinataires_ids = [int(i) for i in destinataires if str(i).isdigit()]
                        newsletter.destinataires_planifies = json.dumps(destinataires_ids)
                        newsletter.save()
                        messages.success(request, f'Newsletter planifiée pour le {date_envoi.strftime("%d/%m/%Y à %H:%M")}')
                        return redirect('newsletter_detail', pk=newsletter.pk)
                    except ValueError:
                        messages.error(request, 'Format de date invalide')
                else:
                    messages.error(request, 'Date d\'envoi requise')
            else:
                # Envoi immédiat INDIVIDUEL à chaque abonné sélectionné
                logger.info("Début de l'envoi immédiat individuel")
                
                # Récupérer les destinataires sélectionnés
                destinataires = request.POST.getlist('destinataires')
                if not destinataires:
                    messages.error(request, 'Veuillez sélectionner au moins un destinataire')
                    return render(request, 'newsletters/newsletter_send.html', {
                        'newsletter': newsletter,
                        'abonnes': abonnes
                    })
                
                # Récupérer les abonnés sélectionnés
                if 'tous' in destinataires:
                    abonnes_a_envoyer = abonnes
                else:
                    abonnes_a_envoyer = Subscriber.objects.filter(id__in=destinataires, statut='actif')
                
                logger.info(f"Nombre d'abonnés sélectionnés : {abonnes_a_envoyer.count()}")
                
                if not abonnes_a_envoyer.exists():
                    messages.error(request, 'Aucun abonné actif sélectionné')
                    return render(request, 'newsletters/newsletter_send.html', {
                        'newsletter': newsletter,
                        'abonnes': abonnes
                    })

                # Supprimer les anciens envois en attente ou en erreur
                Envoi.objects.filter(newsletter=newsletter, statut__in=['en_attente', 'erreur']).delete()
                logger.info("Anciens envois supprimés")
                
                # Créer les entrées d'envoi pour chaque abonné
                for abonne in abonnes_a_envoyer:
                    envoi, created = Envoi.objects.get_or_create(
                        newsletter=newsletter,
                        subscriber=abonne,
                        defaults={'statut': 'en_attente'}
                    )
                    if not created:
                        # Optionnel : tu peux mettre à jour le statut si besoin
                        if envoi.statut != 'en_attente':
                            envoi.statut = 'en_attente'
                            envoi.save()
                logger.info("Nouvelles entrées d'envoi créées")
                
                # Mettre à jour le statut de la newsletter
                newsletter.statut = 'en_cours'
                newsletter.save()
                logger.info("Statut de la newsletter mis à jour en 'en_cours'")

                # Configuration SMTP
                try:
                    logger.info("Tentative de connexion au serveur SMTP")
                    server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                    server.starttls()
                    server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                    logger.info("Connexion SMTP réussie")
                except Exception as e:
                    logger.error(f"Erreur de connexion SMTP: {e}")
                    messages.error(request, "Erreur de connexion au serveur mail")
                    newsletter.statut = 'erreur'
                    newsletter.save()
                    return redirect('newsletter_detail', pk=newsletter.pk)

                sent_count = 0
                error_count = 0

                # Construire l'URL absolue du logo pour l'envoi immédiat
                base_url = request.build_absolute_uri('/')[:-1]  # enlève le slash final
                logo_relative_path = os.path.join(settings.STATIC_URL, 'images/logo.png')
                logo_absolute_url = f"{base_url}{logo_relative_path}"
                final_html_content = newsletter.contenu_html.replace(
                    '{%' + ' static "images/logo.png" %}',
                    logo_absolute_url
                )

                # --- Correction : envoi individuel à chaque abonné sélectionné avec gestion de l'unicité ---
                try:
                    for abonne in abonnes_a_envoyer:
                        envoi, created = Envoi.objects.get_or_create(
                            newsletter=newsletter,
                            subscriber=abonne,
                            defaults={'statut': 'en_cours'}
                        )
                        if not created and envoi.statut == 'envoye':
                            logger.info(f"Envoi déjà existant pour {abonne.email}, on saute.")
                            continue
                        try:
                            msg = MIMEMultipart('alternative')
                            msg['Subject'] = newsletter.objet
                            msg['From'] = f"{settings.EMAIL_HOST_USER}"
                            msg['To'] = abonne.email

                            part1 = MIMEText(newsletter.contenu_text, 'plain', 'utf-8')
                            part2 = MIMEText(final_html_content, 'html', 'utf-8')
                            msg.attach(part1)
                            msg.attach(part2)

                            server.send_message(msg)

                            envoi.statut = 'envoye'
                            envoi.log = 'Envoyé avec succès'
                            envoi.save()
                            sent_count += 1
                            logger.info(f"Email envoyé avec succès à {abonne.email}")
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Erreur lors de l'envoi à {abonne.email}: {str(e)}")
                            envoi.statut = 'erreur'
                            envoi.log = str(e)
                            envoi.save()
                except Exception as e:
                    logger.error(f"Erreur lors de l'envoi individuel: {str(e)}")
                    error_count = len(abonnes_a_envoyer)
                    for envoi in Envoi.objects.filter(newsletter=newsletter, statut='en_attente'):
                        envoi.statut = 'erreur'
                        envoi.log = str(e)
                        envoi.save()

                try:
                    server.quit()
                except:
                    pass
                
                # Mettre à jour le statut final de la newsletter
                logger.info(f"Résumé de l'envoi : {sent_count} envoyés, {error_count} erreurs")
                if error_count > 0:
                    if sent_count == 0:
                        newsletter.statut = 'erreur'
                        logger.info("Statut mis à jour en 'erreur' (aucun envoi réussi)")
                    else:
                        newsletter.statut = 'envoye_partiel'
                        logger.info("Statut mis à jour en 'envoye_partiel'")
                else:
                    newsletter.statut = 'envoye'
                    logger.info("Statut mis à jour en 'envoye'")
                newsletter.save()
                
                if error_count > 0:
                    messages.warning(request, f'Newsletter envoyée avec {error_count} erreurs ({sent_count} emails envoyés)')
                else:
                    messages.success(request, f'Newsletter envoyée avec succès ({sent_count} emails envoyés)')
            
            return redirect('newsletter_detail', pk=newsletter.pk)
            
        except Exception as e:
            logger.error(f"Erreur générale lors de l'envoi : {str(e)}")
            messages.error(request, f'Erreur lors de l\'envoi : {str(e)}')
            newsletter.statut = 'erreur'
            newsletter.save()
            return redirect('newsletter_detail', pk=newsletter.pk)
    
    return render(request, 'newsletters/newsletter_send.html', {
        'newsletter': newsletter,
        'abonnes': abonnes
    })

@login_required
def newsletter_edit(request, pk):
    """Vue pour modifier une newsletter existante"""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            newsletter.titre = request.POST.get('titre')
            newsletter.objet = request.POST.get('objet')
            newsletter.contenu_html = request.POST.get('contenu_html')
            newsletter.contenu_text = request.POST.get('contenu_text')
            newsletter.police = request.POST.get('police', 'Arial')
            newsletter.couleur_texte = request.POST.get('couleur_texte', '#000000')
            newsletter.ajouter_signature = request.POST.get('ajouter_signature') == 'on'
            newsletter.ajouter_social = request.POST.get('ajouter_social') == 'on'
            
            # Sauvegarder les modifications
            newsletter.save()
            
            messages.success(request, 'Newsletter modifiée avec succès')
            return redirect('newsletter_detail', pk=newsletter.pk)
        except Exception as e:
            messages.error(request, f'Erreur lors de la modification de la newsletter: {str(e)}')
            return render(request, 'newsletters/newsletter_form.html', {
                'newsletter': newsletter
            })
    
    # Passer la newsletter existante au template
    return render(request, 'newsletters/newsletter_form.html', {
        'newsletter': newsletter
    })

@login_required
def newsletter_delete(request, pk):
    """Vue pour supprimer une newsletter"""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    if request.method == 'POST':
        try:
            newsletter.delete()
            messages.success(request, 'Newsletter supprimée avec succès')
            return redirect('newsletter_list')
        except Exception as e:
            logger.error(f"Erreur lors de la suppression : {str(e)}")
            messages.error(request, f'Erreur lors de la suppression : {str(e)}')
            return redirect('newsletter_detail', pk=newsletter.pk)
    return render(request, 'newsletters/newsletter_confirm_delete.html', {
        'newsletter': newsletter
    })

@login_required
def subscriber_list(request):
    """Vue pour lister les abonnés"""
    subscribers = Subscriber.objects.all().order_by('-date_inscription')
    return render(request, 'newsletters/subscriber_list.html', {
        'subscribers': subscribers
    })

@login_required
def subscriber_delete(request, subscriber_id):
    """Vue pour supprimer un abonné"""
    subscriber = get_object_or_404(Subscriber, pk=subscriber_id)
    if request.method == 'POST':
        subscriber.delete()
        messages.success(request, 'Abonné supprimé avec succès')
        return redirect('subscriber_list')
    return render(request, 'newsletters/subscriber_confirm_delete.html', {
        'subscriber': subscriber
    })

@login_required
def subscriber_export(request):
    """Vue pour exporter la liste des abonnés en CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="abonnes.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Email', 'Nom', 'Prénom', 'Date d\'inscription', 'Statut'])
    
    subscribers = Subscriber.objects.all().order_by('-date_inscription')
    for subscriber in subscribers:
        writer.writerow([
            subscriber.email,
            subscriber.nom or '',
            subscriber.prenom or '',
            subscriber.date_inscription.strftime('%d/%m/%Y %H:%M'),
            subscriber.statut
        ])
    
    return response

@login_required
def newsletter_duplicate(request, newsletter_id):
    """Vue pour dupliquer une newsletter"""
    original = get_object_or_404(Newsletter, id=newsletter_id)
    
    if request.method == 'POST':
        try:
            # Créer une copie de la newsletter
            new_newsletter = Newsletter.objects.create(
                titre=f"Copie de {original.titre}",
                objet=original.objet,
                contenu_html=original.contenu_html,
                contenu_text=original.contenu_text,
                police=original.police,
                destinataires_cc=original.destinataires_cc,
                destinataires_cci=original.destinataires_cci,
                statut='brouillon'
            )
            messages.success(request, 'Newsletter dupliquée avec succès')
            return redirect('newsletter_edit', newsletter_id=new_newsletter.id)
        except Exception as e:
            messages.error(request, f'Erreur lors de la duplication : {str(e)}')
    
    return redirect('newsletter_list')

@login_required
def newsletter_preview(request, newsletter_id):
    """Vue pour prévisualiser une newsletter"""
    newsletter = get_object_or_404(Newsletter, id=newsletter_id)
    return render(request, 'newsletters/preview.html', {
        'newsletter': newsletter
    })

@login_required
def subscriber_create(request):
    """Vue pour créer un abonné"""
    if request.method == 'POST':
        form = SubscriberForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Abonné créé avec succès')
            return redirect('subscriber_list')
    else:
        form = SubscriberForm()
    
    return render(request, 'newsletters/subscriber_form.html', {
        'form': form,
        'title': 'Nouvel abonné'
    })

@login_required
def subscriber_import(request):
    """Vue pour importer des abonnés depuis un fichier CSV ou Excel"""
    if request.method == 'POST':
        form = ImportSubscribersForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                file = request.FILES['file']
                email_column = form.cleaned_data['email_column']
                nom_column = form.cleaned_data['nom_column']
                prenom_column = form.cleaned_data['prenom_column']

                # Détecter le type de fichier
                filename = file.name.lower()
                if filename.endswith('.csv'):
                    # Essayer différents encodages
                    encodings = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252', 'iso-8859-1', 'windows-1252']
                    df = None
                    used_encoding = None
                    for encoding in encodings:
                        try:
                            file.seek(0)
                            df = pd.read_csv(file, encoding=encoding)
                            used_encoding = encoding
                            break
                        except UnicodeDecodeError:
                            continue
                        except Exception as e:
                            logger.error(f"Erreur avec l'encodage {encoding}: {str(e)}")
                            continue
                    if df is None:
                        messages.error(request, "Impossible de lire le fichier CSV. Veuillez vérifier l'encodage et le format du fichier.")
                        return redirect('subscriber_import')
                    logger.info(f"Fichier CSV lu avec succès en utilisant l'encodage: {used_encoding}")
                elif filename.endswith('.xls') or filename.endswith('.xlsx'):
                    try:
                        file.seek(0)
                        df = pd.read_excel(file)
                        logger.info("Fichier Excel lu avec succès")
                    except Exception as e:
                        logger.error(f"Erreur lors de la lecture du fichier Excel: {str(e)}")
                        messages.error(request, "Impossible de lire le fichier Excel. Veuillez vérifier le format du fichier.")
                        return redirect('subscriber_import')
                else:
                    messages.error(request, "Le fichier doit être au format CSV (.csv), XLS (.xls) ou XLSX (.xlsx).")
                    return redirect('subscriber_import')

                # Vérifier que la colonne email existe
                if email_column not in df.columns:
                    messages.error(request, f"La colonne '{email_column}' n'existe pas dans le fichier. Colonnes disponibles: {', '.join(df.columns)}")
                    return redirect('subscriber_import')

                # Importer les abonnés
                imported = 0
                errors = 0
                for index, row in df.iterrows():
                    try:
                        email = str(row[email_column]).strip().lower()
                        if not email or pd.isna(email):
                            logger.warning(f"Ligne {index + 2}: Email vide ou invalide")
                            errors += 1
                            continue
                        nom = str(row[nom_column]) if nom_column and nom_column in row and pd.notna(row[nom_column]) else None
                        prenom = str(row[prenom_column]) if prenom_column and prenom_column in row and pd.notna(row[prenom_column]) else None
                        token = hashlib.sha256(f"{email}_{datetime.now().isoformat()}".encode()).hexdigest()[:32]
                        subscriber, created = Subscriber.objects.get_or_create(
                            email=email,
                            defaults={
                                'nom': nom,
                                'prenom': prenom,
                                'token_desabonnement': token,
                                'statut': 'actif'
                            }
                        )
                        if created:
                            imported += 1
                            logger.info(f"Abonné importé: {email}")
                        else:
                            logger.info(f"Abonné déjà existant: {email}")
                    except Exception as e:
                        errors += 1
                        logger.error(f"Erreur lors de l'import de la ligne {index + 2}: {str(e)}")
                messages.success(request, f'Import terminé : {imported} nouveaux abonnés, {errors} erreurs')
                return redirect('subscriber_list')
            except Exception as e:
                logger.error(f"Erreur lors de l'import : {str(e)}")
                messages.error(request, f'Erreur lors de l\'import : {str(e)}')
    else:
        form = ImportSubscribersForm()
    return render(request, 'newsletters/subscriber_import.html', {
        'form': form
    })

def unsubscribe(request, token):
    """Vue pour se désabonner"""
    subscriber = get_object_or_404(Subscriber, token_desabonnement=token)
    subscriber.statut = 'desabonne'
    subscriber.save()
    return render(request, 'newsletters/unsubscribe_success.html')

class CustomLoginView(LoginView):
    form_class = CustomLoginForm
    template_name = 'registration/login.html'

@login_required
def subscriber_edit(request, pk):
    """Vue pour modifier un abonné"""
    subscriber = get_object_or_404(Subscriber, pk=pk)
    if request.method == 'POST':
        form = SubscriberForm(request.POST, instance=subscriber)
        if form.is_valid():
            form.save()
            messages.success(request, 'Abonné modifié avec succès')
            return redirect('subscriber_list')
    else:
        form = SubscriberForm(instance=subscriber)
    
    return render(request, 'newsletters/subscriber_edit.html', {
        'form': form,
        'subscriber': subscriber
    })

@login_required
def logout_view(request):
    """Vue pour la déconnexion"""
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'Vous avez été déconnecté avec succès.')
        return redirect('login')
    return redirect('home')

def check_scheduled_newsletters_standalone():
    """Vérifie et envoie les newsletters planifiées"""
    try:
        current_time = timezone.now()
        logger.info(f"Vérification des newsletters planifiées pour {current_time}")
        
        # Récupérer les newsletters planifiées pour maintenant
        newsletters = Newsletter.objects.filter(
            statut='planifie',
            date_envoi_planifie__lte=current_time,
            date_envoi_planifie__isnull=False  # S'assurer qu'une date est définie
        )
        
        for newsletter in newsletters:
            # Sécurité : ne pas envoyer si la date planifiée est dans le futur
            if newsletter.date_envoi_planifie and newsletter.date_envoi_planifie > timezone.now():
                logger.info(f"Newsletter {newsletter.id} planifiée pour le futur ({newsletter.date_envoi_planifie}), on attend.")
                continue
            
            try:
                logger.info(f"Traitement de la newsletter planifiée {newsletter.id} pour {newsletter.date_envoi_planifie}")
                
                # Vérifier si la newsletter a déjà été envoyée
                if Envoi.objects.filter(newsletter=newsletter).exists():
                    logger.info(f"La newsletter {newsletter.id} a déjà été envoyée")
                    newsletter.statut = 'envoye'
                    newsletter.save()
                    continue
                
                # Récupérer la liste des destinataires planifiés (avec log et conversion sécurisée)
                if newsletter.destinataires_planifies:
                    logger.info(f"Destinataires planifiés pour la newsletter {newsletter.id}: {newsletter.destinataires_planifies}")
                    destinataires_ids = json.loads(newsletter.destinataires_planifies)
                    destinataires_ids = [int(i) for i in destinataires_ids if str(i).isdigit()]
                    if destinataires_ids:
                        abonnes = Subscriber.objects.filter(id__in=destinataires_ids, statut='actif')
                    else:
                        abonnes = Subscriber.objects.none()
                else:
                    abonnes = Subscriber.objects.none()
                if not abonnes.exists():
                    logger.warning(f"Aucun abonné actif pour la newsletter {newsletter.id}")
                    continue
                
                # --- Correction : envoi individuel à chaque abonné sélectionné avec gestion de l'unicité ---
                for abonne in abonnes:
                    try:
                        envoi, created = Envoi.objects.get_or_create(
                            newsletter=newsletter,
                            subscriber=abonne,
                            defaults={'statut': 'en_cours'}
                        )
                        if not created and envoi.statut == 'envoye':
                            logger.info(f"Envoi déjà existant pour {abonne.email}, on saute.")
                            continue
                        try:
                            logger.info(f"Tentative d'envoi de la newsletter {newsletter.id} à {abonne.email}")
                            send_newsletter_email(newsletter, abonne)
                            envoi.statut = 'envoye'
                            envoi.log = 'Envoyé avec succès'
                            envoi.save()
                            logger.info(f"Email envoyé avec succès à {abonne.email}")
                        except Exception as e:
                            logger.error(f"Erreur lors de l'envoi à {abonne.email}: {e}")
                            envoi.statut = 'erreur'
                            envoi.log = str(e)
                            envoi.save()
                    except Exception as e:
                        error_count = len(abonnes)
                        logger.error(f"Erreur lors de l'envoi en masse: {str(e)}")
                # Marquer la newsletter comme envoyée
                newsletter.statut = 'envoye'
                newsletter.save()
                
            except Exception as e:
                logger.error(f"Erreur lors du traitement de la newsletter {newsletter.id}: {e}")
                
    except Exception as e:
        logger.error(f"Erreur lors de la vérification des newsletters planifiées: {e}")

def send_newsletter_email(newsletter, subscriber):
    """Envoie un email de newsletter à un abonné"""
    try:
        # Configuration de l'email
        subject = newsletter.objet
        from_email = settings.EMAIL_HOST_USER
        to_email = subscriber.email
        
        # Création du message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        
        # Ajout du contenu HTML
        html_content = newsletter.contenu_html
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Ajout du contenu texte
        text_content = newsletter.contenu_text
        text_part = MIMEText(text_content, 'plain')
        msg.attach(text_part)
        
        # Connexion au serveur SMTP
        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
        server.starttls()
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        
        # Envoi de l'email
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email envoyé avec succès à {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email: {e}")
        raise

def planifier_envoi(request, newsletter_id):
    """Planifie l'envoi d'une newsletter"""
    try:
        newsletter = get_object_or_404(Newsletter, id=newsletter_id)
        
        # Vérifier si la newsletter est déjà envoyée
        if newsletter.statut == 'envoye':
            messages.error(request, "Cette newsletter a déjà été envoyée.")
            return redirect('newsletter_list')
        
        # Vérifier si la newsletter est déjà planifiée
        if newsletter.statut == 'planifie':
            messages.error(request, "Cette newsletter est déjà planifiée.")
            return redirect('newsletter_list')
        
        # Récupérer la date de planification
        date_envoi = request.POST.get('date_envoi')
        if not date_envoi:
            messages.error(request, "Veuillez spécifier une date d'envoi.")
            return redirect('newsletter_list')
        
        # Convertir la date
        try:
            date_envoi = datetime.strptime(date_envoi, '%Y-%m-%d %H:%M')
            date_envoi = timezone.make_aware(date_envoi)
        except ValueError:
            messages.error(request, "Format de date invalide.")
            return redirect('newsletter_list')
        
        # Vérifier que la date est dans le futur
        if date_envoi <= timezone.now():
            messages.error(request, "La date d'envoi doit être dans le futur.")
            return redirect('newsletter_list')
        
        # Planifier l'envoi
        newsletter.date_envoi_planifie = date_envoi
        newsletter.statut = 'planifie'
        newsletter.save()
        
        messages.success(request, f"Newsletter planifiée pour le {date_envoi.strftime('%d/%m/%Y à %H:%M')}")
        return redirect('newsletter_detail', pk=newsletter.pk)
        
    except Exception as e:
        messages.error(request, f"Erreur lors de la planification: {str(e)}")
    
    return redirect('newsletter_list') 