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
from django.db.models.signals import m2m_changed, pre_delete
from django.dispatch import receiver
from openai._exceptions import NotFoundError
import re

import os
logger = logging.getLogger(__name__)
#client = openai.OpenAI(api_key=settings.AI_KEY)

upload_storage = FileSystemStorage(settings.OPENAI_UPLOAD_STORAGE, base_url=settings.MEDIA_URL )

from openai import OpenAIError, RateLimitError, APIError, Timeout

def randstring(tag, length=8):
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    return tag + '-' + ''.join(random.choices(characters, k=length))


def dump_pools(s='') :

    pools = VectorStorePool.objects.all();
    print(f"DUMP POOLS {s}\nvvvvvv")
    for pool in pools :
        print(f"POOL = cs={pool.checksum} id={pool.vector_store_id} pks={pool.vector_stores_pks()}")
    print(f"^^^^^^")


def remote_wait_for_vector_store_delete(vector_store_id, timeout=settings.MAXWAIT, interval=2):
    print(f"WAIT_FOR_VECTOR_STORE_DELETE {vector_store_id}")
    # Initiate delete
    client = OpenAIClient()
    #try :
    #    client.vector_stores.delete(vector_store_id)
    #except Exception as err :
    #    print(f"ERROR {str(err)}")
    #    return

    # Poll until deletion confirmed
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            client.vector_stores.retrieve(vector_store_id)
            #print("Still deleting...")
        except NotFoundError:
            #print("Vector store deletion confirmed.")
            return
        time.sleep(interval)

    raise TimeoutError(f"Vector store {vector_store_id} deletion not confirmed within timeout.")



def remote_wait_for_vector_store_ready(client, vector_store_id, timeout=settings.MAXWAIT):
    print(f"WAIT_FOR_VECTOR_STORE_READY {vector_store_id}")
    start_time = time.time()
    client = OpenAIClient()
    while True:
        vs = client.vector_stores.retrieve(vector_store_id=vector_store_id)
        if vs.status == "completed":
            #print("✅ Vector store is ready.")
            return vs
        elif vs.status == "failed":
            raise RuntimeError("❌ Vector store creation failed.")
        elif time.time() - start_time > timeout:
            raise TimeoutError("⏱️ Timeout: Vector store not ready in time.")
        time.sleep(1)
    i = 0;
    imax = settings.MAXWAIT / interval;
    #remote_wait_for_vector_store_ready(client, vector_store_id, timeout=settings.MAXWAIT):
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
    time.sleep(5)
    assert i < imax , "VECTOR STORE READY TIMED OUT"

#def create_run_with_retry(thread_id, assistant_id, timeout, truncation_strategy, tools, max_retries=5):
#    delay = 2  # initial delay in seconds
#    for attempt in range(1, max_retries + 1):
#        try:
#            run = openai.beta.threads.runs.create(
#                thread_id=thread_id,
#                assistant_id=assistant_id,
#                timeout=timeout,
#                truncation_strategy=truncation_strategy,
#                tools=tools,
#            )
#            return run  # success
#        except RateLimitError as e:
#            print(f"Rate limit hit. Attempt {attempt}/{max_retries}. Retrying in {delay} seconds...")
#        except APIError  as e:
#            print(f"Transient API error on attempt {attempt}/{max_retries}: {e}. Retrying in {delay} seconds...")
#        except Timeout as e:
#            print(f"Transient API error on attempt {attempt}/{max_retries}: {e}. Retrying in {delay} seconds...")
#        except Exception as e:
#            print(f"Non-retryable error: {e}")
#            raise  # re-raise non-rate-limit exceptions
#
#        time.sleep(delay)
#        delay *= 2  # exponential backoff
#        return run
#
#    raise Exception("Max retries exceeded due to rate limiting or API errors.")

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
    if user.pk :
        threads = Thread.objects.filter(name=name,user=user)
    else :
        user = None
    threads = Thread.objects.filter(name=name,user=user)
    if not threads :
        thread = Thread(name=name,user=user)
    else :
        thread = threads[0]
    thread.save()
    thread.assistant = assistant
    thread.save()
    return thread







def upload_or_retrieve_openai_file( name ,src ):
    #print(f"NAME = {name} SRC={src}")
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
    #print(f"T1 = {t1}")
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

