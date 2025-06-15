from django.db import models
from pathlib import Path
from django.db import transaction
import random, string
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
import shutil
from .mathpix import mathpix

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
client = openai.OpenAI(api_key=settings.AI_KEY)

upload_storage = FileSystemStorage(settings.OPENAI_UPLOAD_STORAGE, base_url=settings.MEDIA_URL )

from openai import OpenAIError, RateLimitError, APIError, Timeout

def delete_vector_store_and_wait(vector_store_id, timeout=60, interval=2):
    # Initiate delete
    try :
        client.vector_stores.delete(vector_store_id)
    except Exception as err :
        print(f"ERROR {str(err)}")
        return

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



def wait_for_vector_store_ready(client, vector_store_id, timeout=settings.MAXWAIT):
    start_time = time.time()
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

def create_run_with_retry(thread_id, assistant_id, timeout, truncation_strategy, tools, max_retries=5):
    delay = 2  # initial delay in seconds
    for attempt in range(1, max_retries + 1):
        try:
            run = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
                timeout=timeout,
                truncation_strategy=truncation_strategy,
                tools=tools,
            )
            return run  # success
        except RateLimitError as e:
            print(f"Rate limit hit. Attempt {attempt}/{max_retries}. Retrying in {delay} seconds...")
        except APIError  as e:
            print(f"Transient API error on attempt {attempt}/{max_retries}: {e}. Retrying in {delay} seconds...")
        except Timeout as e:
            print(f"Transient API error on attempt {attempt}/{max_retries}: {e}. Retrying in {delay} seconds...")
        except Exception as e:
            print(f"Non-retryable error: {e}")
            raise  # re-raise non-rate-limit exceptions
        time.sleep(delay)
        delay *= 2  # exponential backoff
        return run

    raise Exception("Max retries exceeded due to rate limiting or API errors.")

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
    pk = instance.pk
    try :
        shutil.rmtree(instance.path)
    except Exception as e:
        logger.error(f" FILE/ {instance.path} DOES NOT EXIST")
        return
    vst = VectorStore.objects.filter(files=instance)
    if hasattr( instance, "file_ids") :
        file_ids = instance.file_ids
        for file_id in file_ids :
            for vs in vst.all() :
                vector_store_id = vs.vector_store_id
                try  :
                    client.vector_stores.files.delete(vector_store_id=vector_store_id,file_id=file_id)
                except  openai.NotFoundError as e: 
                    pass
            try :
                client.files.delete(file_id)
            except openai.NotFoundError as e:
                pass

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
        vector_store.checksum = self.checksum
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
        pks = []
        for f in files.all():
            pks.append(f.checksum)
        return pks

    def files_ok( self, *args, **kwargs) :
        vs = self
        file_ids = vs.file_ids()
        vector_store_id = vs.vector_store_id
        vector_store =  client.vector_stores.retrieve(vector_store_id)
        vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store.id)
        remote_ids = []
        for f in vector_store_files:
            remote_ids.append( f.id)
        return set( file_ids) == set( remote_ids) 



    def save( self, *args, **kwargs ):
        is_new = self._state.adding and not self.pk
        super().save(*args,**kwargs)
        if is_new :
            vector_store = client.vector_stores.create(name=self.name,metadata={"api_key": settings.AI_KEY[-8:] } )
            self.vector_store_id = vector_store.id
            wait_for_vector_store_ready( client, self.vector_store_id )
            super().save(*args,**kwargs)

