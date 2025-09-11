from django.db import models
from openai import OpenAI
from pathlib import Path
from django.db import transaction
import random, string
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
import shutil
from .mathpix import mathpix
from .remote_calls import run_remote_query

import logging
import time
import tiktoken
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import hashlib
import openai
from django.db.models.signals import m2m_changed, pre_delete, post_delete
from django.dispatch import receiver
from openai._exceptions import NotFoundError
import re

import os
logger = logging.getLogger(__name__)

upload_storage = FileSystemStorage(location="/subdomain-data/query", base_url="/media/")

from openai import OpenAIError, RateLimitError, APIError, Timeout

def randstring(tag, length=8):
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    return tag + '-' + ''.join(random.choices(characters, k=length))


def dump_remote_vector_stores(s='') :
    print(f"DUMP REMOTE_VECTOR_STORES {s}\nvvvvvv")
    remote_vector_stores = RemoteVectorStore.objects.all();
    for remote_vector_store in remote_vector_stores :
        print(f"REMOTE_VECTOR_STORE = cs={remote_vector_store.checksum} id={remote_vector_store.vector_store_id} pks={remote_vector_store.vector_stores_pks()}")
    print(f"^^^^^^")


def remote_wait_for_vector_store_delete(vector_store_id, timeout=settings.MAXWAIT, interval=2):
    print(f"WAIT_FOR_VECTOR_STORE_DELETE {vector_store_id}")
    client = OpenAIClient()
    start_time = time.time()
    while time.time() - start_time < timeout:
        print(f"WAITIN DELETE")
        try:
            client.vector_stores.retrieve(vector_store_id)
        except NotFoundError:
            return
        time.sleep(interval)

    raise TimeoutError(f"Vector store {vector_store_id} deletion not confirmed within timeout.")



def remote_wait_for_vector_store_ready(client, vector_store_id, timeout=settings.MAXWAIT):
    print(f"WAIT_FOR_VECTOR_STORE_READY {vector_store_id}")
    start_time = time.time()
    client = OpenAIClient()
    i = 0;
    while True:
        i = i + 1;
        print(f"WATING1 {i}")
        vs = client.vector_stores.retrieve(vector_store_id=vector_store_id)
        if vs.status == "completed":
            return vs
        elif vs.status == "failed":
            raise RuntimeError("❌ Vector store creation failed.")
        elif time.time() - start_time > timeout:
            raise TimeoutError("⏱️ Timeout: Vector store not ready in time.")
        time.sleep(10)
    i = 0;
    imax = settings.MAXWAIT / interval;
    while i < imax :
        file_list = client.vector_stores.files.list(vector_store_id=vector_store_id)
        statuses = [file.status for file in file_list.data]
        if all(status == "completed" for status in statuses):
            break
        elif any(status == "failed" for status in statuses):
            raise Exception(f"❌ Some files failed to process! {statuses}")
        else:
            time.sleep(5)  # Wait before polling again
        i = i + 1 ;
    assert i < imax , "VECTOR STORE READY TIMED OUT"


def validate_file_extension(value):
    ext = os.path.splitext(value.name)[-1].lower()
    if ext not in ['.md','.txt','.pdf','.tex']:
        raise ValidationError(f"Unsupported file extension '{ext}'.")

def hashed_upload_to(instance, filename):
    dirname = '.'.join( instance.file.name.split('.')[:-1] )
    os.makedirs(os.path.join( settings.OPENAI_UPLOAD_STORAGE, dirname ) ,  exist_ok=True)
    return os.path.join( dirname, instance.file.name )

def create_or_retrieve_vector_store( name , files) :
    vs = VectorStore.objects.filter(name=name).all()
    if not vs :
        vs = VectorStore(name=name)
        vs.save();
        vs.files.set(files)
        vs.save()
    else :
        vs = vs[0]
    return vs

def create_or_retrieve_assistant( name , vs ):
    assistants  = Assistant.objects.filter(name=name).all()
    if not assistants :
        assistant = Assistant(name=name)
        assistant.save()
    else :
        assistant = assistants[0]
    assistant.vector_stores.add(vs)
    assistant.save();
    return assistant

def create_or_retrieve_thread( assistant, name, user ) :
    print(f"CREATE_OR_RETRIEVE_THREAD {assistant} {name} {user}")
    if user.pk :
        threads = Thread.objects.filter(name=name,user=user)
    else :
        user = None
    threads = Thread.objects.filter(name=name,user=user)
    if not threads :
        thread = Thread(name=name,user=user)
    else :
        thread = threads[0]
    thread.assistant = assistant
    thread.save()
    return thread







def upload_or_retrieve_openai_file( name ,src ):
    os.makedirs( os.path.join( settings.OPENAI_UPLOAD_STORAGE, name ), exist_ok=True )
    dst = os.path.join(os.path.join( settings.OPENAI_UPLOAD_STORAGE, name ), src)
    name = dst.split('/')[-1];
    ts = OpenAIFile.objects.filter(name=name)
    if not ts :
        if not src == dst :
            shutil.copy2(src, dst)
        t1 = OpenAIFile(file=dst)
        t1.name = name
        t1.save();
    else :
        t1 = ts[0]
    return t1

def split_long_chunks(chunks, max_len=800):
    new_chunks = []
    for chunk in chunks:
        words = chunk["content"].split()
        for i in range(0, len(words), max_len):
            part = ' '.join(words[i:i+max_len])
            new_chunks.append({
                "heading": chunk["heading"],
                "content": part
            })
    return new_chunks

