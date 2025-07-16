# django_ragamuffin/signals.py
import os
import logging
import threading
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.conf import settings
from django.core.management import call_command
from django.db import connection

from .util import create_database_if_not_exists  # if you have this defined

logger = logging.getLogger(__name__)

@receiver(post_migrate)
def handle_post_migrate(sender, **kwargs):
    db = settings.DATABASES['django_ragamuffin']
    db_name = db['NAME']
    host = db['HOST']
    user = db['USER']
    password = db['PASSWORD']
    superuser = os.environ.get("SUPERUSER", 'super')
    superuser_password = os.environ.get("SUPERUSER_PASSWORD", '')

    try:
        create_database_if_not_exists(db_name, host, user, password, superuser, superuser_password)
    except Exception as e:
        logger.info(f"ERROR CREATING SUPERUSER {str(e)}")

    if not getattr(settings, 'RUNTESTS', False):
        def migrate_all():
            for db in settings.DATABASES:
                try:
                    call_command('migrate', database=db, verbosity=0)
                except Exception as e:
                    logger.warning(f"Migration failed for {db}: {e}")

        threading.Thread(target=migrate_all).start()
