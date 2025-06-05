from django.test import TestCase
import hashlib
import django
import time
import os
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ObjectDoesNotExist
import tiktoken
import openai
from openai import OpenAI

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from django_ragamuffin.models import OpenAIFile, VectorStore, Assistant,  Thread
from django.contrib.auth.models import User

model = 'gpt-4o-mini'
client = OpenAI()
import string
import random


def randstring(length=8):
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    return ''.join(random.choices(characters, k=length))


class OpenAI(TestCase):

    def create_testfile_from_string( self, s , name ):
        url = reverse('admin:django_ragamuffin_openaifile_add')  # use your app and model name
        test_file1 = SimpleUploadedFile( name , s , content_type="text/plain")
        csum = hashlib.md5( s  ).hexdigest()
        res = self.client.post( url ,  {'file': test_file1}, follow=True)
        for file in OpenAIFile.objects.all() :
            print(f"ALL FILES = {file} {file.path} ")
        t1 = OpenAIFile.objects.get(name=name)
        return t1




    def setUp( self ):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser( username='admin', email='admin@example.com', password='adminpass')
        self.client.login(username='admin', password='adminpass')
        self.user = User.objects.create_user(username='testuser', password='testpass')

    def test_user_exists(self):
        user_exists = User.objects.filter(username='testuser').exists()
        self.assertTrue(user_exists)

    def test_create_and_delete_file_object(self):
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        url = reverse('admin:django_ragamuffin_openaifile_add')  # use your app and model name
        t1 = self.create_testfile_from_string(b"test1_content_here","test1.txt")
        file_id1 = t1.file_ids[0]
        try :
            aifile = client.files.retrieve(file_id1)
            exists = True
        except openai.OpenAIError as e:
            exists = False
        assert exists , f"{file_id1} Does not exist on server "
        path = t1.path
        assert os.path.exists(path), f"LOCAL FILE PATH {path} DOES NOT EXIST"
        t1.delete();
        try :
            aifile = client.files.retrieve(file_id1)
            exists = True
        except openai.OpenAIError as e:
            exists = False
        assert not exists, f"FILE {file_id1} was not successfully deleted on the server"
        try :
            t1 = OpenAIFile.objects.get(pk=t1.pk)
            exists_locally = True
        except ObjectDoesNotExist as e :
            exists_locally = False
        assert not exists_locally, f"File {file_id1} still exists locally"
        assert not os.path.exists(path), f"LOCAL FILE PATH {path} DID NOT GET DELETED"
        print(f"NTOKENS OF t1 = {t1.ntokens}")




    def test_create_and_delete_two_openai_file_objects(self):
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        print(f"RESPONSE = {response}")
        url = reverse('admin:django_ragamuffin_openaifile_add')  # use your app and model name
        t1 = self.create_testfile_from_string( b"test1_content_here", "test1.txt" )
        t2 = self.create_testfile_from_string( b"test2_content_here" , "test2.txt")
        for t in [t1,t2] :
            path = t.path
            name = t.name
            file_id = t.file_ids[0]
            t.delete();
            try :
                aifile = client.files.retrieve(file_id)
                exists = True
            except openai.OpenAIError as e:
                exists = False
            print(f"NOW EXISTS = {exists}")
            assert not exists, f"FILE {file_id} was not successfully deleted on the server"
            try :
                tt = OpenAIFile.objects.get(pk=t.pk)
                exists_locally = True
            except ObjectDoesNotExist as e :
                exists_locally = False
                print(f"OK! {name} is GONE  LOCALLY ")
            assert not exists_locally, f"File {file_id} still exists locally"
            assert not os.path.exists(path), f"LOCAL FILE PATH {path} DID NOT GET DELETED"






    def test_create_and_delete_vector_store_object(self):
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        print(f"RESPONSE = {response}")
        t1 = self.create_testfile_from_string( b"test1_content_here" ,"test1.txt")
        t2 = self.create_testfile_from_string( b"test2_content_here" ,"test2.txt")
        vsname = randstring()
        vs = VectorStore(name=vsname)
        vs.save()
        vs.files.set([t1,t2])
        vs.save()
        vs.files.add(t1) # REDUNDANT ADD
        vs.save()
        vs.files.add(t2); # REDUNDANT ADD
        vs.save()
        print(f"NTOKENS OF VS = {vs.ntokens()}")
        assert vs.files_ok( ), "TWO FILES NOT OK"
        vs.files.remove( t1  )
        print(f"AFTER REMOVE t1 {vs.file_ids}")
        assert vs.files_ok() , "ONE FILE NOT OK"
        t2.delete()
        print(f"AFTERM REMOVING t2 {vs.file_ids}")
        assert vs.files_ok( ) , "NO FILES SHOULD BE LEFT"
        vs.delete()
        t1.delete()


    def test_create_and_delete_assistant_object(self):
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        print(f"RESPONSE = {response}")
        url = reverse('admin:django_ragamuffin_openaifile_add')  # use your app and model name

        t1 = self.create_testfile_from_string( b"test1_content_here" ,"test1.txt")
        t2 = self.create_testfile_from_string( b"test2_content_here" ,"test2.txt")
        t3 = self.create_testfile_from_string( b"test3_content_here" ,"test3.txt")


        vsname = randstring()
        vs1 = VectorStore(name=vsname)
        vs1.save()
        vs1.files.set([t1])
        vs1.save()

        vsname = randstring()
        vs2 = VectorStore(name=vsname)
        vs2.save()
        vs2.files.set([t2,t3])
        vs2.save()

        aname = randstring()
        assistant = Assistant( name=aname)
        assistant.instructions = 'Answer the questions and make a good guess if the answer is not totally obvious from the context!'
        assistant.save();
        assistant.vector_stores.add(vs1)
        assistant.save();
        file_ids = assistant.file_ids()
        print(f"NTOKENS ASSISTANT = {assistant.ntokens() }")
        print(f"ASSISTANT FILE_IDS = {file_ids}")

        assert  assistant.files_ok()  , f"FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        print(f"NOW ADD VS2")
        assistant.vector_stores.add(vs2)
        file_ids = assistant.file_ids()
        print(f"FILE_IDS IS NOW {file_ids}")
        print(f"NTOKENS ASSISTANT = {assistant.ntokens() }")
        assert assistant.files_ok() , 'FILES_IDS_LOCAL = {file_ids}'
        print(f"NOW SUBTRACT VS1")
        assistant.vector_stores.remove(vs1)
        file_ids = assistant.file_ids()
        print(f"FILE_IDS IS NOW {file_ids}")
        assert assistant.files_ok() , 'FILES_IDS_LOCAL = {file_ids}'

        assistant.vector_stores.remove(vs2)
        file_ids = assistant.file_ids()
        print(f"FILE_IDS SHOULD BE EMPTY : IS NOW {file_ids}")
        assert assistant.files_ok() , 'FILES_IDS_LOCAL = {file_ids}'

        vs1.delete();
        vs2.delete();
        t1.delete();
        t2.delete();
        t3.delete();
        assistant.delete();

    def test_create_and_delete_thread(self):
        import tiktoken


        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        print(f"RESPONSE = {response}")
        url = reverse('admin:django_ragamuffin_openaifile_add')  # use your app and model name
        #test_file1 = SimpleUploadedFile( "test1.txt", b"The dog was black", content_type="text/plain")
        #self.client.post( url ,  {'file': test_file1}, follow=True)
        #t1 = OpenAIFile.objects.get(name="test1.txt")
        #test_file2 = SimpleUploadedFile( "test2.txt", b"The cat was white.", content_type="text/plain")
        #self.client.post( url ,  {'file': test_file2}, follow=True)
        #t2 = OpenAIFile.objects.get(name="test2.txt")

        #test_file3 = SimpleUploadedFile( "test3.txt", b"The dog barked.", content_type="text/plain")
        #self.client.post( url ,  {'file': test_file3}, follow=True)
        #t3 = OpenAIFile.objects.get(name="test3.txt")

        t1 = self.create_testfile_from_string( b"the dog was black" ,"test1.txt")
        t2 = self.create_testfile_from_string( b"the cat was white" ,"test2.txt")
        t3 = self.create_testfile_from_string( b"the dog barked" ,"test3.txt")


        vsname = randstring()
        vs1 = VectorStore(name=vsname)
        vs1.save()
        vs1.files.set([t1,t2,t3])
        vs1.save()
        aname = randstring()
        assistant = Assistant( name=aname)
        assistant.instructions = 'Answer the questions as concisely as possible. No need for complete sentences. Make a good guess if the answer is not totally obvious from the context, but if it is not obvious, start your guess with \'It seems like\' !'
        assistant.save();
        assistant.vector_stores.add(vs1)
        assistant.save();
        file_ids = assistant.file_ids()
        print(f"ASSISTANT FILE_IDS = {file_ids}")
        assert  assistant.files_ok()  , f"FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        print(f"NTOKENS ASSISTANT = {assistant.ntokens() }")
        print(f"ASSITANT REMOTE FILES OK")

        queries =  [ [ 'What color was the dog.', 'black',True],
                     [ 'What color was the cat.', 'white',True],
                     [ 'What did the dog do?', 'barked',True] , 
                     [ 'What did the cat do?', 'miaow',False],
                     [ 'Please repeat the reply to the first request','black',True]
                        ]

        aname = randstring()
        thread = Thread(name=aname,assistant=assistant,user=self.user)
        thread.save()
        for  q in queries :
            print(f"TESTING1 {q}")
            [ query,response , truth ] =  q
            r = thread.run_query(  query=query,  last_messages=2)
            txt = r['assistant']
            assert ( response in txt ) == truth , f"ERROR : in {q} TXT={txt} "
            print(f"QUERY {query} -> {txt}")

        print(f"FINALLY MESSAGES = {thread.messages}")

        vs1.files.remove(t3)
        t3.delete();
        file_ids = assistant.file_ids()
        t3 = self.create_testfile_from_string( b"the cat said miaow" ,"test3.txt")
        #test_file3 = SimpleUploadedFile( "test3.txt", b"The cat said miaow. ", content_type="text/plain")
        #self.client.post( url ,  {'file': test_file3}, follow=True)
        #t3 = OpenAIFile.objects.get(name="test3.txt")
        vs1.files.add(t3)
        vs1.save()
        file_ids = vs1.file_ids();
        print(f"VS FILE_IDS AFTER UPDATING t3  NOW {file_ids}")
        file_ids = assistant.file_ids();
        print(f"ASSISTANT  FILE_IDS AFTER UPDATING t3 IS NOW {file_ids}")
        file_ids = assistant.remote_files();
        print(f"ASSISTANT  REMOTE FILE_IDS AFTER UPDATING t3 IS NOW {file_ids}")
        queries =  [ [ 'What color was the cat.','white',True],
                     ['What color was the dog.','black',True],
                     [ 'What did the cat  do?', 'miaow',True],
                     [ 'What did the dog do?', 'bark' ,False],
                     [ 'Please repeat the reply to the first request','black',True],
                 ]
        for  q in queries :
            [ query,response ,truth ] =  q
            print(f"TESTING2 {q}")
            r = thread.run_query(  query=query,  last_messages=2)
            txt = r['assistant']
            assert ( response in txt ) == truth , f"ERROR : in {q}"
            print(f"QUERY {query} -> {txt}")

        print(f"FINALLY2 MESSAGES = {thread.messages}")
        print(f"MESSAGES_LENGTH  = {len( thread.messages)}")
        vs1.delete();
        t1.delete();
        t2.delete();
        t3.delete();
        assistant.delete();
