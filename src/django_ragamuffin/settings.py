import os
import sys
from django.conf import settings
AI_KEY =  os.environ.get("OPENAI_API_KEY",None)
AI_MODEL = os.environ.get('AI_MODEL','gpt-5-mini')
OPENAI_UPLOAD_STORAGE =  os.environ.get("OPENAI_UPLOAD_STORAGE",'/tmp/openaifiles')
os.makedirs(OPENAI_UPLOAD_STORAGE, exist_ok=True)
API_APP = os.environ.get('API_APP','localhost')
DJANGO_RAGAMUFFIN_DB = os.environ.get("DJANGO_RAGAMUFFIN_DB",None) 
d = settings.DATABASES['default'];
PGDATABASE = d.get('NAME','postgres')
PGHOST = d.get('HOST','localhost')
PGUSER = d.get('USER','postgres')
PGPASSWORD = d.get('PASSWORD','postgres')
if not hasattr(settings, 'SUBDOMAIN' ):
    SUBDOMAIN = os.environ.get('SUBDOMAIN','query')
MAXWAIT = 480 ; # WAIT MAX 120 seconds
DEFAULT_TEMPERATURE = 0.2;
LAST_MESSAGES = 99
MAX_NUM_RESULTS = None
MAX_TOKENS = 8000 # NOT IMPLMENTED AS OF openai==1.173.0 
AI_MODELS = {'staff' : 'gpt-5-mini' , 'default' : AI_MODEL }
MEDIA_ROOT = OPENAI_UPLOAD_STORAGE
if not 'django_ragamuffin' in settings.LOGGING['loggers'] :
    settings.LOGGING['loggers']['django_ragamuffin'] = {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
            }


RUNTESTS = "pytest" in sys.modules
if not RUNTESTS :
    print(f"NOT RUNTESTS")
    if not hasattr('settings','DATABASE_ROUTERS') :
        DATABASE_ROUTERS = ['django_ragamuffin.db_routers.RagamuffinRouter'] 
    else :
        DATABASE_ROUTERS = ['django_ragamuffin.db_routers.RagamuffinRouter'] + settings.DATABASE_ROUTERS

APP_KEY = os.environ.get('APP_KEY',None)
APP_ID = os.environ.get('APP_ID',None)
USE_MATHPIX = os.environ.get('USE_MATHPIX','False') == 'True'
if APP_KEY == None or APP_ID == None :
    USE_MATHPIX = False
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
CHATGPT_TIMEOUT = 240
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
USE_CHATGPT =  os.environ.get("USE_CHATGPT",False) == 'True'
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
APP_KEY = os.environ.get('APP_KEY',None)
APP_ID = os.environ.get('APP_ID',None)
USE_MATHPIX = os.environ.get('USE_MATHPIX','False') == 'True'
if APP_KEY == None or APP_ID == None :
    USE_MATHPIX = False

DEFAULT_TEMPERATURE = 0.2;
LAST_MESSAGES = 99
MAX_NUM_RESULTS = None
MAX_TOKENS = 8000 # NOT IMPLMENTED AS OF openai==1.173.0 
AI_MODELS = {'staff' : 'gpt-5-mini', 'default' : AI_MODEL }
if hasattr(settings,'EFFORT' ) :
    EFFORT = settings.EFFORT
else :
    EFFORT = 'medium'
DJANGO_RAGAMUFFIN_DB = os.environ.get("DJANGO_RAGAMUFFIN_DB",None) 
if not RUNTESTS :
    settings.DATABASES.update({
        'django_ragamuffin': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DJANGO_RAGAMUFFIN_DB,
            'USER': PGUSER,
            'PASSWORD': PGPASSWORD,
            'HOST': PGHOST,
            'PORT': '5432',
            'ATOMIC_REQUESTS' : False,
            }
        })
settings.INSTALLED_APPS.append('django.contrib.humanize')

print(f"PGHOST = {PGHOST}")
