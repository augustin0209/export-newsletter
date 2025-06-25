release: python manage.py migrate
web: gunicorn newsletter_project.wsgi --bind 0.0.0.0:$PORT