@receiver(pre_delete, sender=VectorStore)
def custom_delete_vector_store(sender, instance, **kwargs):
    try :
        vector_store_id = instance.vector_store_id
        #client.vector_stores.delete(vector_store_id=vector_store_id)
        delete_vector_store_and_wait(vector_store_id )
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

    def delete(self,*args, **kwargs):
        vss = self.vector_stores.all();
        for vs in vss :
            if self.name == vs.name :
                vs.delete();
        super().delete(*args, **kwargs) 
            



    def add_file(self,  filename, uploaded_file ):
        name = '.'.join( filename.split('.')[:-1])
        filename = f"{name}/{filename}"
        upload_storage.save(filename , uploaded_file)
        file_url = settings.MEDIA_URL + upload_storage.url(filename)
        src = settings.OPENAI_UPLOAD_STORAGE + '/' + filename
        t1 = upload_or_retrieve_openai_file( name, src )
        self.add_raw_file( t1 )
        #vs = self.vector_stores.all()[0];
        #vs.files.add(t1)
        #self.save();
        return file_url

    def add_raw_files(self,  t1 ):
        #print(f"ADD_FILE {filename} ASSISTANT = {self.name} ")
        #name = '.'.join( filename.split('.')[:-1])
        #filename = f"{name}/{filename}"
        #upload_storage.save(filename , uploaded_file)
        #file_url = settings.MEDIA_URL + upload_storage.url(filename)
        #src = settings.OPENAI_UPLOAD_STORAGE + '/' + filename
        #t1 = upload_or_retrieve_openai_file( name, src )
        vss = self.vector_stores.all();
        if len( vss ) == 0 :
            vs = VectorStore( name=self.name);
            vs.save();
            self.vector_stores.add(vs)
        else :
            vs = vss[0]
        vs.files.add(*t1 )
        self.save();
        return 


    def add_raw_file(self,  t1 ):
        #print(f"ADD_FILE {filename} ASSISTANT = {self.name} ")
        #name = '.'.join( filename.split('.')[:-1])
        #filename = f"{name}/{filename}"
        #upload_storage.save(filename , uploaded_file)
        #file_url = settings.MEDIA_URL + upload_storage.url(filename)
        #src = settings.OPENAI_UPLOAD_STORAGE + '/' + filename
        #t1 = upload_or_retrieve_openai_file( name, src )
        vss = self.vector_stores.all();
        if len( vss ) == 0 :
            vs = VectorStore( name=self.name);
            vs.save();
            self.vector_stores.add(vs)
        else :
            vs = vss[0]
        vs.files.add(t1)
        self.save();
        return 

    def delete_raw_file( self, file ):
        vs = self.vector_stores.all()[0];
        #file = OpenAIFile.objects.get(pk=deletion);
        vs.files.remove(file)
        return




    def delete_file( self, deletion ):
        deletion = int( deletion )
        #print(f"DELETE {deletion} in {self.name}")
        vs = self.vector_stores.all()[0];
        file = OpenAIFile.objects.get(pk=deletion);
        vs.files.remove(file)
        #vss = self.vector_stores.all();
        #pkss = [];
        #for vs in vss :
        #    pks = vs.file_pks();
        #    pkss.extend( pks )
            #print(f"VECTOR_STORES = VS = {pks}")
        # DELETE THE SPECIAL VS's THAT ARE ASSOCIATED WITH ASSISTANTS DUE TO RESTRICTION OF ONE VECTOR STORE

        #def delete_remote_vs( assistant_id ):
        #    #print(f"TRY DELETETING {assistant_id}")
        #    assistant = openai.beta.assistants.retrieve(assistant_id)
        #    #print(f"DELETE ASSISTANT {assistant}")
        #    tool_resources = assistant.tool_resources
        #    #print(f"TOOL_RESOURCES = {tool_resources}")
        #    vector_store_ids = tool_resources.file_search.vector_store_ids
        #    if vector_store_ids :
        #        vector_store_id = vector_store_ids[0];
        #        #print(f"VECTOR_STORES = {vector_store_id}")
        #        vector_store =  client.vector_stores.retrieve(vector_store_id)
        #        #print(f"VECTOR_STORE = {vector_store}")
        #        #print(f"VECTOR_STORE_NAME = {vector_store.name} {assistant_id}")
        #        if vector_store.name == assistant_id : # THIS IS HERE BECAUSE MULTIPL VECTOR STORES CAN'T BE USED BY AN ASSISTANT
        #            #print(f"DELETE REMOTE VECTOR STORE {assistant_id}")
        #            delete_vector_store_and_wait(vector_store_id)
        #            #client.vector_stores.delete(vector_store_id)

        #assistant_id = self.assistant_id
        #delete_remote_vs( assistant_id )
        #print(f"PKSS = {pkss}")
        #pks = [ i for i in pkss if not i == deletion]
        #print(f"PKS = {pks}")
        #vs = self.vector_stores.all();
        #print(f"VS TO BE FIXED = {vs}")
        #
        #self.vector_stores.clear();
        #name = self.name
        ##print(f"NAME = {name}")
        #files = OpenAIFile.objects.filter( pk__in=pks );
        ##print(f"FILES = {files}")
        #vsnew  = create_or_retrieve_vector_store( name , files)
        #self.vector_stores.add( vsnew );

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
            
    def nodelete( self, *args, **kwargs ):
        vs = VectorStore.objects.filter(name=self.name)
        for v in vs.all()  :
            v.delete();
        super().delete(*args, **kwargs) 


    def save( self, *args, **kwargs ):
        #if getattr(self, '_busy', False):
        #    return
        #print(f"SAVE ASSITANT args = {args}")
        #print(f"SAVE ASSITANT kwargs = {kwargs}")
        is_new = self._state.adding and not self.pk
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
                tools=[{"type": "file_search"}],metadata={"api_key": settings.AI_KEY[-8:] } )
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

        if False and len( self.vector_stores.all() ) == 0   and   not getattr(self, '_busy', False) :

            #print(f"LEN = 0 ")
            p = self.parent();
            #print(f"P = {p}")
            i = 0;
            while p and i < 4  :
                self.vector_stores.add( *( p.vector_stores.all() ) )
                self._state.adding  = True
                p = self.parent()
                i = i + 1;
            self._state.busy = True
            #print(f"SELF VECTOR_STORES = {self.vector_stores.all() }")
            #super().save(*args,**kwargs)


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
        assistant = self
        assistant_id = assistant.assistant_id
        remote_assistant = openai.beta.assistants.retrieve(assistant_id)
        tool_resources = remote_assistant.tool_resources
        remote_ids = [];
        vector_store_ids = tool_resources.file_search.vector_store_ids
        for vector_store_id in vector_store_ids :
            vector_store =  client.vector_stores.retrieve(vector_store_id)
            vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store.id)
            for f in vector_store_files:
                remote_ids.append( f.id)
        return remote_ids


        

    def files_ok( self,*args, **kwargs):
        assistant = self
        file_ids = assistant.file_ids();
        remote_ids = assistant.remote_files();
        return set( remote_ids) == set( file_ids )


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


        def run_remote_query( context ):

            print(f"KWARGS = {context}")
            openai = context['openai']; 
            thread_id = context['thread_id'];
            assistant_id = context['assistant_id'];
            query = context['query'];
            last_messages=context['last_messages'];
            max_num_results = context['max_num_results']

            try :
                openai.beta.threads.messages.create( thread_id=thread_id,  role="user", content=query )
            except Exception as err :
                return 'Error in thread'

            truncation_strategy = { "type": "last_messages", "last_messages": last_messages }
            tools=[ { "type": "file_search", "file_search": { "max_num_results": max_num_results , "ranking_options": { "score_threshold": 0.0 } } } ]
            if last_messages is None:
                run = create_run_with_retry(thread_id, assistant_id, timeout, truncation_strategy, tools)
            else:
                run = create_run_with_retry(thread_id, assistant_id, timeout, truncation_strategy, tools)
            interval = 1;
            imax = settings.MAXWAIT / interval
            i = 0;
            print(f"CREATE RUN")
            while i < imax :
                run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                if run_status.status == "completed":
                    break
                elif run_status.status == "failed":
                    raise Exception(f"Run failed. {run_status}")
                else:
                    time.sleep(1)
                i = i + 1;
                print(f"I = {i}")
            usage = run_status.usage
            model = run.model
            assistant_id_ = run_status.assistant_id
            used_instructions =  client.beta.assistants.retrieve(assistant_id=assistant_id_).instructions
            assert i < imax , f"Request timed out after {settings.MAXWAIT} seconds; try again ; try to change the question."
            messages = openai.beta.threads.messages.list(thread_id=thread_id)
            i = 0;
            for msg in messages.data[::-1]:  # newest last
                i = i + 1 
                if msg.role == "assistant":
                    res = msg
            txt =   str( msg.content[0].text.value )
            txt = re.sub(r"【\d+:\d+†[^】]+】", "", txt)
            ntokens = len( encoding.encode(txt ) )
            ntokens = usage.total_tokens
            tokens = encoding.encode(txt)
            time_spent = int( time.time() - now  + 0.5 )
            characters = string.ascii_letters + string.digits  # a-zA-Z0-9
            h = ''.join(random.choices(characters, k=8))
            msg =  {'user' : query, 'assistant' : txt,
                    'ntokens' : ntokens ,
                    'model' : model,
                    'time_spent' : time_spent ,
                    'last_messages' : last_messages,
                    'max_num_results' : max_num_results,
                    'hash' : h }
            return msg

        context = {'openai' : openai, 'thread_id': thread_id, 'assistant_id' : assistant_id, 'query': query, 'last_messages' : last_messages, 'max_num_results' : max_num_results}
        msg = run_remote_query( context)
        thread.messages.append(msg) 
        thread.save()
        return msg