class OpenAIClient( OpenAI ):

    #def vss = models.ForeignKey(VectorStore, on_delete=models.SET_NULL, null=True)


    def __init__(self, **kwargs):
        # Pass the API key and any kwargs to the parent OpenAI constructor
        super().__init__(api_key=settings.AI_KEY, **kwargs)

    def delete_vector_store(self, vs, vector_store_id) :
        assert vs.vector_store_id == vector_store_id, "FAIL1"
        vector_store_id = vs.vector_store_id
        checksum = vs.get_checksum()
        #try :
        #    self.vector_stores.delete(vector_store_id)
        #except Exception as err :
        #    return False
        #remote_wait_for_vector_store_delete(vector_store_id, timeout=settings.MAXWAIT, interval=2)
        return True


    def vector_stores_retrieve(self, vs, vector_store_id) :
        assert vs.vector_store_id == vector_store_id, "FAIL2"
        vector_store_id = vs.vector_store_id
        checksum = vs.get_checksum()
        return self.vector_stores.retrieve(vector_store_id)


    def vector_stores_files_list(  self, vs, vector_store_id ):
        assert vs.vector_store_id == vector_store_id, "FAIL3"
        vector_store_id = vs.vector_store_id
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
        assert vs.vector_store_id == vector_store_id, "FAIL4"
        vector_store_id = vs.vector_store_id
        checksum = vs.get_checksum()
        #print(f"CLIENT_DELETE_FILE")
        try :
            self.vector_stores.files.delete(vector_store_id=vector_store_id,file_id=file_id)
            remote_wait_for_vector_store_ready(self, vector_store_id, timeout=settings.MAXWAIT)
        except  openai.NotFoundError as e: 
            return False
            #print(f"OPENAI_FILE_{file_id} NOT FOUND TO DELETE")
        try :
            self.files.delete( file_id )
        except  openai.NotFoundError as e: 
            #print(f"OPENAI_FILE_{file_id} NOT FOUND TO DELETE")
            return False
        assert checksum == vs.get_checksum() , "FAIL4b"
        return True

    def delete_file_globally( self , file_id ):
        try :
            self.files.delete(file_id)
            return True
            #print(f"NOW DELETE SUCCEEDED {file_id}")
        except openai.NotFoundError as e:
            #print(f"NOW_DELETE FAILED {file_id} ")
            return False

    def vector_stores_files_delete( self, vs, vector_store_id, file_id ):
        assert vs.vector_store_id == vector_store_id, "FAIL5"
        checksum = vs.get_checksum()
        vector_store_id = vs.vector_store_id
        self.vector_stores.files.delete( vector_store_id=vector_store_id , file_id=file_id)
        remote_wait_for_vector_store_ready(self, vector_store_id, timeout=settings.MAXWAIT)
        assert checksum == vs.get_checksum() , "FAIL5b"
        return vector_store_id

    def vector_stores_files_create( self, vs, vector_store_id , file_id ):
        assert vs.vector_store_id == vector_store_id, "FAIL6"
        checksum = vs.get_checksum()
        vector_store_id = vs.vector_store_id
        self.vector_stores.files.create( vector_store_id=vector_store_id , file_id=file_id   )
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
        #print(f"STATE =  {self._state.adding} PK={self.pk}")
        is_new = self._state.adding  and not self.pk
        name =  f"{self.file}".split('/')[-1]
        super().save(*args, **kwargs)  # Save first, so file is processed
        if is_new and self.file:
            #print(f"IS_NEW {self.file}")
            fn = self.file.name 
            self.name = self.file.name.split('/')[-1]
            src = self.file.path
            #print(f"SRC = {src}")
            extension = src.split('.')[-1];
            if extension == 'pdf' :
                txt = mathpix( src ,format_out='mmd')
            else :
                txt = ( open(src,'rb').read() ).decode('utf-8')
            chunks = chunk_mmd(txt)
            chunkdir = os.path.join( os.path.dirname( src ), 'chunks')
            os.makedirs( chunkdir, exist_ok=True )
            srcbase = Path( os.path.basename(src) )
            jbase = srcbase.with_suffix('.json')
            dst = os.path.join( chunkdir, jbase )
            if chunks :
                open( dst, "wb").write( chunks)
            else :
                shutil.copy2(src, dst)
            data = self.file.read()
            self.checksum = hashlib.md5(data).hexdigest()
            uploaded_file = openai.files.create( file=open( dst, "rb"), purpose="assistants")
            self.file_ids = [uploaded_file.id ]
            self.path = os.path.dirname( self.file.path )

            def get_ntokens( file_path):
                valid_text = ''
                encoding = tiktoken.encoding_for_model(settings.AI_MODEL['staff'])
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
            #print(f"NOW AFTER CHUNKING NAME IS {self.name}")
            self.name = name
            super().save(*args, **kwargs) # Then update with true hashed path



