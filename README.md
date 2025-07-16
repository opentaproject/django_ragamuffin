# django_openailite
## Instructions
### Install this github project only
    - cd django;
    - python3.11 -m venv env
    - source env/bin/activate
    - pip install --upgrade pip
    - pip install -r requirements.txt
 ### Get OPENAI_API_KEY
   - Visit https://openai.com , establis an account, and login to the API platform
   - You do not need a **ChatGPT** account, but you must have a paid openai account. It is pay as you go and putting $10 in will allow you to test
   - Create an API key, copy it and create the environment variable
   - OPENAI_API_KEY=xxxxxxxx 

 ### Run
   - python manage.py makemigrations
   - python manage.py migrate
   - python manage.py createsuperuser
   - python manage.py runserver
   - visit http://localhost:8000
### Test
   - pytest is slow, so to make sure you see what is happening flag with -s to see prints statements
   - pytest -s 
   - python manage.py runserver
     - Then check the admin pages to add files, vector_stores, assistants and threads.
### Build
   - cd src
   - python -m build

## Using 
  - pip install django_ragamuffin
  - in settings.py
  ```
  DATABASES = {
    ...
    'django_ragamuffin': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'django_ragamuffin'
        'USER': PGUSER,
        'PASSWORD': PGPASSWORD,
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

APP_ID = os.environ.get("APP_ID",None) # Mathpix
APP_KEY = os.environ.get("APP_KEY",None) #mathpix
AI_KEY =  os.environ.get("OPENAI_API_KEY",None) #openai.com
OPENAI_UPLOAD_STORAGE =  os.environ.get("OPENAI_UPLOAD_STORAGE",'/tmp/openaifiles')
os.makedirs(OPENAI_UPLOAD_STORAGE, exist_ok=True)
INSTALLED_APPS.append('django_ragamuffin')
STATIC_ROOT = os.path.join(BASE_DIR, "deploystatic")
MEDIA_URL = 'media/'
MEDIA_ROOT = OPENAI_UPLOAD_STORAGE
MAXWAIT = 120 ; # WAIT MAX 120 seconds
DEFAULT_TEMPERATURE = 0.2;
LAST_MESSAGES = 99
MAX_NUM_RESULTS = None
MAX_TOKENS = 8000 # NOT IMPLMENTED AS OF openai==1.173.0
AI_MODELS = {'staff' : 'gpt-4o-mini' , 'default' : AI_MODEL }
API_APP = 'localhost'
DJANGO_RAGAMUFFIN_DB = 'query4'
DATABASE_ROUTERS = ['django_ragamuffin.db_routers.RagamuffinRouter']
```

Add the line to urls.py
```
  path('grappelli/', include('grappelli.urls')),  # must come before adm
  path('django_ragamuffin/', include('django_ragamuffin.urls')),
  ```
