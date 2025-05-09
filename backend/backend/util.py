import psycopg2
from psycopg2 import sql
import io
from django.core.management import call_command
import os
import django
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from urllib.parse import urljoin



def create_database_if_not_exists(db_name, host,user , password , superuser, superuser_password ) :
    port = 5432
    conn = psycopg2.connect(dbname="postgres", user=user, password=password, host=host, port=port)
    conn.autocommit = True  # Enable auto-commit mode
    cursor = conn.cursor()
    cursor.execute(sql.SQL("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s"), [db_name])
    exists = cursor.fetchone()
    
    if not exists:
        # Database does not exist, so create it
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        settings.DEBUG=True
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', '.settings')
        django.setup()
        cursor.close()
        conn.close()
        call_command( 'makemigrations'  )
        #call_command( 'migrate'  )
        #fake_stdin = io.StringIO(superuser_password)
        #call_command( 'createsuperuser', '--username' , superuser, '--email' , 'super@mail.com', '--noinput',stdin=fake_stdin)