@receiver(pre_delete, sender=Assistant)
def custom_delete_assistant(sender, instance, **kwargs):
    pk = instance.pk
    try :
        assistant_id = instance.assistant_id
        #print(f"TRY DELETETING {assistant_id}")
        assistant = openai.beta.assistants.retrieve(assistant_id)
        #print(f"DELETE ASSISTANT {assistant}")
        tool_resources = assistant.tool_resources
        #print(f"TOOL_RESOURCES = {tool_resources}")
        vector_store_ids = tool_resources.file_search.vector_store_ids
        if vector_store_ids :
            vector_store_id = vector_store_ids[0];
            #print(f"VECTOR_STORES = {vector_store_id}")
            vector_store =  client.vector_stores.retrieve(vector_store_id)
            #print(f"VECTOR_STORE = {vector_store}")
            #print(f"VECTOR_STORE_NAME = {vector_store.name} {assistant_id}")
            if vector_store.name == assistant.id : # THIS IS HERE BECAUSE MULTIPL VECTOR STORES CAN'T BE USED BY AN ASSISTANT
                #print(f"DELETE REMOTE VECTOR STORE {assistant_id}")
                #client.vector_stores.delete(vector_store_id)
                delete_vector_store_and_wait(vector_store_id)
        #print(f"DELETED VECTOR STORE")
        res = client.beta.assistants.delete(assistant_id)
        #print(f"DELTED ASSISTANT")
        #print(f"RES = {res}")
    except Exception as err :
        print(f"ERROR = {str(err)}")


