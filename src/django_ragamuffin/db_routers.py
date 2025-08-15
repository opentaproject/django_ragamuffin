from django.conf import settings
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from django.core.exceptions import PermissionDenied, SuspiciousOperation
import inspect


class RagamuffinRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'django_ragamuffin':
            #print(f"READ {model._meta.app_label} hints={hints}")
            frames = inspect.stack()  # [0] is current, [1] is caller
            for frame in frames :
                if 'src' in frame.filename :
                    pass
                    #print(f"READ Called from  {frame.filename}, line {frame.lineno}")
            #print(f"{settings.DATABASES['django_ragamuffin']['NAME']}")
            return "django_ragamuffin"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'django_ragamuffin':
            #print(f"WRITE {model._meta.app_label} hints={hints}")
            frame = inspect.stack()[5]  # [0] is current, [1] is caller
            if 'src' in frame.filename :
                pass
                #print(f"WRITE Called from {frame.filename}, line {frame.lineno}")
            return "django_ragamuffin"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Optional: allow relations within the same db
        return True
        if (
            obj1._meta.app_label == 'django_ragamuffin' or
            obj2._meta.app_label == 'django_ragamuffin'
        ):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'django_ragamuffin':
            return db == "django_ragamuffin"
        return None

