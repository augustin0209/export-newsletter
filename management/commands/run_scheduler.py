 # newsletters/management/commands/run_scheduler.py
from django.core.management.base import BaseCommand
from newsletters.views import check_scheduled_newsletters_standalone # Nous allons adapter la fonction
import time
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
        help = 'Runs a scheduler to check and send planned newsletters periodically.'

        def handle(self, *args, **options):
            self.stdout.write(self.style.SUCCESS('Starting newsletter scheduler...'))
            while True:
                try:
                    self.stdout.write('Checking for scheduled newsletters...')
                    check_scheduled_newsletters_standalone() # Appelle la fonction que nous allons créer
                    self.stdout.write('Scheduled newsletters check complete. Waiting 30 seconds.')
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'Error in scheduler: {e}'))
                time.sleep(30) # Attendre 30 secondes