@receiver(m2m_changed, sender=Assistant.vector_stores.through)
def handle_assistants_changed(sender, instance, action, **kwargs):
    if getattr(instance, '_updating_from_m2m', False):
        return
    #if action == 'pre_add' :
    #    instance._updating_from_m2m = True
    #    return
    instance._updating_from_m2m = True
    try :
        instance._count = instance._count + 1 
    except :
        instance._count = 0 
    if instance._count > 1 :
        return

    assistant_id = instance.assistant_id
    rebuild = False
    if action == "post_remove":
        vector_stores = instance.vector_stores.all();
        assistant_id = instance.assistant_id
        assistant = openai.beta.assistants.retrieve(assistant_id)
        tool_resources = assistant.tool_resources
        try :
            vector_store_id = tool_resources.file_search.vector_store_ids[0]
            vector_store =  client.vector_stores.retrieve(vector_store_id)
            #print(f"VECTOR_STORE_NAME = {vector_store.name} {assistant_id} ")
            if vector_store.name == assistant_id  :
                #print(f"DELETINT VECTOR STORE SINCE INSNAT = VECTOR")
                #client.vector_stores.delete(vector_store_id)
                delete_vector_store_and_wait(vector_store_id)
            #print(f"REMAINING VECTOR_STORES TO BE SET UP {vector_stores}")
        except :
            #print(f"ERROR DELTING")
            pass
        rebuild = True
        #
        # TODO RESTORE THE VECTOR STORE HERE
        #

    if action == "post_add" or rebuild:
        pks = [];
        ids = [];
        file_ids = [];
        file_pks = []
        for f in instance.vector_stores.all() :
            file_ids.extend( f.file_ids() )
            file_pks.extend( f.file_pks() )
            pks.append( f.pk )
            ids.append( f.vector_store_id );
        file_ids = list( set( file_ids ) )
        file_ids.sort() 
        file_pks = list( set( file_pks ) )
        #print(f"IDS = {ids}")
        vsname = instance.name
        if len( ids ) < 1 :
            assistant = client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": ids }},
                metadata={"api_key": settings.AI_KEY[-8:] } 
                )
        else :
            vss = VectorStore.objects.filter(name=vsname).all();
            if vss :
                vs = vss[0]
            else :
                vs = VectorStore(name=vsname)
            vs.save();
            vs.files.set(file_pks)
            vs.save();
            instance.vector_stores.clear();
            instance.save();
            instance.vector_stores.set([vs.pk])
            instance.save();
            vector_store_id = vs.vector_store_id
            #vs = client.vector_stores.create( name=f"{assistant_id}", file_ids=file_ids, metadata={"api_key": settings.AI_KEY[-8:] } )
            #wait_for_vector_store_ready( client, vs.id )
            try :
                assistant = client.beta.assistants.update(
                    assistant_id=assistant_id,
                    tool_resources={"file_search": {"vector_store_ids": [ vector_store_id ] }},
                    metadata={"api_key": settings.AI_KEY[-8:] } 
                    )
            except Exception as e:
                print(f"CLIENT CANNOT UPDATE ASSISTANT {str(e)}")
        #while True:
        #    a = client.beta.assistants.retrieve(assistant.id)
        #    if a.status == "ready":
        #        break
        #    elif a.status == "failed":
        #        raise Exception("Assistant creation failed.")
        #    time.sleep(1)

    instance.save()
    del instance._updating_from_m2m



