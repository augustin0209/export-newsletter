release: python manage.py migrate && echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('RH_admin', 'contact.flexipartner@gmail.com
', 'Flexi_4Newsletter?')" | python manage.py shell
web: gunicorn EXPORT_NEWSLETTER.wsgi --bind 0.0.0.0:$PORT
