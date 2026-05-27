import os
import sys
from django.conf import settings
from openai import OpenAI
from openai import OpenAIError
import re

DEFAULT_AI_MODEL = 'gpt-4o-mini'

def get_latest_mini_model(default=DEFAULT_AI_MODEL) :
    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return default
    client = OpenAI(api_key=api_key)
    try:
        models = client.models.list()
    except (OpenAIError, TypeError):
        return default
    mini_models = []
    for m in models.data:
        model_id = m.id
        if re.match(r"^gpt-5(\.\d+)?-mini", model_id):
            mini_models.append(model_id)
    if not mini_models:
        return default
    def model_sort_key(model_id):
        m = re.match(r"^gpt-(\d+)(?:\.(\d+))?-mini", model_id)
        major = int(m.group(1))
        minor = int(m.group(2) or 0)
        date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})$", model_id)
        if date_match:
            date_tuple = tuple(map(int, date_match.groups()))
        else:
            date_tuple = (0, 0, 0)
        return (major, minor, date_tuple)
    return sorted(mini_models, key=model_sort_key)[-1]

AI_KEY =  (getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY", None))
AI_MODEL = (getattr(settings, 'AI_MODEL', None) or os.environ.get('AI_MODEL', DEFAULT_AI_MODEL ))
# Default to '/subdomain-data/query' to keep a single source of truth.
# Projects can override this in their settings if needed.
OPENAI_UPLOAD_STORAGE =  (getattr(settings, "OPENAI_UPLOAD_STORAGE", None) or os.environ.get("OPENAI_UPLOAD_STORAGE", '/subdomain-data/query'))
os.makedirs(OPENAI_UPLOAD_STORAGE, exist_ok=True)
API_APP = (getattr(settings, 'API_APP', None) or os.environ.get('API_APP', 'localhost'))
DJANGO_RAGAMUFFIN_DB = (getattr(settings, "DJANGO_RAGAMUFFIN_DB", None) or os.environ.get("DJANGO_RAGAMUFFIN_DB", None)) 
d = settings.DATABASES['default'];
PGDATABASE = d.get('NAME','postgres')
PGHOST = d.get('HOST','localhost')
PGUSER = d.get('USER','postgres')
PGPASSWORD = d.get('PASSWORD','postgres')
if not hasattr(settings, 'SUBDOMAIN' ):
    SUBDOMAIN = (getattr(settings, 'SUBDOMAIN', None) or os.environ.get('SUBDOMAIN','query'))
MAXWAIT = 480 ; # WAIT MAX 120 seconds
DEFAULT_TEMPERATURE = 0.2;
LAST_MESSAGES = 99
MAX_NUM_RESULTS = None
MAX_TOKENS = 8000 # NOT IMPLMENTED AS OF openai==1.173.0 
AI_MODELS = getattr(settings, 'AI_MODELS', {'staff' : AI_MODEL , 'default' : AI_MODEL }  )
print(f"AI_MODELS = {AI_MODELS}")
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

APP_KEY = (getattr(settings, 'APP_KEY', None) or os.environ.get('APP_KEY', None))
APP_ID = (getattr(settings, 'APP_ID', None) or os.environ.get('APP_ID', None))
USE_MATHPIX = ((getattr(settings, 'USE_MATHPIX', None) or os.environ.get('USE_MATHPIX','False')) == 'True')
if APP_KEY == None or APP_ID == None :
    USE_MATHPIX = False
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
CHATGPT_TIMEOUT = 240
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
USE_CHATGPT =  getattr(settings, "USE_CHATGPT", None) or os.environ.get("USE_CHATGPT", False) == 'True'
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
APP_KEY = (getattr(settings, 'APP_KEY', None) or os.environ.get('APP_KEY', None))
APP_ID = (getattr(settings, 'APP_ID', None) or os.environ.get('APP_ID', None))
USE_MATHPIX = ((getattr(settings, 'USE_MATHPIX', None) or os.environ.get('USE_MATHPIX','False')) == 'True')
if APP_KEY == None or APP_ID == None :
    USE_MATHPIX = False

DEFAULT_TEMPERATURE = 0.2;
LAST_MESSAGES = 99
MAX_NUM_RESULTS = None
MAX_TOKENS = 8000 # NOT IMPLMENTED AS OF openai==1.173.0 
if hasattr(settings,'EFFORT' ) :
    EFFORT = settings.EFFORT
else :
    EFFORT = 'medium'
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