#@receiver(post_save, sender=Assistant)
#def assistant_post_save(sender, instance, created,  *args, **kwargs):
#    print(f"ARGS={args} KWARGS={kwargs}")
#    print(f'New {sender.__name__} created: {instance}')
#    if created :
#        if len( instance.vector_stores.all() ) == 0  :
#            print(f"LEN = 0 ")
#            p = instance.parent();
#            print(f"P = {p}")
#            i = 0;
#            #while p and i < 4  :
#            for v in p.vector_stores.all() :
#                print(f"ADD {v}")
#                instance.vector_stores.add(v);
#                p = instance.parent();

@receiver(m2m_changed, sender=VectorStore.files.through)
def handle_files_changed(sender, instance, action, **kwargs):
    print(f"HANDLE_SENDER_VECTOR_STORE action={action} ")
    if action == "post_add" or action == 'post_remove' :
        if getattr(instance, '_updating_from_m2m', False):
            return
        instance._updating_from_m2m = True
        vector_store_id = instance.vector_store_id
        vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store_id)
        old_file_ids = []
        for vector_store_file in vector_store_files :
            file_id = vector_store_file.id
            old_file_ids.append(file_id)
            #try :
            #    client.vector_stores.files.delete( vector_store_id=vector_store_id, file_id=file_id)
            #except :
            #    print(f"FILE ERROR {file_id}")
        new_file_ids = []
        for f in instance.files.all() :
            new_file_ids.extend( f.file_ids )
        #print(f"OLD_FILE_IDS = {old_file_ids} ")
        #print(f"NEW_FILE_IDS = {new_file_ids} ")
        pks = [];
        ids = [];
        cksums = []
        for f in instance.files.all() :
            pks.append( f.pk )
            ids.extend( f.file_ids );
            cksums.append( f.checksum)
        added_files = list( set( new_file_ids) - set( old_file_ids ) )
        subtracted_files = list( set( old_file_ids)  - set( new_file_ids) )
        print(f"ADDED_FILES = {set(added_files)}")
        print(f"SUBTRACTED_FILES = {set(subtracted_files)}")
        for file_id in subtracted_files :
            client.vector_stores.files.delete( vector_store_id=vector_store_id, file_id=file_id)
        for file_id in added_files :
            client.vector_stores.files.create( vector_store_id=vector_store_id, file_id=file_id,  )
        interval = 5;
        imax = settings.MAXWAIT / interval;
        i = 0;
        while i < imax :
            file_list = client.vector_stores.files.list(vector_store_id=vector_store_id)
            #print(f"FILE_LIST = {file_list}")
            statuses = [file.status for file in file_list.data]
            #print(f"STATUSES = {statuses}")
            if all(status == "completed" for status in statuses):
                #print("✅ All files processed and ready!")
                break
            elif any(status == "failed" for status in statuses):
                raise Exception(f"❌ Some files failed to process! {statuses}")
            else:
                #print(f"⏳ Current statuses: {statuses} - Waiting...")
                time.sleep(5)  # Wait before polling again
            i = i + 1 ;
        time.sleep(5)




        ids = list( set(ids ))
        pks = list( set(pks) )
        cksums = list( set( cksums) )
        cksums.sort()
        ckstring = ''.join(cksums).encode()
        checksum = hashlib.md5(ckstring).hexdigest()
        instance.checksum = checksum
        instance.save(update_fields=['checksum'])
        #others = VectorStore.objects.filter(checksum=checksum)
        #npks =  list( OpenAIFile.objects.filter(file_id__in=ids).values_list('pk',flat=True)  )
        #print(f"IDS = {ids} PKS = {pks}")
        del instance._updating_from_m2m
        #try :
        #    files = client.vector_stores.files.list(vector_store_id=vector_store_id)
        #except :
        #    files = []

        #is_done = False;
        #i = 0;
        #while not is_done  and i < 20 :
        #    is_done = True
        #    i = i + 1;
        #    for f in files:
        #        if f.status == 'in_progress' :
        #            is_done = False 
        #    time.sleep(1)