@receiver(pre_delete, sender=OpenAIFile)
def custom_delete_openaifile(sender, instance, **kwargs):
    #print(f"CUSTOM_DELETE_OPENAIFILE")
    pk = instance.pk
    try :
        shutil.rmtree(instance.path)
    except Exception as e:
        logger.error(f" FILE/ {instance.path} DOES NOT EXIST")
        return
    vst = VectorStore.objects.filter(files=instance).all();
    #print(f"VST = {vst}")
    client = OpenAIClient()
    if hasattr( instance, "file_ids") :
        #print(f"A")
        file_ids = instance.file_ids
        #print(f"FILE_IDS = {file_ids}")
        for file_id in file_ids :
            for vs in vst :
                #print(f"CUSTOM_DELETE_FILE VS = {vs}")
                vector_store_id = vs.vector_store_id
                client.delete_file_from_vs(vs,  vector_store_id, file_id )
                vs.save();
            try :
                client.delete_file_globally(  file_id)
                #print(f"DELETE SUCCEEDED")
            except openaiNotFoundError as e:
                #print(f"DELETE FAILED")
                pass
            #try :
            #    print(f"NOW DELETE {file_id}")
            #    client.files.delete(file_id)
            #except openai.NotFoundError as e:
            #    print(f"{str(e)}")
            #    pass

class VectorStore( models.Model ):
    checksum = models.CharField(blank=True, max_length=255)
    vector_store_id = models.CharField(max_length=255,blank=True)
    name =  models.CharField(max_length=255,unique=True)
    files = models.ManyToManyField( OpenAIFile )

    def __str__(self):
        return f"{self.name}"

    def clone( self, newname, *args, **kwargs):
        vector_stores = VectorStore.objects.filter( name=newname).all();
        assert  len( vector_stores) == 0 , f"CREATE ASSISTANT WITH NAME {newname} ; ASSISTANT ALREADY EXISTS"
        vector_store = VectorStore(name=newname)
        vector_store.save();
        vector_store.files.set(self.files.all() )
        vector_store.save();
        return vector_store;


    def file_ids(self, *args, **kwargs ):
        files = self.files
        ids = []
        for f in files.all():
            ids.extend( f.file_ids )
        return ids

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

    def get_checksum(self):
        cksums = self.file_checksums();
        ckstring = ''.join(cksums).encode()
        checksum = hashlib.md5(ckstring).hexdigest()
        #print(f"GET CHECKSUM  cksums={cksums} {self} = {checksum}")
        return checksum


    def files_ok( self, *args, **kwargs) :
        vs = self
        file_ids = vs.file_ids()
        vector_store_id = vs.vector_store_id
        client = OpenAIClient()
        vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store_id)
        remote_ids = []
        for f in vector_store_files:
            remote_ids.append( f.id)
        print(f"FILESOK? LOCAL={file_ids} == REMOTE={remote_ids}")
        return set( file_ids) == set( remote_ids) 



    def save( self, *args, **kwargs ):
        is_new = self._state.adding and not self.pk
        super().save(*args,**kwargs)
        checksum = self.get_checksum();
        if is_new :
            client = OpenAIClient()
            pools = VectorStorePool.objects.filter(checksum=checksum).all()
            if not pools :
                name = 'vs3-' + self.name
                vector_store = client.vector_stores.create( name=name,metadata={"api_app" : settings.API_APP, "api_key": settings.AI_KEY[-8:] , "checksum" : checksum } )
                vector_store_id = vector_store.id
                remote_wait_for_vector_store_ready(client, vector_store_id, timeout=settings.MAXWAIT)
                VectorStorePool.objects.create(checksum=checksum, vector_store_id=vector_store_id)
            else :
                vector_store_id = pools[0].vector_store_id
            self.vector_store_id = vector_store_id


        super().save(*args,**kwargs)



@receiver(pre_delete, sender=VectorStore)
def custom_delete_vector_store(sender, instance, **kwargs):
    client = OpenAIClient();
    try :
        vector_store_id = instance.vector_store_id
        client.delete_vector_store( instance, vector_store_id )
    except openai.NotFoundError as e:
        pass


def get_current_model( user=None ):
    if user == None :
        model = settings.AI_MODEL['default']
    elif user.is_superuser :
        model = settings.AI_MODEL['staff']
    else :
        model = settings.AI_MODEL['default']
    return model