def chunk_mmd(linestring):
    chunks = []
    current_chunk = []
    current_heading = ''
    lines  = linestring.splitlines()

    for line in lines:
        if re.match(r'^#{1,6} ', line) or line == ''  or re.match(r'\\section', line ) :
            if re.match(r'\\section',line) :
                current_heading = line.strip() 
            if current_chunk:
                chunks.append({
                    "heading": current_heading,
                    "content": ''.join(current_chunk).strip()
                })
            current_chunk = []
        else:
            current_chunk.append(line)

    if current_chunk:
        chunks.append({
            "heading": current_heading,
            "content": ''.join(current_chunk).strip()
        })

    s = f"{chunks}"
    chunks = split_long_chunks( chunks );
    s = re.sub(r"},","},\n",s)
    return s.encode('utf-8')





class QUser(models.Model ):
    username = models.CharField(max_length=255,blank=True)
    is_staff = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username}"



class OpenAIClient( OpenAI ):



    def __init__(self, **kwargs):
        super().__init__(api_key=settings.AI_KEY, **kwargs)

    def get_or_update_remote_vector_store(self, vs , old_checksum=None,old_file_ids=[]):
        new_checksum = vs.get_checksum();
        checksum = vs.get_checksum()
        new_checksum = checksum
        new_file_ids =  [i[0] for i in  vs.files.values_list('file_ids', flat=True)  ]
        pks = [ i.pk for i in vs.files.all() ]
        remote_vector_stores = RemoteVectorStore.objects.filter(checksum=new_checksum).all()
        if remote_vector_stores :
            remote_vector_store = remote_vector_stores[0]
            new_vector_store_id = remote_vector_store.vector_store_id
            vs.remote_vector_store = remote_vector_stores[0]
            new_vector_store_id =    remote_vector_store.vector_store_id
            vs.vsid = new_vector_store_id
            vs.remote_vector_store = remote_vector_store
            vs.save();
            return new_vector_store_id
        else :
            remote_vector_stores = RemoteVectorStore.objects.filter(checksum=old_checksum).all()
            if  False and remote_vector_stores :
                remote_vector_store = remote_vector_stores[0]
                vector_store_id = remote_vector_store.vector_store_id
                deleted_files = list( set( old_file_ids) - set( new_file_ids) )
                for f in deleted_files:
                    try :
                        self.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=f)
                        remote_wait_for_vector_store_ready(self, vector_store_id, timeout=settings.MAXWAIT)
                    except openai.NotFoundError as e:
                        print(f"File {f} not found in vector store {vector_store_id}: {e}")
                        continue
                added_files = list( set( new_file_ids) - set( old_file_ids) )
                vs.checksum = new_checksum
                if not added_files == []:
                    self.vector_stores.file_batches.create( vector_store_id=vector_store_id, file_ids=added_files, 
                        metadata={"api_app" : settings.API_APP, "api_key": settings.AI_KEY[-8:] , "checksum" : new_checksum } )
                    remote_wait_for_vector_store_ready(self, vector_store_id, timeout=settings.MAXWAIT)
                remote_vector_store.checksum = new_checksum;
                new_vector_store_id = remote_vector_store.vector_store_id
                remote_vector_store.save();

            else :
                name = checksum
                print(f"AI_KEY = {settings.AI_KEY}")
                new_remote_vector_store = self.vector_stores.create(name=name,file_ids=new_file_ids , 
                    metadata={"api_app" : settings.API_APP, "api_key": settings.AI_KEY[-8:] , "checksum" : new_checksum } )
                remote_wait_for_vector_store_ready(self, new_remote_vector_store.id, timeout=settings.MAXWAIT)
                rvs = new_remote_vector_store
                new_remote_vector_store, created   = RemoteVectorStore.objects.get_or_create(checksum=checksum,vector_store_id=rvs.id);
                new_remote_vector_store.save();
                vs.vector_store_id = rvs.id
                vs.remote_vector_store = new_remote_vector_store
                vs.vsid = rvs.id
                vs.save()
                new_vector_store_id = rvs.id
        return new_vector_store_id


    def delete_vector_store(self, vs, vector_store_id) :
        assert vs.get_vector_store_id() == vector_store_id, "FAIL1"
        try:
            vector_store_id = vs.get_vector_store_id()
        except AttributeError as e:
            print(f"Failed to get vector_store_id: {e}")
            raise
        checksum = vs.get_checksum()
        return True


    def vector_stores_retrieve(self, vs, vector_store_id) :
        vector_store_id = vs.get_vector_store_id()
        checksum = vs.get_checksum()
        return self.vector_stores.retrieve(vector_store_id)


    def vector_stores_files_list(  self, vs, vector_store_id ):
        assert vs.get_vector_store_id() == vector_store_id, "FAIL3"
        vector_store_id = vs.get_vector_store_id()
        checksum = vs.get_checksum()
        vector_store_files = self.vector_stores.files.list( vector_store_id=vector_store_id)
        assert checksum == vs.get_checksum() , "FAIL3b"
        return vector_store_files

    def vector_stores_create( self,  name, metadata ):
        name = randstring('vs' + name )
        vector_store = self.vector_stores.create(name=name,metadata=metadata )
        remote_wait_for_vector_store_ready( self, vector_store.id )
        return vector_store

    def delete_file_from_vs( self,  vs, vector_store_id, file_id ):
        assert vs.get_vector_store_id() == vector_store_id, "FAIL4"
        vector_store_id = vs.get_vector_store_id()
        checksum = vs.get_checksum()
        try :
            self.vector_stores.files.delete(vector_store_id=vector_store_id,file_id=file_id)
            remote_wait_for_vector_store_ready(self, vector_store_id, timeout=settings.MAXWAIT)
        except  openai.NotFoundError as e: 
            return False
        try :
            self.files.delete( file_id )
        except  openai.NotFoundError as e: 
            return False
        assert checksum == vs.get_checksum() , "FAIL4b"
        return True

    def delete_file_globally( self , file_id ):
        try :
            print(f"DELETE GLOBALLY {file_id}")
            self.files.delete(file_id)
            return True
        except Exception as err :
            print(f"GLOBAL DELETION ERROR {str(err)}")
            return False

    def vector_stores_files_delete( self, vs, vector_store_id, file_id ):
        assert vs.get_vector_store_id() == vector_store_id, "FAIL5"
        checksum = vs.get_checksum()
        vector_store_id = vs.get_vector_store_id()
        self.vector_stores.files.delete( vector_store_id=vector_store_id , file_id=file_id)
        remote_wait_for_vector_store_ready(self, vector_store_id, timeout=settings.MAXWAIT)
        assert checksum == vs.get_checksum() , "FAIL5b"
        return vector_store_id

    def vector_stores_files_create( self, vs, vector_store_id , file_id ):
        assert vs.get_vector_store_id() == vector_store_id, "FAIL6"
        checksum = vs.get_checksum()
        vector_store_id = vs.get_vector_store_id()
        self.vector_stores.files.create( vector_store_id=vector_store_id , file_id=file_id , 
             metadata={"api_app" : settings.API_APP, "api_key": settings.AI_KEY[-8:] , "checksum" : new_checksum }  )
        remote_wait_for_vector_store_ready(self, vector_store_id=vector_store_id, timeout=settings.MAXWAIT)
        assert checksum == vs.get_checksum() , "FAIL6b"
        return vector_store_id





