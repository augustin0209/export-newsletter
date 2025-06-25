import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app_newsletter.settings')  # adapte si ton settings a un autre nom

from django.core.management import execute_from_command_line

if __name__ == '__main__':
    execute_from_command_line(['manage.py', 'runserver', '127.0.0.1:8000', '--noreload'])
