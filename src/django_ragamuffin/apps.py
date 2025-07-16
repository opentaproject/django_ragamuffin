from django.apps import AppConfig
from django.conf import settings
import os
import sys
from .util import create_database_if_not_exists
import threading
import logging
#from django.db.models.signals import post_migrate
logger = logging.getLogger(__name__)
#from django.dispatch import receiver


#@receiver(post_migrate)
#def handle_post_migrate(sender, **kwargs):
#    db = settings.DATABASES['django_ragamuffin']
#    db_name = db['NAME']
#    host = db['HOST']
#    user = db['USER']
#    password = db['PASSWORD']
#    superuser = os.environ.get("SUPERUSER", 'super')
#    superuser_password = os.environ.get("SUPERUSER_PASSWORD", '')
#
#    try:
#        create_database_if_not_exists(db_name, host, user, password, superuser, superuser_password)
#    except Exception as e:
#        logger.info(f"ERROR CREATING SUPERUSER {str(e)}")
#
#    if not getattr(settings, 'RUNTESTS', False):
#        def migrate_all():
#            for db in settings.DATABASES:
#                try:
#                    call_command('migrate', database=db, verbosity=0)
#                except Exception as e:
#                    logger.warning(f"Migration failed for {db}: {e}")
#
#        threading.Thread(target=migrate_all).start()
#



class OpenaiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_ragamuffin"

#    def broken_ready(self):
#        import django_ragamuffin.signals  # just import here, logic lives in signals



    def ready(self):
        from django.conf import settings
        from django.core.management import call_command
        if any(cmd in sys.argv for cmd in ["migrate", "makemigrations", "collectstatic", "test"]):
            return

        def migrate_all():
            if not settings.RUNTESTS :
                for db in settings.DATABASES:
                    if db == 'django_ragamuffin' :
                        call_command('migrate', database=db, verbosity=0)
        print("CHECK APP READY")
        db = settings.DATABASES['django_ragamuffin'];
        db_name = db['NAME'];
        host = db['HOST'];
        user = db['USER'];
        password = db['PASSWORD']
        superuser = os.environ.get("SUPERUSER", 'super')
        superuser_password = os.environ.get("SUPERUSER_PASSWORD",'')
        try :
            create_database_if_not_exists(db_name, host,user, password , superuser, superuser_password) 
        except Exception as e:
            logger.info(f"ERROR CREATING SUPERUSER {str(e)}")
        threading.Thread(target=migrate_all).start()