class OpenAIFile(models.Model) :
    date = models.DateTimeField(auto_now=True)
    checksum = models.CharField(blank=True, max_length=255)
    name = models.CharField(max_length=255,blank=True)
    path = models.CharField(max_length=255,blank=True)
    file_ids = models.JSONField(default=list, null=True, blank=True)
    file = models.FileField( max_length=512, upload_to=hashed_upload_to, storage=upload_storage, validators=[validate_file_extension] )
    ntokens = models.IntegerField(default=0,null=True, blank=True)
    

    def __str__(self):
        return f"{self.name}"



    def save( self, *args, **kwargs ):
        is_new = self._state.adding  and not self.pk
        name =  f"{self.file}".split('/')[-1]
        super().save(*args, **kwargs)  # Save first, so file is processed
        if ( is_new and self.file ):
            fn = self.file.name 
            self.name = self.file.name.split('/')[-1]
            src = self.file.path
            extension = src.split('.')[-1];
            if extension == 'pdf' :
                txt = mathpix( src ,format_out='mmd')
            else :
                txt = ( open(src,'rb').read() ).decode('utf-8')
            if extension == 'pdf' :
                chunks = chunk_mmd(txt)
            else :
                chunks = txt.encode()
            chunkdir = os.path.join( os.path.dirname( src ), 'chunks')
            os.makedirs( chunkdir, exist_ok=True )
            srcbase = Path( os.path.basename(src) )
            if extension == 'pdf' :
                jbase = srcbase.with_suffix('.json')
            else :
                jbase = srcbase.with_suffix('.' + extension )
            dst = os.path.join( chunkdir, jbase )
            if chunks :
                open( dst, "wb").write( chunks)
            else :
                shutil.copy2(src, dst)
            data = self.file.read()
            self.checksum = hashlib.md5(data).hexdigest()
            uploaded_file = openai.files.create( file=open( dst, "rb"), purpose="assistants"  )
            self.file_ids = [uploaded_file.id ]
            self.path = os.path.dirname( self.file.path )

            def get_ntokens( file_path):
                valid_text = ''
                encoding = tiktoken.get_encoding('cl100k_base')
                with open(file_path, "rb") as f:
                    for line in f:
                        try:
                            decoded = line.decode("utf-8")
                            valid_text += decoded
                        except UnicodeDecodeError:
                            continue  # Skip invalid lines
                tokens = encoding.encode(valid_text)
                return len( tokens )



            self.ntokens = get_ntokens( dst )
            self.name = name
            super().save(*args, **kwargs) # Then update with true hashed path



@receiver(pre_delete, sender=OpenAIFile)
def custom_delete_openaifile(sender, instance, **kwargs):
    pk = instance.pk
    vst = instance.vector_stores.all();
    client = OpenAIClient()
    if hasattr( instance, "file_ids") :
        file_ids = instance.file_ids
        for file_id in file_ids :
            o = OpenAIFile.objects.get(file_ids=[file_id])
            for vs in vst :
                vector_store_id = vs.get_vector_store_id()
                old_checksum = vs.checksum
                vs.files.remove( o )
                vs.save(update_fields=['checksum'] );
                vs.checksum = vs.get_checksum();
                vsid =  client.get_or_update_remote_vector_store( vs )
                vs.vsid = vsid
                vs.save()
                new_checksum = vs.checksum
                assert not new_checksum == old_checksum, f'CHECKSUMS UNCHANGED {old_checksum} for {vector_store_id}'

    try :
        client.delete_file_globally( file_id )
        shutil.rmtree(instance.path)
    except Exception as e:
        logger.error(f" FILE/ {instance.path} DOES NOT EXIST")
        return



