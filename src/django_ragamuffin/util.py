import psycopg2
from psycopg2 import sql
import io
from django.core.management import call_command
import os
import django
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from urllib.parse import urljoin
from django.db.migrations.executor import MigrationExecutor
from django.db import connections

def needs_migration(using='default'):
    connection = connections[using]
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    #print(f"using={using} PLAN = {plan}")
    return bool(plan)



def create_database_if_not_exists(db_name, host,user , password , superuser, superuser_password ) :
    port = 5432
    conn = psycopg2.connect(dbname="postgres", user=user, password=password, host=host, port=port)
    conn.autocommit = True  # Enable auto-commit mode
    cursor = conn.cursor()
    cursor.execute(sql.SQL("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s"), [db_name])
    exists_  = cursor.fetchone()
    exists = bool(exists_ and exists_[0])
    #print(f"CREATE_DATABASE {db_name} exists = {exists}")
    
    if not exists:
        #print(f"DOES NOT EXISTS")
        # Database does not exist, so create it
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        settings.DEBUG=True
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', '.settings')
        django.setup()
        cursor.close()
        conn.close()
        #call_command( 'migrate', database='django_ragamuffin'  )
    for db_alias in settings.DATABASES.keys():
        needm = needs_migration( db_alias )
        if needm :
            print(f"YES Migrating: {db_alias}")
            call_command("migrate", database=db_alias)
    fake_stdin = io.StringIO(superuser_password)
    if not settings.RUNTESTS :
        try :
            call_command( 'createsuperuser', '--username' , superuser, '--email' , 'super@mail.com', '--noinput',stdin=fake_stdin)
        except RuntimeWarning as err :
            pass
            #print(f"CANNOT CREATE DEFAULT SUPERUSER {str(err)} ")
            

