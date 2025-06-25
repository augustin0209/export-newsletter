import sqlite3
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from datetime import datetime
import logging
import json
from typing import List, Dict, Optional
import hashlib
import threading
import time

def adapt_datetime(dt):
    return dt.isoformat()

def convert_datetime(s):
    try:
        return datetime.fromisoformat(s.decode())
    except:
        return None

class NewsletterManager:
    def __init__(self, db_path: str = "newsletter.db", config_file: str = "config.json", service_mode: bool = False):
        self.db_path = db_path
        self.config_file = config_file
        self.setup_logging()
        self.setup_database()
        self.load_config()
        # Ne démarrer le thread que si on n'est pas en mode service
        if not service_mode:
            self.check_thread = threading.Thread(target=self._check_scheduled_newsletters, daemon=True)
            self.check_thread.start()
    
    def setup_logging(self):
        """Configuration des logs"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('newsletter.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_database(self):
        """Initialise la base de données"""
        conn = sqlite3.connect(self.db_path)
        # Enregistrer les adaptateurs pour les dates
        sqlite3.register_adapter(datetime, adapt_datetime)
        sqlite3.register_converter("TIMESTAMP", convert_datetime)
        cursor = conn.cursor()
        
        # Table des abonnés
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                nom TEXT,
                prenom TEXT,
                date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                statut TEXT DEFAULT 'actif',
                token_desabonnement TEXT UNIQUE
            )
        ''')
        
        # Table des newsletters
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS newsletters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL,
                objet TEXT NOT NULL,
                contenu_html TEXT,
                contenu_text TEXT,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_envoi TIMESTAMP,
                date_envoi_planifie TIMESTAMP,
                statut TEXT DEFAULT 'brouillon',
                police TEXT DEFAULT 'Arial',
                destinataires_cc TEXT,
                destinataires_cci TEXT
            )
        ''')
        
        # Table des envois
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS envois (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                newsletter_id INTEGER,
                subscriber_id INTEGER,
                date_envoi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                statut TEXT,
                FOREIGN KEY (newsletter_id) REFERENCES newsletters (id),
                FOREIGN KEY (subscriber_id) REFERENCES subscribers (id)
            )
        ''')
        
        # Mettre à jour la structure de la base de données si nécessaire
        self._update_database_structure(cursor)
        
        conn.commit()
        conn.close()
        self.logger.info("Base de données initialisée")
    
    def _update_database_structure(self, cursor):
        """Met à jour la structure de la base de données si nécessaire"""
        try:
            # Vérifier si la table newsletters existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='newsletters'")
            if cursor.fetchone():
                # Liste des colonnes à ajouter avec leurs valeurs par défaut
                columns_to_add = [
                    ('objet', 'TEXT', 'titre'),
                    ('date_envoi_planifie', 'TIMESTAMP', 'NULL'),
                    ('police', 'TEXT', "'Arial'"),
                    ('destinataires_cc', 'TEXT', 'NULL'),
                    ('destinataires_cci', 'TEXT', 'NULL')
                ]
                
                # Récupérer les colonnes existantes
                cursor.execute("PRAGMA table_info(newsletters)")
                existing_columns = [column[1] for column in cursor.fetchall()]
                
                # Ajouter les nouvelles colonnes si elles n'existent pas
                for column_name, column_type, default_value in columns_to_add:
                    if column_name not in existing_columns:
                        self.logger.info(f"Ajout de la colonne {column_name} à la table newsletters")
                        cursor.execute(f'''
                            ALTER TABLE newsletters 
                            ADD COLUMN {column_name} {column_type} 
                            DEFAULT {default_value}
                        ''')
            
            self.logger.info("Structure de la base de données mise à jour avec succès")
        except Exception as e:
            self.logger.error(f"Erreur lors de la mise à jour de la structure: {e}")
            raise
    
    def load_config(self):
        """Charge la configuration email"""
        default_config = {
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "email_sender": "votre_email@gmail.com",
            "email_password": "votre_mot_de_passe_app",
            "sender_name": "Votre Newsletter",
            "provider": "gmail"  # gmail, outlook, custom
        }
        
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            # Debug: afficher la config chargée (sans mot de passe)
            debug_config = self.config.copy()
            debug_config['email_password'] = '***masqué***'
            self.logger.info(f"Configuration chargée: {debug_config}")
        else:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            self.config = default_config
            self.logger.warning(f"Fichier de configuration créé: {self.config_file}. Veuillez le modifier avec vos paramètres SMTP.")
    
    def generate_unsubscribe_token(self, email: str) -> str:
        """Génère un token unique pour le désabonnement"""
        return hashlib.sha256(f"{email}_{datetime.now().isoformat()}".encode()).hexdigest()[:32]
    
    def import_subscribers_from_excel(self, file_path: str, email_column: str = "email", 
                                    nom_column: str = None, prenom_column: str = None):
        """Importe les abonnés depuis un fichier Excel"""
        try:
            df = pd.read_excel(file_path)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            imported = 0
            errors = 0
            
            for _, row in df.iterrows():
                try:
                    email = row[email_column].strip().lower()
                    nom = row[nom_column] if nom_column and nom_column in row else None
                    prenom = row[prenom_column] if prenom_column and prenom_column in row else None
                    token = self.generate_unsubscribe_token(email)
                    
                    cursor.execute('''
                        INSERT OR IGNORE INTO subscribers (email, nom, prenom, token_desabonnement)
                        VALUES (?, ?, ?, ?)
                    ''', (email, nom, prenom, token))
                    
                    if cursor.rowcount > 0:
                        imported += 1
                    
                except Exception as e:
                    self.logger.error(f"Erreur lors de l'import de {row}: {e}")
                    errors += 1
            
            conn.commit()
            conn.close()
            self.logger.info(f"Import terminé: {imported} nouveaux abonnés, {errors} erreurs")
            return imported, errors
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'import Excel: {e}")
            return 0, 1
    
    def import_subscribers_from_csv(self, file_path: str, email_column: str = "email",
                                  nom_column: str = None, prenom_column: str = None):
        """Importe les abonnés depuis un fichier CSV"""
        try:
            df = pd.read_csv(file_path)
            return self._import_from_dataframe(df, email_column, nom_column, prenom_column)
        except Exception as e:
            self.logger.error(f"Erreur lors de l'import CSV: {e}")
            return 0, 1
    
    def _import_from_dataframe(self, df: pd.DataFrame, email_column: str,
                             nom_column: str = None, prenom_column: str = None):
        """Méthode helper pour importer depuis un DataFrame"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        imported = 0
        errors = 0
        
        for _, row in df.iterrows():
            try:
                email = str(row[email_column]).strip().lower()
                nom = str(row[nom_column]) if nom_column and nom_column in row and pd.notna(row[nom_column]) else None
                prenom = str(row[prenom_column]) if prenom_column and prenom_column in row and pd.notna(row[prenom_column]) else None
                token = self.generate_unsubscribe_token(email)
                
                cursor.execute('''
                    INSERT OR IGNORE INTO subscribers (email, nom, prenom, token_desabonnement)
                    VALUES (?, ?, ?, ?)
                ''', (email, nom, prenom, token))
                
                if cursor.rowcount > 0:
                    imported += 1
                
            except Exception as e:
                self.logger.error(f"Erreur lors de l'import de {row}: {e}")
                errors += 1
        
        conn.commit()
        conn.close()
        self.logger.info(f"Import terminé: {imported} nouveaux abonnés, {errors} erreurs")
        return imported, errors
    
    def add_subscriber(self, email: str, nom: str = None, prenom: str = None):
        """Ajoute un abonné manuellement"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            token = self.generate_unsubscribe_token(email)
            
            cursor.execute('''
                INSERT INTO subscribers (email, nom, prenom, token_desabonnement)
                VALUES (?, ?, ?, ?)
            ''', (email.strip().lower(), nom, prenom, token))
            
            conn.commit()
            conn.close()
            self.logger.info(f"Abonné ajouté: {email}")
            return True
        except sqlite3.IntegrityError:
            self.logger.warning(f"Email déjà existant: {email}")
            return False
        except Exception as e:
            self.logger.error(f"Erreur lors de l'ajout de {email}: {e}")
            return False
    
    def unsubscribe_by_token(self, token: str):
        """Désabonne un utilisateur via son token"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscribers 
                SET statut = 'desabonne' 
                WHERE token_desabonnement = ?
            ''', (token,))
            
            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                self.logger.info(f"Utilisateur désabonné avec le token: {token}")
                return True
            else:
                conn.close()
                return False
        except Exception as e:
            self.logger.error(f"Erreur lors du désabonnement: {e}")
            return False
    
    def unsubscribe_by_email(self, email: str):
        """Désabonne un utilisateur via son email"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscribers 
                SET statut = 'desabonne' 
                WHERE email = ?
            ''', (email.strip().lower(),))
            
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            
            if affected > 0:
                self.logger.info(f"Utilisateur désabonné: {email}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Erreur lors du désabonnement: {e}")
            return False
    
    def create_newsletter(self, titre: str, contenu_html: str, contenu_text: str = None, 
                         objet: str = None, police: str = "Arial", 
                         destinataires_cc: List[str] = None, 
                         date_envoi_planifie: datetime = None):
        """Crée une nouvelle newsletter avec les paramètres avancés"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Si pas d'objet spécifié, utiliser le titre
            if not objet:
                objet = titre
            
            # Convertir les listes en chaînes JSON
            cc_str = json.dumps(destinataires_cc) if destinataires_cc else None
            
            cursor.execute('''
                INSERT INTO newsletters (
                    titre, objet, contenu_html, contenu_text, 
                    police, destinataires_cc, date_envoi_planifie
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                titre, objet, contenu_html, contenu_text or "Version texte non disponible",
                police, cc_str, date_envoi_planifie
            ))
            
            newsletter_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            self.logger.info(f"Newsletter créée: {titre} (ID: {newsletter_id})")
            return newsletter_id
        except Exception as e:
            self.logger.error(f"Erreur lors de la création de la newsletter: {e}")
            return None
    
    def get_active_subscribers(self) -> List[Dict]:
        """Récupère la liste des abonnés actifs"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, email, nom, prenom, token_desabonnement
                FROM subscribers 
                WHERE statut = 'actif'
            ''')
            
            subscribers = []
            for row in cursor.fetchall():
                subscribers.append({
                    'id': row[0],
                    'email': row[1],
                    'nom': row[2],
                    'prenom': row[3],
                    'token': row[4]
                })
            
            conn.close()
            return subscribers
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des abonnés: {e}")
            return []
    
    def send_newsletter(self, newsletter_id: int, test_email: str = None):
        """Envoie la newsletter aux abonnés avec gestion avancée des destinataires"""
        try:
            # Récupérer la newsletter
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT titre, objet, contenu_html, contenu_text, police, destinataires_cc 
                FROM newsletters WHERE id = ?
            ''', (newsletter_id,))
            newsletter = cursor.fetchone()
            
            if not newsletter:
                self.logger.error(f"Newsletter {newsletter_id} non trouvée")
                return False
            
            titre, objet, contenu_html, contenu_text, police, destinataires_cc = newsletter
            
            # Convertir la chaîne JSON des CC en liste
            cc_list = json.loads(destinataires_cc) if destinataires_cc else []
            
            # Récupérer les abonnés (ou email de test)
            if test_email:
                subscribers = [{'email': test_email, 'nom': 'Test', 'prenom': 'User', 'token': 'test_token', 'id': 0}]
            else:
                subscribers = self.get_active_subscribers()
            
            if not subscribers:
                self.logger.warning("Aucun abonné actif trouvé")
                return False
            
            # Configuration SMTP
            try:
                server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
                server.starttls()
                server.login(self.config['email_sender'], self.config['email_password'])
            except Exception as e:
                self.logger.error(f"Erreur de connexion SMTP: {e}")
                return False
            
            sent_count = 0
            error_count = 0
            
            # Liste des destinataires en CCI
            bcc_emails = [sub['email'] for sub in subscribers]
            
            for subscriber in subscribers:
                try:
                    # Personnaliser le contenu
                    html_content = contenu_html
                    text_content = contenu_text
                    
                    # Ajouter le lien de désabonnement
                    unsubscribe_link = f"http://votre-site.com/unsubscribe?token={subscriber['token']}"
                    html_content += f'<br><br><small><a href="{unsubscribe_link}">Se désabonner</a></small>'
                    text_content += f'\n\nPour vous désabonner: {unsubscribe_link}'
                    
                    # Créer le message
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = objet
                    msg['From'] = f"{self.config['sender_name']} <{self.config['email_sender']}>"
                    
                    # Ajouter les destinataires en CC si présents
                    if cc_list:
                        msg['Cc'] = ', '.join(cc_list)
                    
                    # Ajouter les destinataires en CCI
                    msg['Bcc'] = ', '.join(bcc_emails)
                    
                    # Ajouter les versions texte et HTML avec la police spécifiée
                    html_content = f'<div style="font-family: {police}, sans-serif;">{html_content}</div>'
                    part1 = MIMEText(text_content, 'plain', 'utf-8')
                    part2 = MIMEText(html_content, 'html', 'utf-8')
                    
                    msg.attach(part1)
                    msg.attach(part2)
                    
                    # Envoyer
                    server.send_message(msg)
                    
                    # Enregistrer l'envoi
                    if not test_email:
                        cursor.execute('''
                            INSERT INTO envois (newsletter_id, subscriber_id, statut)
                            VALUES (?, ?, 'envoye')
                        ''', (newsletter_id, subscriber['id']))
                    
                    sent_count += 1
                    self.logger.info(f"Email envoyé à: {subscriber['email']}")
                    
                except Exception as e:
                    error_count += 1
                    self.logger.error(f"Erreur envoi pour {subscriber['email']}: {e}")
                    
                    if not test_email:
                        cursor.execute('''
                            INSERT INTO envois (newsletter_id, subscriber_id, statut)
                            VALUES (?, ?, 'erreur')
                        ''', (newsletter_id, subscriber['id']))
            
            server.quit()
            
            # Marquer la newsletter comme envoyée
            if not test_email:
                cursor.execute('''
                    UPDATE newsletters 
                    SET statut = 'envoye', date_envoi = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (newsletter_id,))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Envoi terminé: {sent_count} succès, {error_count} erreurs")
            return True
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'envoi: {e}")
            return False
    
    def get_statistics(self):
        """Retourne les statistiques de la newsletter"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Nombre d'abonnés actifs
            cursor.execute("SELECT COUNT(*) FROM subscribers WHERE statut = 'actif'")
            actifs = cursor.fetchone()[0]
            
            # Nombre total d'abonnés
            cursor.execute("SELECT COUNT(*) FROM subscribers")
            total = cursor.fetchone()[0]
            
            # Nombre de newsletters envoyées
            cursor.execute("SELECT COUNT(*) FROM newsletters WHERE statut = 'envoye'")
            newsletters_envoyees = cursor.fetchone()[0]
            
            # Dernière newsletter
            cursor.execute("""
                SELECT titre, date_envoi 
                FROM newsletters 
                WHERE statut = 'envoye' 
                ORDER BY date_envoi DESC 
                LIMIT 1
            """)
            derniere = cursor.fetchone()
            
            conn.close()
            
            return {
                'abonnes_actifs': actifs,
                'total_abonnes': total,
                'newsletters_envoyees': newsletters_envoyees,
                'derniere_newsletter': derniere
            }
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération des statistiques: {e}")
    
    def test_smtp_connection(self):
        """Test la connexion SMTP"""
        try:
            self.logger.info("=== TEST DE CONNEXION SMTP ===")
            self.logger.info(f"Serveur: {self.config['smtp_server']}")
            self.logger.info(f"Port: {self.config['smtp_port']}")
            self.logger.info(f"Email: {self.config['email_sender']}")
            self.logger.info(f"Mot de passe: {'*' * len(self.config['email_password'])}")
            
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            server.set_debuglevel(1)  # Activer le debug SMTP
            server.starttls()
            server.login(self.config['email_sender'], self.config['email_password'])
            server.quit()
            self.logger.info("✅ Connexion SMTP réussie!")
            return True
        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"❌ Erreur d'authentification: {e}")
            self.logger.error("Solutions:")
            self.logger.error("1. Vérifiez le fichier config.json")
            self.logger.error("2. Utilisez un mot de passe d'application Gmail")
            self.logger.error("3. Activez la validation en 2 étapes")
            return False
        except Exception as e:
            self.logger.error(f"❌ Erreur de connexion: {e}")
            return False
    
    def planifier_envoi(self, newsletter_id: int, date_envoi: datetime):
        """Planifie l'envoi d'une newsletter pour une date future"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE newsletters 
                SET date_envoi_planifie = ?, statut = 'planifie'
                WHERE id = ?
            ''', (date_envoi, newsletter_id))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Newsletter {newsletter_id} planifiée pour le {date_envoi}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur lors de la planification: {e}")
            return False
    
    def verifier_envois_planifies(self):
        """Vérifie et envoie les newsletters planifiées"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Récupérer les newsletters planifiées pour maintenant
            cursor.execute('''
                SELECT id FROM newsletters 
                WHERE statut = 'planifie' 
                AND date_envoi_planifie <= CURRENT_TIMESTAMP
            ''')
            
            newsletters_a_envoyer = cursor.fetchall()
            
            for (newsletter_id,) in newsletters_a_envoyer:
                self.send_newsletter(newsletter_id)
            
            conn.close()
            return len(newsletters_a_envoyer)
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des envois planifiés: {e}")
            return 0
    
    def _check_scheduled_newsletters(self):
        """Vérifie périodiquement les newsletters planifiées"""
        while True:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                cursor.execute('''
                    SELECT id, titre, date_envoi_planifie 
                    FROM newsletters 
                    WHERE statut = 'planifie' 
                    AND datetime(date_envoi_planifie) <= datetime(?)
                ''', (current_time,))
                
                newsletters_a_envoyer = cursor.fetchall()
                
                if newsletters_a_envoyer:
                    self.logger.info(f"Newsletters à envoyer trouvées: {len(newsletters_a_envoyer)}")
                    for id, titre, date in newsletters_a_envoyer:
                        self.logger.info(f"Envoi de la newsletter: {titre} (ID: {id})")
                        self.send_newsletter(id)
                
                conn.close()
            except Exception as e:
                self.logger.error(f"Erreur lors de la vérification des newsletters planifiées: {e}")
            
            # Attendre 30 secondes avant la prochaine vérification
            time.sleep(30)

def txt_to_html(txt_path, html_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    html_lines = [
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "<style>",
        "    body { font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }",
        "    .image-container { text-align: center; margin: 20px 0; }",
        "    .image-container img { max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
        "    .image-caption { color: #666; font-size: 0.9em; margin-top: 8px; font-style: italic; }",
        "    table { width: 100%; border-collapse: collapse; margin: 15px 0; }",
        "    th, td { padding: 12px; border: 1px solid #ddd; }",
        "    th { background-color: #f5f5f5; text-align: left; }",
        "    h1 { color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }",
        "    h2 { color: #444; margin-top: 30px; }",
        "    h3 { color: #555; }",
        "    ul { padding-left: 20px; }",
        "    li { margin-bottom: 8px; }",
        "    p { margin-bottom: 15px; }",
        "</style>",
        "</head>",
        "<body>"
    ]
    
    in_list = False
    in_table = False
    table_rows = []
    current_image_caption = None
    
    for line in lines:
        stripped = line.strip()
        
        # Gestion des images (format simple: [IMAGE]chemin/vers/image.jpg[CAPTION]Légende de l'image[/CAPTION])
        if stripped.startswith("[IMAGE]"):
            image_parts = stripped[7:].split("[CAPTION]")
            image_url = image_parts[0]
            caption = image_parts[1].replace("[/CAPTION]", "") if len(image_parts) > 1 else None
            
            html_lines.append("<div class='image-container'>")
            html_lines.append(f"<img src='{image_url}' alt='Image' loading='lazy'>")
            if caption:
                html_lines.append(f"<div class='image-caption'>{caption}</div>")
            html_lines.append("</div>")
            continue
        
        # Gestion des tableaux (format simple avec des tabulations ou des virgules)
        if "\t" in stripped or "," in stripped:
            if not in_table:
                in_table = True
                html_lines.append("<table>")
            
            # Utiliser soit les tabulations soit les virgules comme séparateurs
            separator = "\t" if "\t" in stripped else ","
            cells = [cell.strip() for cell in stripped.split(separator)]
            
            if not table_rows:  # Première ligne = en-tête
                html_lines.append("<thead><tr>")
                for cell in cells:
                    html_lines.append(f"<th>{cell}</th>")
                html_lines.append("</tr></thead><tbody>")
            else:
                html_lines.append("<tr>")
                for cell in cells:
                    html_lines.append(f"<td>{cell}</td>")
                html_lines.append("</tr>")
            
            table_rows.append(cells)
            continue
        elif in_table:
            in_table = False
            html_lines.append("</tbody></table>")
            table_rows = []
        
        # Gestion des titres (format simple: TITRE:, SOUS-TITRE:, etc.)
        if stripped.upper().endswith(":"):
            if stripped.upper().startswith("TITRE:"):
                html_lines.append(f"<h1>{stripped[:-1]}</h1>")
            elif stripped.upper().startswith("SOUS-TITRE:"):
                html_lines.append(f"<h2>{stripped[:-1]}</h2>")
            elif stripped.upper().startswith("SECTION:"):
                html_lines.append(f"<h3>{stripped[:-1]}</h3>")
            continue
        
        # Gestion des listes (format simple: - ou * au début de la ligne)
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{stripped[2:]}</li>")
            continue
        
        # Gestion des sauts de ligne et paragraphes
        if stripped == "":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
            continue
        
        # Texte normal
        if in_list:
            html_lines.append("</ul>")
            in_list = False
        html_lines.append(f"<p>{stripped}</p>")
    
    # Fermer les balises ouvertes
    if in_list:
        html_lines.append("</ul>")
    if in_table:
        html_lines.append("</tbody></table>")
    
    html_lines.append("</body></html>")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_lines))

if __name__ == "__main__":
    # Initialiser le gestionnaire
    newsletter_manager = NewsletterManager()
    
    # Vérifier les newsletters planifiées au démarrage
    print("\n=== VÉRIFICATION DES NEWSLETTERS PLANIFIÉES ===")
    conn = sqlite3.connect(newsletter_manager.db_path)
    cursor = conn.cursor()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        SELECT id, titre, date_envoi_planifie 
        FROM newsletters 
        WHERE statut = 'planifie' 
        AND datetime(date_envoi_planifie) <= datetime(?)
    ''', (current_time,))
    newsletters_a_envoyer = cursor.fetchall()
    
    if newsletters_a_envoyer:
        print(f"\n{len(newsletters_a_envoyer)} newsletter(s) à envoyer :")
        for id, titre, date in newsletters_a_envoyer:
            print(f"- {titre} (ID: {id}, planifiée pour: {date})")
            newsletter_manager.send_newsletter(id)
    conn.close()
    
    # Menu principal
    while True:
        print("\n=== MENU PRINCIPAL ===")
        print("1. Créer une nouvelle newsletter")
        print("2. Gérer les abonnés")
        print("3. Envoyer une newsletter")
        print("4. Voir les statistiques")
        print("5. Vérifier les envois planifiés")
        print("6. Quitter")
        
        choix = input("\nVotre choix (1-6): ")
        
        if choix == "1":
            # Créer une nouvelle newsletter
            print("\n=== CRÉATION D'UNE NEWSLETTER ===")
            titre = input("Titre de la newsletter: ")
            objet = input("Objet de l'email (laissez vide pour utiliser le titre): ")
            police = input("Police (Arial, Times New Roman, etc.) [Arial]: ") or "Arial"
            
            # Demander le contenu
            print("\nEntrez le contenu de votre newsletter (tapez 'FIN' sur une nouvelle ligne pour terminer):")
            contenu = []
            while True:
                ligne = input()
                if ligne == "FIN":
                    break
                contenu.append(ligne)
            
            # Convertir le contenu en HTML
            with open("temp_newsletter.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(contenu))
            
            txt_to_html("temp_newsletter.txt", "temp_newsletter.html")
            
            with open("temp_newsletter.html", "r", encoding="utf-8") as f:
                html_content = f.read()
            
            # Nettoyer les fichiers temporaires
            os.remove("temp_newsletter.txt")
            os.remove("temp_newsletter.html")
            
            # Créer la newsletter
            newsletter_id = newsletter_manager.create_newsletter(
                titre=titre,
                contenu_html=html_content,
                objet=objet or titre,
                police=police
            )
            
            if newsletter_id:
                print(f"\nNewsletter créée avec succès (ID: {newsletter_id})")
            
        elif choix == "2":
            # Gérer les abonnés
            print("\n=== GESTION DES ABONNÉS ===")
            print("1. Ajouter un abonné")
            print("2. Importer depuis Excel")
            print("3. Importer depuis CSV")
            print("4. Retour")
            
            sous_choix = input("\nVotre choix (1-4): ")
            
            if sous_choix == "1":
                email = input("Email: ")
                nom = input("Nom (optionnel): ")
                prenom = input("Prénom (optionnel): ")
                newsletter_manager.add_subscriber(email, nom, prenom)
            
            elif sous_choix == "2":
                fichier = input("Chemin du fichier Excel: ")
                email_col = input("Nom de la colonne email [email]: ") or "email"
                nom_col = input("Nom de la colonne nom (optionnel): ")
                prenom_col = input("Nom de la colonne prénom (optionnel): ")
                newsletter_manager.import_subscribers_from_excel(fichier, email_col, nom_col, prenom_col)
            
            elif sous_choix == "3":
                fichier = input("Chemin du fichier CSV: ")
                email_col = input("Nom de la colonne email [email]: ") or "email"
                nom_col = input("Nom de la colonne nom (optionnel): ")
                prenom_col = input("Nom de la colonne prénom (optionnel): ")
                newsletter_manager.import_subscribers_from_csv(fichier, email_col, nom_col, prenom_col)
        
        elif choix == "3":
            # Envoyer une newsletter
            print("\n=== ENVOI DE NEWSLETTER ===")
            print("1. Envoyer immédiatement")
            print("2. Planifier un envoi")
            print("3. Retour")
            
            sous_choix = input("\nVotre choix (1-3): ")
            
            if sous_choix in ["1", "2"]:
                # Lister les newsletters disponibles
                conn = sqlite3.connect(newsletter_manager.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id, titre, statut FROM newsletters ORDER BY date_creation DESC")
                newsletters = cursor.fetchall()
                conn.close()
                
                if not newsletters:
                    print("Aucune newsletter disponible")
                    continue
                
                print("\nNewsletters disponibles:")
                for id, titre, statut in newsletters:
                    print(f"{id}. {titre} ({statut})")
                
                newsletter_id = int(input("\nID de la newsletter à envoyer: "))
                
                if sous_choix == "1":
                    # Envoi immédiat
                    test_email = input("Email de test (laissez vide pour envoyer à tous): ")
                    if test_email:
                        newsletter_manager.send_newsletter(newsletter_id, test_email=test_email)
                    else:
                        newsletter_manager.send_newsletter(newsletter_id)
                
                else:
                    # Planification
                    date_str = input("Date d'envoi (format: JJ/MM/AAAA HH:MM): ")
                    try:
                        date_envoi = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
                        newsletter_manager.planifier_envoi(newsletter_id, date_envoi)
                        print(f"Newsletter planifiée pour le {date_str}")
                    except ValueError:
                        print("Format de date invalide")
        
        elif choix == "4":
            # Afficher les statistiques
            stats = newsletter_manager.get_statistics()
            if stats:
                print("\n=== STATISTIQUES ===")
                print(f"Abonnés actifs: {stats['abonnes_actifs']}")
                print(f"Total abonnés: {stats['total_abonnes']}")
                print(f"Newsletters envoyées: {stats['newsletters_envoyees']}")
                if stats['derniere_newsletter']:
                    print(f"Dernière newsletter: {stats['derniere_newsletter'][0]} ({stats['derniere_newsletter'][1]})")
        
        elif choix == "5":
            # Vérifier les envois planifiés
            print("\n=== VÉRIFICATION DES ENVOIS PLANIFIÉS ===")
            conn = sqlite3.connect(newsletter_manager.db_path)
            cursor = conn.cursor()
            
            # Afficher toutes les newsletters planifiées
            cursor.execute('''
                SELECT id, titre, date_envoi_planifie, statut 
                FROM newsletters 
                WHERE statut = 'planifie'
            ''')
            toutes_newsletters = cursor.fetchall()
            
            print("\nToutes les newsletters planifiées :")
            for id, titre, date, statut in toutes_newsletters:
                print(f"- {titre} (ID: {id}, statut: {statut}, date prévue: {date})")
            
            # Vérifier les newsletters à envoyer maintenant
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                SELECT id, titre, date_envoi_planifie 
                FROM newsletters 
                WHERE statut = 'planifie' 
                AND datetime(date_envoi_planifie) <= datetime(?)
            ''', (current_time,))
            newsletters_a_envoyer = cursor.fetchall()
            
            print("\nDate actuelle:", datetime.now())
            
            if newsletters_a_envoyer:
                print(f"\n{len(newsletters_a_envoyer)} newsletter(s) à envoyer :")
                for id, titre, date in newsletters_a_envoyer:
                    print(f"- {titre} (ID: {id}, planifiée pour: {date})")
                    newsletter_manager.send_newsletter(id)
            else:
                print("\nAucune newsletter à envoyer pour le moment.")
            
            conn.close()
        
        elif choix == "6":
            print("Au revoir!")
            break
        
        else:
            print("Choix invalide")