class RemoteVectorStore( models.Model ) :
    checksum = models.CharField(blank=True, max_length=255,unique=True)
    vector_store_id  =  models.CharField(blank=True, max_length=255 )

    def vector_stores_pks(self ):
        pks = [ i.pk for i in self.vector_stores.all() ]
        return pks
    def slow_file_names(self):
        client = OpenAIClient()
        vs_files = client.vector_stores.files.list(vector_store_id=self.vector_store_id)
        names = [];
        for vs_file in vs_files.data:
            file_id = vs_file.id
            file_obj = client.files.retrieve(file_id)
            names.append(file_obj.filename)
        return names

    def file_names(self):
        vss = VectorStore.objects.filter(checksum=self.checksum).all();
        names = [];
        for v in vss :
            names.extend( v.file_names() );
        return names





class VectorStore( models.Model ):
    checksum = models.CharField(blank=True, max_length=255)
    vsid = models.CharField(max_length=255,blank=True)
    name =  models.CharField(max_length=255 ) # ,unique=True)
    files = models.ManyToManyField( OpenAIFile , related_name='vector_stores')
    remote_vector_store = models.ForeignKey( 
        RemoteVectorStore ,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='vector_stores',
        )




    def __str__(self):
        return f"{self.name}"

    def get_vector_store_id( self ):
        return self.remote_vector_store.vector_store_id


    def clone( self, newname, *args, **kwargs):
        vector_stores = VectorStore.objects.filter( name=newname).all();
        if vector_stores :
            vector_store = vector_stores[0]
        else :
            vector_store = VectorStore(name=newname)
            vector_store.save();
        vector_store.files.set(self.files.all() )
        vector_store.remote_vector_store = self.remote_vector_store
        vector_store.checksum = self.checksum
        vector_store.save();
        return vector_store;


    def file_ids(self, *args, **kwargs ):
        files = self.files
        ids = []
        for f in files.all():
            ids.extend( f.file_ids )
        return ids

    def file_names(self, *args, **kwargs ):
        files = self.files
        n = []
        for f in files.all():
            n.append( f.name)
        return n


    def ntokens( self, *args, **kwargs ):
        files = self.files
        n = 0;
        for f in files.all():
            n = n + f.ntokens
        return n



    def file_pks(self, *args, **kwargs ):
        pks = []
        files = self.files
        for f in files.all():
            pks.append(f.pk)
        return pks

    def file_checksums(self, *args, **kwargs ):
        files = self.files
        if not files :
            return [];
        checksums = []
        for f in files.all():
            checksums.append(f.checksum)
        checksums = list( set( checksums) )
        checksums.sort()
        return checksums

    def old_save(self, *args, **kwargs):
        is_new = not self.pk
        if is_new :
            super().save(*args, **kwargs)
        checksum = self.get_checksum()
        client = OpenAIClient()
        if is_new:
            try:
                vector_store_id = client.get_or_update_remote_vector_store(self)
                self.vsid = vector_store_id
            except openai.OpenAIError as e:
                print(f"OpenAIError in get_or_update_remote_vector_store: {e}")
                raise
            except Exception as e:
                print(f"Unexpected error in get_or_update_remote_vector_store: {e}")
                raise
        super().save(*args, **kwargs)

    def save(self, *args, **kwargs):
        is_new = self._state.adding and not self.pk


        self.checksum = self.get_checksum()
        client = OpenAIClient()

        if is_new:
            vector_store_id = client.get_or_update_remote_vector_store(self)
            self.vsid = vector_store_id

        super().save(*args, **kwargs)


    def get_checksum(self):
        cksums = self.file_checksums();
        ckstring = ''.join(cksums).encode()
        checksum = hashlib.md5(ckstring).hexdigest()
        return checksum

    def files_ok( self, *args, **kwargs) :
        vs = VectorStore.objects.get(pk=self.pk)
        file_ids = vs.file_ids()
        vector_store_id = vs.get_vector_store_id()
        client = OpenAIClient()
        vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store_id)
        remote_ids = []
        for f in vector_store_files:
            remote_ids.append( f.id)
        return set( file_ids) == set( remote_ids) 

    def save( self, *args, **kwargs ):
        is_new = self._state.adding and not self.pk
        if is_new :
            super().save(*args,**kwargs)
        checksum = self.get_checksum();
        client = OpenAIClient()
        if is_new :
            vector_store_id = client.get_or_update_remote_vector_store( self )
            self.vsid = vector_store_id
        super().save(*args,**kwargs)



@receiver(pre_delete, sender=RemoteVectorStore)
def custom_delete_remote_vector_store(sender, instance, **kwargs):
    return
    client = OpenAIClient();
    vector_store_id = instance.vector_store_id
    try :
        client.vector_stores.delete( vector_store_id )
        remote_wait_for_vector_store_delete(vector_store_id, timeout=settings.MAXWAIT, interval=2)
    except Exception as e :
        print(f"FAILED REMOTE_VECTOR_STORE_CLIENT_DELETE {vector_store_id} {str(e)} ")
        pass




def get_current_model( user=None ):
    if user == None :
        model = settings.AI_MODELS['default']
    elif user.is_staff: 
        model = settings.AI_MODELS['staff']
    else :
        model = settings.AI_MODELS['default']
    return model


DEFAULT_INSTRUCTIONS = """Answer only questions about the enclosed document. 
    Do not offer helpful answers to questions that do not refer to the document. 
    Be concise. 
    If the question is irrelevant, answer with "That is not a question that is relevant to the document." \n 
    For images use created by mathpix, not the sandbox link created by openai. 
    Since it is visible, dont  say something like "You can view the picture ... ". 
    If a link does not exist, just say that such an image does not exist. '
    """