DEFAULT_INSTRUCTIONS = """Answer only questions about the enclosed document. 
    Do not offer helpful answers to questions that do not refer to the document. 
    Be concise. 
    If the question is irrelevant, answer with "That is not a question that is relevant to the document." \n 
    For images use created by mathpix, not the sandbox link created by openai. 
    Since it is visible, dont  say something like "You can view the picture ... ". 
    If a link does not exist, just say that such an image does not exist. '
    """


class Assistant( models.Model ):
    name =   models.CharField(max_length=255,blank=True)
    instructions = models.TextField(blank=True,null=True)
    vector_stores = models.ManyToManyField( VectorStore ,blank=True)
    assistant_id = models.CharField(max_length=255,blank=True, null=True)
    json_field = models.JSONField( default=dict ,  blank=True, null=True)
    model = models.CharField(max_length=255,blank=True,null=True)
    temperature = models.FloatField(null=True, blank=True)


    def __str__(self):
        return f"{self.name}"


    def path(self) :
        p = '/'.join( self.name.split('.') )
        return p

    #def delete(self,*args, **kwargs):
    #    name = self.name
    #    print(f"DELETE ASSISTANT {self.name}")
    #    #vss = self.vector_stores.all();
    #    #for vs in vss :
    #    #    vs.delete();
    #    super().delete(*args, **kwargs) 
    #    print(f"DELETED ASSISTANT {name}")
    #    return
            



    def add_file(self,  filename, uploaded_file ):
        name = '.'.join( filename.split('.')[:-1])
        filename = f"{name}/{filename}"
        upload_storage.save(filename , uploaded_file)
        file_url = settings.MEDIA_URL + upload_storage.url(filename)
        src = settings.OPENAI_UPLOAD_STORAGE + '/' + filename
        t1 = upload_or_retrieve_openai_file( name, src )
        self.add_raw_file( t1 )
        return file_url

    def add_raw_files(self,  t1 ):
        vss = self.vector_stores.all();
        if len( vss ) == 0 :
            vs = VectorStore( name=self.name);
            vs.save();
            self.vector_stores.add(vs)
        else :
            vs = vss[0]
        #for t in t1 :
        #    vs.add_raw_file( t )
        for t in t1 :
            self.add_raw_file( t )
        return 


    def add_raw_file(self,  t1 ):
        vss = self.vector_stores.all();
        if len( vss ) == 0 :
            vs = VectorStore( name=self.name);
            vs.save();
            self.vector_stores.add(vs)
            vs.save();
            self.save()
        else :
            vs = vss[0]
            print(f"VSOLD = {vs.vector_store_id}")
            try  :
                vs.files.add(t1)
                print(f"B SAVE")
                vs.save();
                print(f"C SAVED")
                self.vector_stores.set([vs])
                self.save()
            except  Exception as err :
                dump_pools("ERROR IN ADD_RAW_FILE")
        print(f"VSNEW = {vs.vector_store_id}")
        print("D")
        assistant_id = self.assistant_id 
        print(f"E")
        client = OpenAIClient()
        client.beta.assistants.update(
            assistant_id=assistant_id,
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vs.vector_store_id],
                }
            }
        )
        print(f"F")
        self.save();
        print(f"G")
        return 

    def delete_raw_file( self, file ):
        vs = self.vector_stores.all()[0];
        vs.files.remove(file)
        vs.save();
        self.vector_stores.set([vs])
        assistant_id = self.assistant_id 
        client = OpenAIClient()
        client.beta.assistants.update(
            assistant_id=assistant_id,
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vs.vector_store_id],
                }
            }
        )
        self.save();
        return




    def delete_file( self, deletion ):
        deletion = int( deletion )
        vs = self.vector_stores.all()[0];
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
        #print(f"P = {p} NAM = { p.name } {type(p)} ")
        if p :
            i = 0;
            while not p.parent() == None and instructions == ''  and i < 4 :
                p = p.parent();
                instructions = p.get_instructions();
                i = i + 1 ;
        if instructions == '':
            instructions = DEFAULT_INSTRUCTIONS 
        if appended :
            instructions = instructions + "\n" + appended
        return instructions
            

    def save( self, *args, **kwargs ):
        is_new = self._state.adding and not self.pk
        client = OpenAIClient()
        try :
            if not self.model :
                self.model = get_current_model( )
        except :
            pass
        if self.pk :
            old = Assistant.objects.get(pk=self.pk)
            old_instructions = old.get_instructions()
            old_temperature = old.temperature
            old_model = self.model
        else :
            old_instructions = None
        if self.temperature :
            temperature = self.temperature
        else :
            temperature = settings.DEFAULT_TEMPERATURE
        super().save(*args,**kwargs)
        #print(f"VECTOR_STORESAGAIN = {self.vector_stores.all()}")
        vs_empty = False;
        instructions = self.get_instructions();
        if is_new :
            assistant = client.beta.assistants.create( name=self.name,
                instructions=instructions, 
                model=self.model,
                temperature=temperature,
                tools=[{"type": "file_search"}],metadata={"api_app" : settings.API_APP, "api_key": settings.AI_KEY[-8:] } )
            self.assistant_id = assistant.id
            super().save(update_fields=['assistant_id'])

            def attach_vector_store():
                if not self.vector_stores.exists():
                    vs = VectorStore( name=self.name);
                    vs.save();
                    self.vector_stores.add(vs)

            transaction.on_commit(attach_vector_store) 

        else :
            super().save( *args, **kwargs)
            #print(f"IS NOT NEW")
            #vss = self.vector_stores.all();
            #v#ss = VectorStore.objects.filter(name=self.name).all()
            #if len( vss ) == 0 :
            #    vs = VectorStore( name=self.name);
            #    vs.save();
            #    self.vector_stores.add(vs)
            #else :
            #    vs = vss[0]
            #    self.vector_stores.add(vs)


            assistant_id = self.assistant_id
            if not old_instructions  ==  instructions :
                client.beta.assistants.update(assistant_id, instructions=instructions)
            if not old_temperature ==  temperature :
                client.beta.assistants.update(assistant_id, temperature=temperature)
            if not old_model ==  self.model :
                client.beta.assistants.update(assistant_id, model=self.model)

        #if False and len( self.vector_stores.all() ) == 0   and   not getattr(self, '_busy', False) :

        #    #print(f"LEN = 0 ")
        #    p = self.parent();
        #    #print(f"P = {p}")
        #    i = 0;
        #    while p and i < 4  :
        #        self.vector_stores.add( *( p.vector_stores.all() ) )
        #        self._state.adding  = True
        #        p = self.parent()
        #        i = i + 1;
        #    self._state.busy = True
        #    #print(f"SELF VECTOR_STORES = {self.vector_stores.all() }")
        #    #super().save(*args,**kwargs)


    def clone( self, newname, *args, **kwargs):
        assistants = Assistant.objects.filter( name=newname).all();
        assert  len( assistants) == 0 , f"CREATE ASSISTANT WITH NAME {newname} ; ASSISTANT ALREADY EXISTS"
        assistant = Assistant(name=newname)
        assistant.instructions = self.instructions;
        assistant.json_field = self.json_field;
        assistant.model = self.model
        assistant.temperature = self.temperature;
        assistant.save();
        i = 0;
        for v in self.vector_stores.all() :
            vnew  = v;
            #vnew = v.clone(f"{newname}-{i}");
            assistant.vector_stores.add(vnew )
            i = i + 1;
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
        vs = self.vector_stores.all()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.append( vf.pk )
        f = list( set( f) )
        return f

    def file_ids(self, *args, **kwargs ):
        vs = self.vector_stores.all()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.extend( vf.file_ids )
        f = list( set( f) )
        return f

    def files( self, *args, **kwargs ):
        vs = self.vector_stores.all()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.append( ( vf.pk , vf.name ) )
        #print(f"F = {f}")
        return f





    def file_names( self, *args, **kwargs ):
        vs = self.vector_stores.all()
        f = []
        for v in vs :
            for vf in v.files.all():
                f.append( vf.name )
        f = list( set( f) )
        return f

    def remote_files( self, *args, **kwargs ) :
        #print(f"REMOTE_FILES?")
        client = OpenAIClient()
        assistant = self
        vss = self.vector_stores.all();
        for vs in vss :
            print(f"ASSISTANT VS = {vs}")
        assistant_id = assistant.assistant_id
        remote_assistant = openai.beta.assistants.retrieve(assistant_id)
        tool_resources = remote_assistant.tool_resources
        remote_ids = [];
        vector_store_ids = tool_resources.file_search.vector_store_ids
        print(f"VECTOR_STORE_IDS = {vector_store_ids}")
        #vss = self.vector_stores.all();
        #print(f"VSS = {vss}")
        #for vs in vss :
        #    vspk = vs.pk
        #    pool = VectorStorePool.object.filter(vector_stores=vspk)
        #    print(f"POOL = {pool}")
        #    vsid = pool.vector_store_id
        #    print(f"VSID = {vsid}")
        #print(f"VPKS = {vpks}")
        #pools = VectorStorePool.object.filter(vector_stores__in=vpks)
        #print(f"POOLS = {pools}")
        #client = OpenAIClient()
        for vector_store_id in vector_store_ids :
            #print(f"A {vector_store_id}")
            #print(f"B")
            #vector_store =  client.vector_stores.retrieve(vector_store_id)
            #print(f"C")
            vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store_id)
            #print(f"D {vector_store_files}")
            for f in vector_store_files:
                remote_ids.append( f.id)
        print(f"REMOTE_IDS= {remote_ids}")
        return remote_ids


        

    def files_ok( self,*args, **kwargs):
        #print("FILES_OK")
        assistant = self
        vss = assistant.vector_stores.all();
        #for vs in vss :
        #    #print(f"CHECK VS = {vs}")
        #    vs.files_ok();
        #print(f"F1")
        file_ids = assistant.file_ids();
        #print(f"F2")
        remote_ids = assistant.remote_files();
        #print("F3")
        #print(f"FILES_OK? LOCAL={file_ids} == REMOTE={remote_ids} ?" )
        return set( remote_ids) == set( file_ids )


