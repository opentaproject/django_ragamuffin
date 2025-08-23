from django.test import TransactionTestCase as TestCase
from django.apps import AppConfig

import hashlib
import django
import time
import os
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ObjectDoesNotExist
import tiktoken
from django_ragamuffin.utils import print_messages
import openai
from openai import OpenAI
from django.conf import settings
import pytest
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')


django.setup()
from django_ragamuffin.models import OpenAIFile, VectorStore, Assistant,  Thread,  delete_remote_vector_stores, dump_remote_vector_stores, QUser
from django.contrib.auth.models import User

from django.conf import settings
settings.API_APP = 'test'

model = 'gpt-4o-mini'
client = OpenAI() 
import string
import random

settings.API_APP = 'test'

def randstring(tag, length=8):
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    return tag + '-' + ''.join(random.choices(characters, k=length))


class OpenAI(TestCase):
    databases = "__all__"

    @pytest.mark.django_db
    def create_testfile_from_string( self, s , name ):
        print(f"TEST1")
        url = reverse('admin:django_ragamuffin_openaifile_add')  # use your app and model name
        test_file1 = SimpleUploadedFile( name , s , content_type="text/plain")
        csum = hashlib.md5( s  ).hexdigest()
        res = self.client.post( url ,  {'file': test_file1}, follow=True)
        #for file in OpenAIFile.objects.all() :
        #    print(f"ALL FILES = {file} {file.path} ")
        t1 = OpenAIFile.objects.get(name=name)
        return t1

    @pytest.mark.django_db
    def tearDown( self ):
        print(f"TEARDOWN")
        #delete_remote_vector_stores();


    @pytest.mark.django_db
    def setUp( self ):
        print(f"DO SETUP")
        User = get_user_model()
        self.admin_user = User.objects.create_superuser( username='admin', email='admin@example.com', password='adminpass')
        self.client.login(username='admin', password='adminpass')
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.quser = QUser.objects.create(username=self.user.username)

    @pytest.mark.django_db
    def test_user_exists(self):
        print(f"TEST_USER_EXISTS")
        user_exists = User.objects.filter(username='testuser').exists()
        self.assertTrue(user_exists)

    @pytest.mark.django_db
    def test_create_and_delete_file_object(self):
        print(f"TEST_CREATE_AND_DELETE_FILE_OBJECTS")
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




    @pytest.mark.django_db
    def test_create_and_delete_two_openai_file_objects(self):
        print(f"TEST_CREATE_AND_DELETE_TWO_OPENAI..")
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
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
            assert not exists, f"FILE {file_id} was not successfully deleted on the server"
            try :
                tt = OpenAIFile.objects.get(pk=t.pk)
                exists_locally = True
            except ObjectDoesNotExist as e :
                exists_locally = False
            assert not exists_locally, f"File {file_id} still exists locally"
            assert not os.path.exists(path), f"LOCAL FILE PATH {path} DID NOT GET DELETED"




    @pytest.mark.django_db
    def test_create_and_delete_file_globally(self):

        aname = randstring('T1')
        print(f"TEST_CREATE_AND_DELETE_FILE_GLOBALLY ")
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        t1 = self.create_testfile_from_string( b"test1_content_here" ,"test1.txt")
        t2 = self.create_testfile_from_string( b"test2_content_here" ,"test2.txt")
        vsname = randstring('T2')
        vs = VectorStore( name=vsname)
        vs.save()
        vs.files.set([t1,t2])
        vs.save()
        dump_remote_vector_stores("TEST0");
        assert vs.files_ok( ), "TWO FILES NOT OK"
        t2.delete();
        #vs = VectorStore.objects.get(name=vsname)
        #vs.save();
        dump_remote_vector_stores("T1");
        assert vs.files_ok() , "ONE FILE NOT OK"
        t1.delete();
        #vs.save()
        #vs = VectorStore.objects.get(name=vsname)
        dump_remote_vector_stores("TEST2");
        assert vs.files_ok() , "ONE FILE NOT OK"
        vs.delete();
        delete_remote_vector_stores();
        dump_remote_vector_stores("TEST3");

    @pytest.mark.django_db
    def test_clone_vector_store_object(self):
        dump_remote_vector_stores("cloned-2");
        aname = randstring('T3')
        print(f"TEST_CREATE_AND_CLONE_VECTOR_STORE_OBJECT")
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        dump_remote_vector_stores("cloned-1");
        t1 = self.create_testfile_from_string( b"test1_content_here" ,"test1.txt")
        t2 = self.create_testfile_from_string( b"test2_content_here" ,"test2.txt")
        dump_remote_vector_stores("cloned0");
        vsname = randstring('T4')
        vs1 = VectorStore( name=vsname)
        vs1.save()
        print(f"VSPK-A = {vs1.pk} ")# #VS2PK = {vs2.pk}")
        vs1.files.set([t1,t2])
        print(f"VSPK-B = {vs1.pk} ")# #VS2PK = {vs2.pk}")
        vs1.save()
        vs2 = vs1.clone(vsname + '-copy')
        vs2.save();
        for i in [1,2] :
            assert vs1.files_ok(), "VS1 FILES BROKEN"
            assert vs2.files_ok(), "VS2 FILES BROKEN"
            files1 = vs1.files.all();
            files2 = vs2.files.all();
            #print(f"FILES = {files1}")
            assert len( files1 ) == 3 - i , f"FILES = {files1}"
            assert set( files1 ) == set( files2 ) , "FILES NOT THE SAME"
            assert vs1.get_checksum() == vs2.get_checksum(), "CHECKSUMS DIFFER"
            vid1 = vs1.remote_vector_store.vector_store_id 
            vid2 = vs2.remote_vector_store.vector_store_id 
            assert vid1 == vid2 , "REMOTE VECTOR_STORES_DIFFER"
            if i == 1 :
                t1.delete();
        t2.delete();
        vs1.delete();
        vs2.delete();
        delete_remote_vector_stores();
        dump_remote_vector_stores("cloned5");







    @pytest.mark.django_db
    def test_create_and_delete_vector_store_object(self):

        aname = randstring('T5')
        print(f"TEST_CREATE_AND_DELETE_VECTOR_STORE_OBJECT")
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        t1 = self.create_testfile_from_string( b"test1_content_here" ,"test1.txt")
        t2 = self.create_testfile_from_string( b"test2_content_here" ,"test2.txt")
        vsname = randstring('T6')
        vs = VectorStore( name=vsname)
        vs.save()
        vs.files.set([t1,t2])
        vs.save()
        vs.files.add(t1) # REDUNDANT ADD
        vs.save()
        vs.files.add(t2); # REDUNDANT ADD
        vs.save()
        assert vs.files_ok( ), "TWO FILES NOT OK"
        print(f"NEXT REMOVE A {t1} FILE NOW")
        vs.files.remove( t1  )
        print(f"FILES {t1} REMOVED")
        assert vs.files_ok() , "ONE FILE NOT OK"
        vs.files.remove( t2 ) 
        assert vs.files_ok(  ) , "NO FILES SHOULD BE LEFT"
        vs.delete()
        t2.delete();
        t1.delete();
        dump_remote_vector_stores("TEST4");
        delete_remote_vector_stores()


    @pytest.mark.django_db
    def test_create_and_delete_assistant_object(self):
        print(f"TEST_CREATE_AND_DELETE_ASSISTANT_OBJECT")
        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
        url = reverse('admin:django_ragamuffin_openaifile_add')  # use your app and model name
        t1 = self.create_testfile_from_string( b"test1_content_here" ,"test1.txt")
        t2 = self.create_testfile_from_string( b"test2_content_here" ,"test2.txt")
        t3 = self.create_testfile_from_string( b"test3_content_here" ,"test3.txt")
        vsname = randstring('T7')
        aname = randstring('T8')
        assistant = Assistant(name=aname )
        assistant.instructions = 'Answer the questions and make a good guess if the answer is not totally obvious from the context!'
        assistant.save()
        bname = randstring('T9')
        assistantb = Assistant( name=bname)
        assistantb.instructions = 'Answer the questions and make a good guess if the answer is not totally obvious from the context!'
        assistantb.save()
        assistant.add_raw_file(t1)
        assistantb.add_raw_file(t1)
        assert  assistant.files_ok()  , "FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        assistant.add_raw_file(t2)
        assistantb.add_raw_file(t2)
        assert  assistant.files_ok()  , "FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        assistant.add_raw_file(t3)
        assistantb.add_raw_file(t3)
        dump_remote_vector_stores('T3')
        assert  assistant.files_ok()  , "FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        assistant.delete_raw_file(t3)
        assert  assistant.files_ok()  , "FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        assistant.delete_raw_file(t2)
        assert  assistant.files_ok()  , "FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        assistant.delete_raw_file(t1)
        assert  assistant.files_ok()  , "FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        #print(f"NOW ADD VS2")
        #vs.files.set([t1,t2] )
        #vs.save();
        #assistant.save();
        #file_ids = assistant.file_ids()
        #print(f"ASSISTANT FILE_IDS2 IS NOW {file_ids}")
        ##print(f"NTOKENS ASSISTANT = {assistant.ntokens() }")
        #assert assistant.files_ok() , 'FILES_IDS_LOCAL = {file_ids}'
        #print(f"NOW SUBTRACT VS1")
        #assistant.vector_stores.remove(vs1)
        #file_ids = assistant.file_ids()
        #print(f"FILE_IDS IS NOW {file_ids}")
        #assert assistant.files_ok() , 'FILES_IDS_LOCAL = {file_ids}'

        #assistant.vector_stores.remove(vs2)
        #file_ids = assistant.file_ids()
        #print(f"FILE_IDS SHOULD BE EMPTY : IS NOW {file_ids}")
        #assert assistant.files_ok() , 'FILES_IDS_LOCAL = {file_ids}'

        #vs2.delete();
        assistant.delete();
        assistantb.delete();
        dump_remote_vector_stores("TEST5");
        t1.delete();
        t2.delete();
        t3.delete();
        delete_remote_vector_stores();
        dump_remote_vector_stores("TEST6");

    @pytest.mark.django_db(transaction=True)
    def test_create_and_delete_thread(self):
        print(f"TEST_CREATE_AND_DELETE_THREAD")
        import tiktoken


        url = reverse('admin:django_ragamuffin_openaifile_changelist')  # use your app and model name
        response = self.client.get(url)
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


        #vsname = randstring('T4')
        #vs1 = VectorStore(name=vsname)
        #vs1.save()
        #vs1.files.set([t1,t2,t3])
        #vs1.save()
        aname = randstring('T10')
        assistant = Assistant( name=aname ) # , model=settings.AI_MODELS['default'] )
        print(f"CREATED ASSISTANT {aname}")
        assistant.save();
        assistant.instructions = 'Answer the questions as concisely as possible. No need for complete sentences. Make a good guess if the answer is not totally obvious from the context, but if it is not obvious, start your guess with \'It seems like\' !'
        #assistant.save()
        assistant.add_raw_files([t1,t2,t3])
        file_ids = assistant.file_ids()
        assert  assistant.files_ok()  , f"FILE_IDS_LOCAL = {file_ids} not equal to FILE_IDS_REMOTE "
        print(f"ASSITANT REMOTE FILES OK")

        queries =  [ [ 'Q1: What color was the dog.', 'lack',True],
                    [ 'Q2: Please repeat the reply to the first request','lack',True],
                    [ 'Q3: What color was the cat.', 'hite',True],
                    [ 'Q4: What did the dog do?', 'arked',True] , 
                    [ 'Q4: What did the cat do?', 'iaow',False],
                    [ 'Q6: Please repeat the reply to the first request','lack',True]
                        ]

        thread = Thread(name=aname,assistant=assistant,user=self.quser)
        thread.messages = []
        #thread.messages = None
        thread.save()
        for  q in queries :
            print(f"Q {q}")
            [ query,response , truth ] =  q
            r = thread.run_query(  query=query,  last_messages=99)
            txt = r['assistant']
            print(f"TXT = {txt}")
            assert ( response in txt ) == truth , f"ERROR : in {q} TXT={txt} "


        print(f"DELETE_RAW_FILE")
        assistant.delete_raw_file(t3)
        print(f"D2")
        t3.delete();
        print(f"D3")
        #file_ids = assistant.file_ids()
        #print(f"D4")
        t3 = self.create_testfile_from_string( b"the cat said miaow" ,"test3.txt")
        #thread.messages[-1]['response_id'] = None
        #thread.save()
        #test_file3 = SimpleUploadedFile( "test3.txt", b"The cat said miaow. ", content_type="text/plain")
        #self.client.post( url ,  {'file': test_file3}, follow=True)
        #t3 = OpenAIFile.objects.get(name="test3.txt")
        assistant.add_raw_file(t3)
        #threads = assistant.threads.all();
        #for thread in threads :
        #    thread.messages = []
        #file_ids = vs.file_ids();
        #file_ids = assistant.file_ids();
        #file_ids = assistant.remote_files();
        queries =  [ 
                    [ 'Q7: What color was the cat.','hite',True],
                    [ 'Q8: What color was the dog.','lack',True],
                    [ 'Q9: What did the cat  do?', 'iaow',True],
                    [ 'Q10: What was the first query in the conversation','cat',True ],
                    [ 'Q11: What did the dog do?', 'arked' ,False],
                 ]
        clear = True
        for  q in queries :
            [ query,response ,truth ] =  q
            r = thread.run_query(  query=query,  clear=clear, last_messages=4)
            clear = False
            txt = r['assistant']
            print(f" Q={q} TXT={txt}")
            if not truth == None :
                assert ( response in txt ) == truth , f"ERROR : in {q}"

        #vs.delete();
        t1.delete();
        t2.delete();
        t3.delete();
        print(f"NOW DELETE ASSISTANT {aname}")
        assistant.delete();
        print(f"DELETED ASSISTANT {aname}")
        dump_remote_vector_stores("FINAL1");
        delete_remote_vector_stores();
        dump_remote_vector_stores("FINAL2");