class ModeChoice(models.Model):
    key = models.SlugField(max_length=50, unique=True)   # e.g. "examiner"
    label = models.CharField(max_length=100)             # e.g. "Examiner"

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


class Mode(models.Model):
    choice = models.ForeignKey(ModeChoice, on_delete=models.PROTECT)
    text = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.choice.label}"

    @classmethod
    def get_text_for(cls, key):
        try:
            return cls.objects.get(choice__key=key).text
        except cls.DoesNotExist:
            return ""


class Assistant( models.Model ):
    name =   models.CharField(max_length=255,blank=True)
    instructions = models.TextField(blank=True,null=True)
    vector_stores = models.ManyToManyField( VectorStore ,blank=True,related_name='assistants')
    assistant_id = models.CharField(max_length=255,blank=True, null=True)
    json_field = models.JSONField( default=dict ,  blank=True, null=True)
    temperature = models.FloatField(null=True, blank=True)
    clear_threads = models.BooleanField(default=False)
    mode_choice = models.ForeignKey( "ModeChoice", on_delete=models.PROTECT, related_name="assistant_set", default=None, null=True, blank=True)
    



    def __str__(self):
        return f"{self.name}"


    def path(self) :
        p = '/'.join( self.name.split('.') )
        return p

    def get_all_threads(self) :
        threads = Thread.objects.filter(name=self.name).all()
        return threads


    def add_file(self,  filename, uploaded_file ):
        name = '.'.join( filename.split('.')[:-1])
        filename = f"{name}/{filename}"
        upload_storage.save(filename , uploaded_file)
        file_url = settings.MEDIA_URL + upload_storage.url(filename)
        src = settings.OPENAI_UPLOAD_STORAGE + '/' + filename
        t1 = upload_or_retrieve_openai_file( name, src )
        self.add_raw_file( t1 )
        return file_url

    def add_file_by_name(self, full_path):
        """Copy a local file into storage and register it.

        - `full_path`: absolute path to a local file to import.
        - Copies the file into `OPENAI_UPLOAD_STORAGE/<stem>/<basename>`
          (matching the pattern used by `add_file`).
        - Returns a media URL to the stored file.
        """
        if not os.path.isabs(full_path) or not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {full_path}")

        base = os.path.basename(full_path)
        stem = '.'.join(base.split('.')[:-1]) or base
        relpath = f"{stem}/{base}"

        dst = os.path.join(settings.OPENAI_UPLOAD_STORAGE, relpath)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(full_path, dst)

        # Register with our OpenAIFile model and link to vector store
        t1 = upload_or_retrieve_openai_file(stem, dst)
        self.add_raw_file(t1)

        file_url = settings.MEDIA_URL + upload_storage.url(relpath)
        return file_url

    def add_raw_files(self,  t1 ):
        vss = self.vector_stores.all();
        if len( vss ) == 0 :
            vs = VectorStore( name=self.name);
            vs.save();
            self.vector_stores.add(vs)
        else :
            vs = vss[0]
        for t in t1 :
            self.add_raw_file( t )
        return 


    def add_raw_file(self, t1):
        vss = self.vector_stores.all()
        if len(vss) == 0:
            vs = VectorStore(name=self.name)
            vs.save()
            self.vector_stores.add(vs)
            self.save()
        else:
            vs = vss[0]
        try:
            vs.files.add(t1)
            vs.save()
            self.vector_stores.set([vs])
            self.save()
        except Exception as err:
            dump_remote_vector_stores("ERROR IN ADD_RAW_FILE")
        assistant_id = self.assistant_id
        self.save();
        return 

    def delete_raw_file( self, file ):
        vss = self.vector_stores.all()
        for vs in vss :
            vs.files.remove(file)
            vs.save();
        self.vector_stores.set([vs])
        assistant_id = self.assistant_id 
        threads = self.threads.all();
        for thread in threads :
            print(f"ASSISTANT DELETE_RAW_FILE {thread} ")
            thread.clear = True;
            thread.save(update_fields=['clear']);
        self.save();
        return




    def delete_file( self, deletion ):
        deletion = int( deletion )
        vsall = self.vector_stores.all();
        for vs in vsall :
            file = OpenAIFile.objects.get(pk=deletion);
            vs.files.remove(file)

    def parent( self ):
        name = '.'.join( self.name.split('.')[:-1] )
        assistants = Assistant.objects.filter(name=name);
        if assistants :
            return assistants[0]
        else :
            return None

    def children( self ):
        name  = self.name;
        pattern = r'^%s\.[^.]+$' % name
        children = Assistant.objects.filter(name__regex=pattern).only('pk','name')
        res = [ {obj.pk : obj.name} for obj in children ]
        return res

    def get_instructions( self ): # GET THE LAST INSTRUCTIONS IN THE TREE
        if self.instructions :
            self.instructions = self.instructions.strip();
        appended = ''
        instructions = ''
        if self.instructions :
            do_append = self.instructions.split()[0].strip().rstrip(':').lower()  == 'append'
            if do_append :
                appended = ''.join( re.split(r'(\s+)', self.instructions)[1:] )
                instructions = ''
            else :
                instructions = self.instructions
        a = self;
        p = a.parent();
        if p :
            i = 0;
            while not p.parent() == None and instructions == ''  and i < 4 :
                p = p.parent();
                instructions = p.get_instructions();
                i = i + 1 ;
        if instructions == '':
            if not self.mode_choice :
                instructions = DEFAULT_INSTRUCTIONS 
            else :
                instructions = Mode.objects.get(choice=self.mode_choice).text
        if appended :
            instructions = instructions + "\n" + appended
        return instructions


    def get_vector_stores( self ): # GET THE LAST INSTRUCTIONS IN THE TREE
        print(f"ASSISTAN GET VETOR STORES")
        p = self;
        vector_stores = [] # VectorStore.objects.none()
        if p :
            i = 0;
            while not p.parent() == None and len( vector_stores ) == 0 :
                p = p.parent();
                vector_stores = p.get_vector_stores();
                i = i + 1 ;
        print(f"VECTOR_STORES INITIALL IS {vector_stores}")
        if self.vector_stores.all() :
            print(f"RETURN IMMEDIATELY add {vector_stores} + {self.vector_stores.all() }")
            vector_stores = vector_stores + list( self.vector_stores.all() )
        print(f"RETURNING {vector_stores}")
        return vector_stores

            

    def save( self, *args, **kwargs ):
        is_new = self._state.adding and not self.pk
        super().save(*args,**kwargs)
        if is_new :
            characters = string.ascii_letters + string.digits  # a-zA-Z0-9
            h = ''.join(random.choices(characters, k=8))
            self.assistant_id = 'myasst_' + h
            super().save(update_fields=['assistant_id'])
            vss = VectorStore.objects.filter( name=self.name);
            if vss :
                vs = vss[0]
                self.vector_stores.set([vs])
                self.save();
                transaction.on_commit(self.save ) 

        else :
            super().save( *args, **kwargs)


    def clone_stub( self, newname ) :
        print(f"CLONED_STUB  {newname}")
        vss = self.vector_stores.all();
        #if vss :
        #    vs = vss[0]
        #    vnew  = vs.clone( newname )
        #else :
        #    vsnews = VectorStore.objects.filter(name=newname).all()
        #    if vsnews :
        #        vnew = vsnews[0]
        #    else :
        #        vnew = VectorStore(name=newname)
        #        vnew.save();
        assistant = Assistant(name=newname)
        #assistant.instructions = self.instructions;
        assistant.json_field = self.json_field;
        assistant.temperature = self.temperature;
        assistant.save();
        #assistant.vector_stores.set([vnew.pk])
        #assistant.save();
        return assistant;




    def clone( self, newname ) :
        print(f"CLONED {newname}")
        vss = self.vector_stores.all();
        if vss :
            vs = vss[0]
            vnew  = vs.clone( newname )
        else :
            vsnews = VectorStore.objects.filter(name=newname).all()
            if vsnews :
                vnew = vsnews[0]
            else :
                vnew = VectorStore(name=newname)
                vnew.save();
        assistant = Assistant(name=newname)
        assistant.instructions = self.instructions;
        assistant.json_field = self.json_field;
        assistant.temperature = self.temperature;
        assistant.save();
        assistant.vector_stores.set([vnew.pk])
        assistant.save();
        return assistant;

    

    def ntokens( self, *args, **kwargs ):
        vs = self.vector_stores.all()
        n = 0;
        for v in vs :
            for vf in v.files.all():
                n = n + vf.ntokens 
        return n


    def file_pks( self, *args, **kwargs ):
        vs = self.get_vector_stores()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.append( vf.pk )
        f = list( set( f) )
        return f

    def file_ids(self, *args, **kwargs ):
        vs = self.get_vector_stores()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.extend( vf.file_ids )
        f = list( set( f) )
        return f

    def files( self, *args, **kwargs ):
        vs = self.get_vector_stores()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.append( ( vf.pk , vf.name ) )
        return f

    def local_files( self, *args, **kwargs ):
        vs = self.vector_stores.all();
        f = []
        for v in vs :
            for vf in v.files.all():
                f.append( ( vf.pk , vf.name ) )
        return f








    def file_names( self, *args, **kwargs ):
        vs = self.get_vector_stores()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.append( vf.name )
        f = list( set( f) )
        return f

    def remote_files( self, *args, **kwargs ) :
        if True : # not DEBUG :
            return self.file_ids( args, kwargs )
        client = OpenAIClient()
        assistant = self
        vss = self.get_vector_stores();
        for vs in vss :
            files = vs.files;
        assistant_id = assistant.assistant_id
        remote_ids = [];
        vector_store_ids = [ item.vsid for  item in vss ]
        files = [];
        for vector_store_id in vector_store_ids :
            vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store_id)
            for f in vector_store_files:
                remote_ids.append( f.id)
        return remote_ids


    def get_remote_vector_stores( self, *args, **kwargs ):
        client = OpenAIClient()
        assistant = self
        vss = self.get_vector_stores();
        remote_ids = [ item.vsid for item in vss ]
        return remote_ids 



        

    def files_ok( self,*args, **kwargs):
        assistant = self
        vss = assistant.vector_stores.all();
        file_ids = assistant.file_ids();
        remote_ids = assistant.remote_files();
        return set( remote_ids) == set( file_ids )