class VectorStorePool( models.Model ) :
    checksum = models.CharField(blank=True, max_length=255,unique=True)
    vector_stores = models.ManyToManyField(VectorStore, blank=True)
    vector_store_id  =  models.CharField(blank=True, max_length=255 )

    def vector_stores_pks(self ):
        pks = [ i.pk for i in self.vector_stores.all() ]
        return pks

    def delete( self, *args, **kwargs ):
        client = OpenAIClient();
        vector_store_id = self.vector_store_id
        #print(f"VECTOR_STORE_CLIENT_DELETE {self.pk} {vector_store_id}")
        try :
            client.vector_stores.delete( vector_store_id )
            remote_wait_for_vector_store_delete(vector_store_id, timeout=settings.MAXWAIT, interval=2)
        except :
            print(f"FAILED VECTOR_STORE_CLIENT_DELETE")
            pass
        super().delete(*args, **kwargs) 
        #print(f"DONE WITH VECTOR_STORE_CLIENT_DELETE")



class Thread(models.Model) :
    name = models.CharField(max_length=255)
    date = models.DateTimeField(auto_now=True)
    thread_id = models.CharField(max_length=255,blank=True)
    messages = models.JSONField( default=dict ,  blank=True, null=True)
    assistant = models.ForeignKey(Assistant, on_delete=models.SET_NULL, null=True, related_name="threads")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    max_tokens = models.IntegerField( blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'user'], name='unique_thread')
        ]
    

    def __str__(self):
        return f"{self.name}"




    def save( self, *args, **kwargs ):
        is_new = self._state.adding  and not self.pk
        self.messages = self.messages
        client = OpenAIClient();
        super().save(*args, **kwargs)  # Save first, so file is processed
        if is_new  :
            thread = client.beta.threads.create(); 
            thread_id = thread.id
            self.thread_id = thread_id
            self.messages = []
            super().save(*args, **kwargs) # Then update with true hashed path
        elif 'update_fields' in kwargs :
            thread_id = self.thread_id
            old_thread_id = thread_id
            new_thread =  client.beta.threads.create(); 
            new_thread_id = new_thread.id
            if self.messages :
                for msg in self.messages:
                    for role in ['user','assistant'] :
                        openai.beta.threads.messages.create(
                            thread_id=new_thread_id,
                            role=role,
                            content=msg[role]
                        )
                        
            self.thread_id = new_thread_id
            self.messages = self.messages
            super().save(*args, **kwargs)



    def run_query( self, *args, **kwargs  ):
        last_messages = kwargs.get('last_messages',settings.LAST_MESSAGES)
        max_num_results = kwargs.get('max_num_results',settings.MAX_NUM_RESULTS)
        query= kwargs['query']
        now = time.time();
    
        """ last_messages is either None for auto or an integer for length of thread history to keep at OpenAI. 
        The entire history is kept in the local database"""
        assistant = self.assistant
        if not assistant.model == get_current_model( self.user ):
            assistant.model = get_current_model( self.user )
            assistant.save();
        assistant_id = assistant.assistant_id
        model = assistant.model
        thread = self
        thread_id = thread.thread_id
    
        encoding = tiktoken.encoding_for_model(settings.AI_MODEL['staff'])
        if thread.max_tokens :
            max_tokens = thread.max_tokens
        else :
            max_tokens = settings.MAX_TOKENS
        timeout = settings.MAXWAIT
        context = {'openai' : openai, 'thread_id': thread_id, 'assistant_id' : assistant_id, 'query': query, 'last_messages' : last_messages, 'max_num_results' : max_num_results}
        msg = run_remote_query( context)
        thread.messages.append(msg) 
        thread.save()
        return msg






