# django_openailite
## Instructions
### Install this github project only
   - cd django;
   - python3.11 -m venv env
   - source env/bin/activate
   - pip install --upgrade pip
   - pip install -r requirements.txt
   - Note that **openai==1.73.0** is with model **gpt-4o-mini** is used. *Other combinations may fail since the assistants api seems to change daily.*
 ## Get OPENAI_API_KEY
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