class Thread(models.Model) :
    name = models.CharField(max_length=255)
    date = models.DateTimeField(auto_now=True)
    thread_id = models.CharField(max_length=255,blank=True)
    messages = models.JSONField( default=dict ,  blank=True, null=True)
    assistant = models.ForeignKey(Assistant,  null=True, on_delete=models.SET_NULL,related_name="threads")
    user = models.ForeignKey(QUser, null=True, on_delete=models.SET_NULL, blank=True )
    max_tokens = models.IntegerField( blank=True, null=True)
    clear = models.BooleanField(default=False)




    
    


    def __str__(self):
        return f"{self.name}"

    def mark_clear(self) :
        self.clear = True
        self.save(clear=True, update_fields=['clear'] );


    def save( self, clear=False, *args, **kwargs ):
        old_clear = self.clear
        is_new = self._state.adding  and not self.pk
        self.messages = self.messages
        client = OpenAIClient();
        super().save(*args, **kwargs)  # Save first, so file is processed
        if is_new  :
            characters = string.ascii_letters + string.digits  # a-zA-Z0-9
            h = ''.join(random.choices(characters, k=8))
            thread_id ='mythread1_' + h
            self.thread_id = thread_id
            self.messages = []
            super().save(*args, **kwargs) # Then update with true hashed path
        else :
            if clear  or old_clear :
                if self.messages :
                    self.messages[-1]['previous_response_id'] = None
                    self.clear = False
            super().save(*args, **kwargs)





    def run_query( self, clear=False , *args, **kwargs  ):
        more_instructions = kwargs.get('instructions', '')
        last_messages = kwargs.get('last_messages',settings.LAST_MESSAGES)
        max_num_results = kwargs.get('max_num_results',settings.MAX_NUM_RESULTS)
        query= kwargs['query']
        if len( query.strip() )  == 0 :
            msg =  {'user' : query, 'assistant' : 'blank!',
                'ntokens' : 0,
                'summary' : 'summary' ,
                    }
            return msg

        now = time.time();
    
        """ last_messages is either None for auto or an integer for length of thread history to keep at OpenAI. 
        The entire history is kept in the local database"""
        assistant = self.assistant
        if not assistant :
            assistants = Assistant.objects.filter(name=self.name ).all()
            assistant = assistants[0]
        threads = assistant.get_all_threads();
        assistant_id = assistant.assistant_id
        vector_stores = assistant.get_vector_stores()
        vss = [ item.vsid for item in vector_stores ]
        print(f"VECTOR_STORES = {vss}")
        instructions = assistant.get_instructions() + '\n' + more_instructions
        print(f"INSTRUCTIONS IN QUERY IS {instructions}")
        #vss = [];
        #for vs in vector_stores :
        #    vss.append(vs.vsid)
        thread = self
        thread_id = thread.thread_id
        print(f"VSS = {vss}")
    
        encoding = tiktoken.get_encoding("cl100k_base")

        if thread.max_tokens :
            max_tokens = thread.max_tokens
        else :
            max_tokens = settings.MAX_TOKENS
        timeout = settings.MAXWAIT
        if self.messages :
            previous_response_id = self.messages[-1].get('response_id',None)
        else :
            previous_response_id = None
        if clear or self.clear :
            previous_response_id = None
            self.clear = False
        user = self.user
        model = get_current_model(self.user)
        context = {'openai' : openai, 'instructions' : instructions, 'model' : model, 
                    'thread_id': thread_id, 'assistant_id' : assistant_id, 'query': query, 
                    'last_messages' : last_messages, 'max_num_results' : max_num_results, 
                   'previous_response_id' : previous_response_id ,'vss' : vss }

        def my_run_remote_query( context ) :
            now = time.time();
            vss = context['vss']
            openai = context['openai']; 
            thread_id = context['thread_id'];
            assistant_id = context['assistant_id'];
            query = context['query'];
            last_messages=context['last_messages'];
            max_num_results = context['max_num_results']
            model = context['model']
            previous_response_id = context.get('previous_response_id',None)
            effort = settings.EFFORT
            print(f"CONTEXT VSS = {vss}")
            msg = ''
            try :
                if vss :
                    try :
                        RESPONSE = openai.responses.create(
                            model=model,
                            input=query,
                            previous_response_id=previous_response_id,
                            instructions=instructions,
                            reasoning={"effort": effort, 'summary': 'auto'},
                            tools=[{"type": "file_search",
                                "vector_store_ids": vss  # your vector store id
                                }]
                        )
                    except Exception as err:
                        print(f"ERROR1 {str(err)} ")
                        if "Previous response with id" in str(err) :
                            previous_response_id = None
                        import ast
                        payload_str = str(err).split(" - ", 1)[1]
                        payload = ast.literal_eval(payload_str)   # safe parse to dict
                        msg = payload["error"]["message"]
                        RESPONSE = openai.responses.create(
                            model=model,
                            input=query,
                            previous_response_id=previous_response_id,
                            instructions=instructions,
                            reasoning={"effort": effort ,'summary': 'auto'},
                            tools=[{"type": "file_search",
                                "vector_store_ids": vss  # your vector store id
                                }]

                            )
    
    
    
                else :
                    try :
                        RESPONSE = openai.responses.create(
                            model=model,
                            input=query,
                            previous_response_id=previous_response_id,
                            instructions=instructions,
                            reasoning={"effort": effort ,'summary': 'auto'},
                            )
                    except  Exception as err :
                        print(f"ERROR4 {str(err)} ")
                        if "Previous response with id" in str(err) :
                            previous_response_id = None
                        import ast
                        payload_str = str(err).split(" - ", 1)[1]
                        payload = ast.literal_eval(payload_str)   # safe parse to dict
                        msg = payload["error"]["message"]
                        RESPONSE = openai.responses.create(
                            model=model,
                            input=query,
                            previous_response_id=previous_response_id,
                            instructions=instructions,
                            reasoning={"effort": effort ,'summary': 'auto'},
                            )

            except  Exception as e :
                print(f"ERROR3 {str(e)}")

    
            print(f"RESPONSE = {RESPONSE}")
            output = RESPONSE.output
            response_id = RESPONSE.id
            summary = 'Null'
            ntokens = RESPONSE.usage.total_tokens
            txt = ''
            summary = 'no summary available'
            for o in output :
                if hasattr(o,'summary'):
                    summary = f"**{msg}**<br><br>\n" 
                    summaries = o.summary
                    for s in summaries :
                        if hasattr(s ,'text' ):
                            summary = summary + s.text + '<br><br>\n'
                        else :
                            summary = summary  + f"{s}"
                if hasattr(o,'content') :
                    ocs = o.content;
                    if ocs :
                        for oc in ocs :
                            if hasattr(oc,'text') :
                                txt = txt + oc.text

            time_spent = int( time.time() - now  + 0.5 )
            characters = string.ascii_letters + string.digits  # a-zA-Z0-9
            h = ''.join(random.choices(characters, k=8))
            msg =  {'user' : query, 'assistant' : txt,
                'ntokens' : ntokens ,
                'model' : model,
                'time_spent' : time_spent ,
                'last_messages' : last_messages,
                'max_num_results' : max_num_results,
                'summary' : summary,
                'response_id' : response_id,
                'previous_response_id' : previous_response_id,
                'hash' : h }
            return msg

        msg = my_run_remote_query( context)
        if thread.messages :
            thread.messages.append(msg) 
        else :
            thread.messages = [msg]
        thread.save()
        from .utils import print_messages
        print_messages(thread)
        return msg