@receiver(pre_delete, sender=Assistant)
def custom_delete_assistant(sender, instance, **kwargs):
    pk = instance.pk
    client = OpenAIClient();
    try :
        assistant_id = instance.assistant_id
        assistant = openai.beta.assistants.retrieve(assistant_id)
        tool_resources = assistant.tool_resources
        vector_store_ids = tool_resources.file_search.vector_store_ids
        client = OpenAIClient()
        if vector_store_ids :
            vs = VectorStore.objects.get(name=instance.name)
            vector_store_id = vector_store_ids[0];
            vector_store =  client.vector_stores_retrieve(vs,vector_store_id)
            if vector_store.name == assistant.id : # THIS IS HERE BECAUSE MULTIPL VECTOR STORES CAN'T BE USED BY AN ASSISTANT
                client.delete_vector_store( vector_store_id)
        res = client.beta.assistants.delete(assistant_id)
    except Exception as err :
        print(f"ERROR = {str(err)}")


@receiver(m2m_changed, sender=Assistant.vector_stores.through)
def handle_assistants_changed(sender, instance, action, **kwargs):
    print(f"HANDLE_SENDER_ASSISTANT action={action}")
    dontcontinue =  getattr(instance, '_updating_from_m2m', False)
    print(f"DONT_CONTINUE = {dontcontinue}")
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
    print(f"ASSISTANT =  {action} {assistant} {assistant.vector_stores.all()} ")
    for vs in assistant.vector_stores.all():
        print(f"     VS = {vs} FILES= {vs.files.all()}")
    client = OpenAIClient()
    rebuild = False
    if action == "post_remove":
        print(f"POST_REMOVE")
        vector_stores = instance.vector_stores.all();
        vs = vector_stores[0];
        assistant_id = instance.assistant_id
        assistant = openai.beta.assistants.retrieve(assistant_id)
        tool_resources = assistant.tool_resources
        try :
            vector_store_id = tool_resources.file_search.vector_store_ids[0]
            vector_store =  client.vector_stores_retrieve(vs, vector_store_id)
            if vector_store.name == assistant.name:
                client.vector_store_delete( vector_store_id)
        except  Exception as err :
            print(f" VECTOR_STORE ERROR DELTING ON POST_REMOVE")
            pass
        rebuild = True

    if action == "post_add" or rebuild:
        print(f"POST_ADD")
        pks = [];
        ids = [];
        file_ids = [];
        file_pks = []
        for v in instance.vector_stores.all() :
            print(f"V NAME = {v.name} ")
            file_ids.extend( v.file_ids() )
            file_pks.extend( v.file_pks() )
            pks.append( v.pk )
            ids.append( v.vector_store_id );
        file_ids = list( set( file_ids ) )
        file_ids.sort() 
        file_pks = list( set( file_pks ) )
        vsname = instance.name
        vs, created = VectorStore.objects.get_or_create(name=vsname)
        vs.files.set(file_pks)
        print(f"SAVED FILE_PKS created={created} {file_pks}")
        vs.save();
        print(f"VS NAME = {vs.name}")
        vector_store_id = vs.vector_store_id
        print(f"VS VECTTOR_STORE_ID {vector_store_id}")
        instance.vector_stores.set([vs.pk])
        try :
            assistant = client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": [ vector_store_id ] }},
                metadata={"api_key": settings.AI_KEY[-8:] } 
                )
        except Exception as e:
            print(f"CLIENT CANNOT UPDATE ASSISTANT {str(e)}")

    instance.save()
    del instance._updating_from_m2m


