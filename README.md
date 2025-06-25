# Gestionnaire de Newsletter Django

Une application Django pour gérer et envoyer des newsletters avec une interface web moderne.

## Fonctionnalités

- Création et gestion de newsletters avec éditeur WYSIWYG
- Gestion des abonnés (ajout manuel ou import depuis Excel/CSV)
- Envoi de newsletters avec support HTML et texte
- Planification des envois
- Statistiques d'envoi
- Système de désabonnement
- Interface responsive avec Bootstrap 5

## Prérequis

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)
- Un compte Gmail pour l'envoi des emails (ou autre serveur SMTP)

## Installation

1. Clonez le dépôt :
```bash
git clone https://github.com/votre-username/newsletter-manager.git
cd newsletter-manager
```

2. Créez un environnement virtuel et activez-le :
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Installez les dépendances :
```bash
pip install -r requirements.txt
```

4. Configurez la base de données :
```bash
python manage.py migrate
```

5. Créez un superutilisateur :
```bash
python manage.py createsuperuser
```

6. Configurez les paramètres SMTP dans `newsletter_project/settings.py` :
```python
EMAIL_HOST_USER = 'votre-email@gmail.com'
EMAIL_HOST_PASSWORD = 'votre-mot-de-passe-app'  # Pour Gmail, utilisez un mot de passe d'application
```

## Utilisation

1. Démarrez le serveur de développement :
```bash
python manage.py runserver
```

2. Accédez à l'application dans votre navigateur :
```
http://localhost:8000
```

3. Connectez-vous avec votre compte superutilisateur pour accéder à l'interface d'administration :
```
http://localhost:8000/admin
```

## Gestion des abonnés

- Ajoutez des abonnés manuellement via l'interface web
- Importez des abonnés depuis un fichier Excel ou CSV
- Gérez les désabonnements via le lien de désabonnement inclus dans chaque newsletter

## Envoi de newsletters

1. Créez une nouvelle newsletter avec l'éditeur WYSIWYG
2. Prévoyez l'envoi ou envoyez immédiatement
3. Testez l'envoi avec un email de test
4. Suivez les statistiques d'envoi

## Sécurité

- Les mots de passe et tokens sont sécurisés
- Protection CSRF activée
- Validation des emails
- Gestion sécurisée des désabonnements

## Développement

Pour contribuer au projet :

1. Créez une branche pour votre fonctionnalité
2. Committez vos changements
3. Poussez vers la branche
4. Créez une Pull Request

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails. 