@receiver(pre_delete, sender=Assistant)
def custom_delete_assistant(sender, instance, **kwargs):
    pk = instance.pk
    client = OpenAIClient();
    try :
        assistant = instance
        assistant_id = instance.assistant_id
        vector_store_ids = instance.get_remote_vector_stores()
        client = OpenAIClient()
        if vector_store_ids :
            vs = VectorStore.objects.get(name=instance.name)
            vector_store_id = vector_store_ids[0];
            vector_store =  client.vector_stores_retrieve(vs,vector_store_id)
            if vector_store.name == assistant.name : # THIS IS HERE BECAUSE MULTIPL VECTOR STORES CAN'T BE USED BY AN ASSISTANT
                client.delete_vector_store( vector_store_id)
    except Exception as err :
        print(f"ERROR = {str(err)}")

@receiver(post_delete, sender=Assistant)
def post_delete_assistant(sender, instance, **kwargs):
    assistants = Assistant.objects.filter(name=instance.name ).all();
    for assistant in assistants :
        assistant.delete();




@receiver(m2m_changed, sender=Assistant.vector_stores.through)
def handle_assistants_changed(sender, instance, action, **kwargs):
    dontcontinue =  getattr(instance, '_updating_from_m2m', False)
    if getattr(instance, '_updating_from_m2m', False):
        return
    instance._updating_from_m2m = True
    try :
        instance._count = instance._count + 1 
    except :
        instance._count = 0 
    if instance._count > 1 :
        return

    assistant = instance
    assistant_id = instance.assistant_id
    for vs in assistant.vector_stores.all():
        print(f"     VS = {vs} FILES= {vs.files.all()}")
    client = OpenAIClient()
    rebuild = False
    if action == "post_remove":
        vector_stores = instance.vector_stores.all();
        assistant_id = instance.assistant_id
        assistant = instance
        rebuild = True

    if action == "post_add" or action == 'post_remove' : # rebuild:
        pks = [];
        ids = [];
        file_ids = [];
        file_pks = []
        for v in instance.vector_stores.all() :
            file_ids.extend( v.file_ids() )
            file_pks.extend( v.file_pks() )
            pks.append( v.pk )
            ids.append( v.get_vector_store_id() );
        file_ids = list( set( file_ids ) )
        file_ids.sort() 
        file_pks = list( set( file_pks ) )
        vsname = instance.name
        vss = VectorStore.objects.filter(name=vsname).all().order_by('-id')
        if vss :
            vs = vss[0]
        else :
            vs = VectorStore(name=vsname)
            vs.save()
        vs.files.set(file_pks)
        vs.save();
        vector_store_id = vs.get_vector_store_id()
        instance.vector_stores.set([vs.pk])

    instance.save()
    del instance._updating_from_m2m