DELETE_POOL_ON_EMPTY = False


@receiver(m2m_changed, sender=VectorStore.files.through)
def handle_files_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    print(f"HANDLE_SENDER_VECTOR_STORE action={action}")
    if getattr(instance, '_updating_from_m2m', False):
        #print(f"RETURN DIRECT")
        return
    client = OpenAIClient()
    if action in {"pre_add", "pre_remove", "pre_clear"}:
        instance._old_file_ids =  instance.file_ids() # [i[0] for i in instance.files.values_list('file_ids', flat=True)  ]
        checksum = instance.get_checksum();
        instance._old_checksum = instance.get_checksum();
        #print(f"AA CHECKSUM={checksum} ID={instance.vector_store_id} ")
        #pools = VectorStorePool.objects.filter(checksum=checksum).all()
        #if pools :
        #    pool = pools[0]
        #    print(f"REMOVE INSTANCPK = {instance.pk} from {checksum} ")
        #    pool.vector_stores.remove(instance.pk)
        #    pool.save();
        #else :
        #    return
        ##else :
        ##    pool, created   = VectorStorePool.objects.get_or_create(checksum=instance.checksum, vector_store_id=instance.vector_store_id);
        ##try :
        ##    print(f"CC REMOVE {instance.pk} ")
        ##    old_pool.vector_stores.remove( instance.pk )
        ##    old_pool.save();
        ##except Exception as err :
        ##    print(f"POOL ERROR {str(err)}")
        #if len( pool.vector_stores.all() ) == 0 :
        #    if DELETE_POOL_ON_EMPTY :
        #        pool.delete();
        #else :
        #    try :
        #        pool.save();
        #    except Exception as err :
        #        print(f"POOL SAVE ERROR {instance.checksum} {instance.vector_store_id}")
        #old_pool.save();

    elif action == "post_add" or action == 'post_remove' :
        old_file_ids  =  getattr(instance, '_old_file_ids', [] )
        old_checksum  =  getattr(instance, '_old_checksum');
        new_file_ids =  [i[0] for i in  instance.files.values_list('file_ids', flat=True)  ]
        instance._updating_from_m2m = True
        vector_store_id = instance.vector_store_id
        vs = instance
        added_files = list( set( new_file_ids) - set( old_file_ids ) )
        subtracted_files = list( set( old_file_ids)  - set( new_file_ids) )
        #if not added_files and not subtracted_files :
        #    print(f"FILES IDENTICAL")
        #    del instance._updating_from_m2m
        #    return
        #print(f"ADDED_FILES = {set(added_files)}")
        #print(f"SUBTRACTED_FILES = {set(subtracted_files)}")
        #interval = 5;
        #imax = settings.MAXWAIT / interval;
        #i = 0;
        #remote_wait_for_vector_store_ready(client, vector_store_id, timeout=settings.MAXWAIT)
        #print(f"OLD_FILES={old_file_ids} NEW_FILES = {new_file_ids}")
        #print(f"ALL_FILES = {instance.files.all()}")
        #oldname = vs.name;
        #vs.name = randstring('oldname')
        #vs.save(update_fields=['name']);

        checksum = instance.get_checksum();
        new_checksum = checksum
        #print(f"OLD_CHECKSUM = {old_checksum} NEW_CHECKSUM={checksum}")


        pools = VectorStorePool.objects.filter(checksum=new_checksum).all()
        if pools :
            pool = pools[0]
            new_vector_store_id = pool.vector_store_id
            #print(f"ADD INSTANCEPK = {instance.pk} to {new_checksum}")
            pool.vector_stores.add(instance)
            #pool.save();
        else :
            name = randstring('vss')
            new_vector_store = client.vector_stores.create(name=name,file_ids=new_file_ids , 
                metadata={"api_app" : settings.API_APP, "api_key": settings.AI_KEY[-8:] , "checksum" : new_checksum } )
            remote_wait_for_vector_store_ready(client, new_vector_store.id, timeout=settings.MAXWAIT)
            new_vector_store_id = new_vector_store.id
            print(f"CREATE NEW POOL WITH {checksum} {new_vector_store_id}")
            new_pool, created   = VectorStorePool.objects.get_or_create(checksum=checksum,vector_store_id=new_vector_store_id);
            #print(f"NEW_POOL = {new_pool} create={created}")
            new_pool.vector_stores.add( instance );
            new_pool.save();

        instance.vector_store_id = new_vector_store_id
        print(f"UPDATE VS cs={checksum} {vector_store_id}")
        instance.save(update_fields=['checksum','vector_store_id']);
        #instance.save();
        #dump_pools();
        del instance._updating_from_m2m

def delete_pools():
    pools = VectorStorePool.objects.all();
    for pool in pools :
        pool.delete();

def dump_pools_(s='') :
    pools = VectorStorePool.objects.all();
    print(f"{s}\nvvvvvv")
    for pool in pools :
        print(f"POOL = cs={pool.checksum} id={pool.vector_store_id} pks={pool.vector_stores_pks()}")
    print(f"^^^^^^")


