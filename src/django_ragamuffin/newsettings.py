AI_KEY =  OPENAI_API_KEY
USE_CHATGPT =  os.environ.get("USE_CHATGPT",False) == 'True'
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
RUNTESTS = "pytest" in sys.modules

AI_KEY =  os.environ.get("AI_KEY",None)
USE_CHATGPT =  os.environ.get("USE_CHATGPT",False) == 'True'
#AI_MODEL = os.environ.get('AI_MODEL','gpt-3.5-turbo')
AI_MODEL = os.environ.get('AI_MODEL','gpt-4o-mini')
SERVER = os.environ.get("SERVER", OPENTA_SERVER )
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
print(f"CACHES = {CACHES}")
APP_KEY = os.environ.get('APP_KEY',None)
APP_ID = os.environ.get('APP_ID',None)
USE_MATHPIX = os.environ.get('USE_MATHPIX','False') == 'True'
if APP_KEY == None or APP_ID == None :
    USE_MATHPIX = False
print(f"SESSION = {SESSION_ENGINE}")
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
#NOCACHES = {};
#NOCACHES['default'] =  {
#        "BACKEND": "django.core.cache.backends.memcached.MemcachedCache",  # uses pure Python
#        "LOCATION": "memcached:11211",
#    }
#NOCACHES['default']  = {
#        'BACKEND': 'django.core.cache.backends.memcached.PyLibMCCache',
#        'LOCATION': 'memcached:11211',
#        'OPTIONS': {
#            'binary': True,
#            'behaviors': {
#                'tcp_nodelay': True,
#                'tcp_keepalive': True,
#                'connect_timeout': 2000,  # milliseconds
#                'send_timeout': 750 * 1000,
#                'receive_timeout': 750 * 1000,
#                'retry_timeout': 2,        # seconds before retrying downed server
#                'dead_timeout': 10,        # seconds to mark server as "dead"
#            },
#        },
#    }
CACHES['default']  = {
        "BACKEND": "django.core.cache.backends.memcached.PyMemcacheCache",
        "LOCATION": ["127.0.0.1:11211"],  # or "memcached:11211" in Docker/K8s
        "TIMEOUT": 300,  # Key TTL in seconds (None = never expire)
        "OPTIONS": {
            # Connection pooling
            "use_pooling": True,
            "max_pool_size": 10,

            # Network timeouts (in seconds)
            "connect_timeout": 2,   # TCP connection timeout
            "timeout": 2,           # Read/write timeout

            # TCP options
            "no_delay": True,       # Disable Nagle’s algorithm (faster small writes)
            #"tcp_keepalive": True,  # Keep connections alive

            # Error handling
            "ignore_exc": False,    # Raise errors instead of silently ignoring them
        },
    }


INSTALLED_APPS.append('django_ragamuffin')
DJANGO_RAGAMUFFIN_DB = os.environ.get("DJANGO_RAGAMUFFIN_DB",None) 
DATABASES.update({
    'django_ragamuffin': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DJANGO_RAGAMUFFIN_DB,
        'USER': PGUSER,
        'PASSWORD': PGPASSWORD,
        'HOST': 'localhost',
        'PORT': '5432',
        'ATOMIC_REQUESTS' : False,
        }
    })

MAXWAIT = 120 ; # WAIT MAX 120 seconds
DEFAULT_TEMPERATURE = 0.2;
LAST_MESSAGES = 99
MAX_NUM_RESULTS = None
MAX_TOKENS = 8000 # NOT IMPLMENTED AS OF openai==1.173.0 
AI_MODELS = {'staff' : 'gpt-5-mini', 'default' : AI_MODEL }
API_APP = 'localhost'
EFFORT = 'low'