DELETE_REMOTE_VECTOR_STORE_ON_EMPTY = False


@receiver(m2m_changed, sender=VectorStore.files.through)
def handle_files_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if getattr(instance, '_updating_from_m2m', False):
        return
    client = OpenAIClient()
    if action in {"pre_add", "pre_remove", "pre_clear"}:
        instance._old_file_ids =  instance.file_ids() # [i[0] for i in instance.files.values_list('file_ids', flat=True)  ]
        instance._old_checksum = instance.get_checksum();
        pass

    elif action == "post_add" or action == 'post_remove' :
        old_file_ids  =  getattr(instance, '_old_file_ids', [] )
        old_checksum  =  getattr(instance, '_old_checksum', None);
        instance.checksum = instance.get_checksum();
        deletions = list( set( old_file_ids  ) - set( instance.file_ids() )  )
        assistants = list( set( Assistant.objects.filter(name=instance.name).all() ) )
        if len( deletions) > 0 :
            for assistant in assistants :
                threads = assistant.get_all_threads()
                for thread in threads :
                    messages = thread.messages;
                    if messages :
                        messages[-1]['response_id'] = None
                    thread.messages = messages;
                    thread.clear = True
                    thread.save();

        instance._updating_from_m2m = True
        instance.vsid = client.get_or_update_remote_vector_store( instance , old_checksum,old_file_ids)
        instance.save();
        del instance._updating_from_m2m

def delete_remote_vector_stores():
    remote_vector_stores = RemoteVectorStore.objects.all();
    for remote_vector_store in remote_vector_stores :
        remote_vector_store.delete();

