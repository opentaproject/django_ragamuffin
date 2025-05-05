from django.db import models
import base64
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User, AnonymousUser
import shutil
import json
from .mathpix import mathpix

from django.db import transaction, IntegrityError
import logging
import time
import tiktoken
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import hashlib
import openai 
from openai import OpenAI
from django.db.models.signals import m2m_changed, pre_delete
from django.dispatch import receiver
import re

import os
logger = logging.getLogger(__name__)
client = openai.OpenAI(api_key=settings.AI_KEY)

upload_storage = FileSystemStorage(settings.OPENAI_UPLOAD_STORAGE, base_url="/" )

def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ['.md','.txt','.pdf','.tex']:
        raise ValidationError(f"Unsupported file extension '{ext}'.")

def hashed_upload_to(instance, filename):
    print(f"FILE_NAME = {instance.file.name}")
    dirname = instance.file.name.split('.')[0]
    os.makedirs(os.path.join( settings.OPENAI_UPLOAD_STORAGE, dirname ) ,  exist_ok=True)
    return os.path.join( dirname, instance.file.name )

def create_or_retrieve_vector_store( name , files) :
    vs = VectorStore.objects.filter(name=name)
    if not vs :
        vs = VectorStore(name=name)
        vs.save();
        vs.files.set(files)
        vs.save()
    else :
        vs = vs[0]
    return vs

def create_or_retrieve_assistant( name , vs ):
    assistants  = Assistant.objects.filter(name=name)
    if not assistants :
        assistant = Assistant(name=name)
        assistant.save()
        assistant.vector_stores.add(vs)
        assistant.save();
    else :
        assistant = assistants[0]
    return assistant

def create_or_retrieve_thread( assistant, name, user ) :
    if user.pk :
        threads = Thread.objects.filter(name=name,user=user)
    else :
        user = None
    threads = Thread.objects.filter(name=name,user=user)
    if not threads :
        thread = Thread(name=name,user=user)
        thread.save()
        thread.assistant = assistant
        thread.save()
    else :
        thread = threads[0]
    return thread







def upload_or_retrieve_openai_file( name ,src ):
    print(f"UPLOAD_OR_RETRIEVE NAME {name}")
    print(f"UPLOAD_OR_RETRIEVE SRC {src}")
    os.makedirs( os.path.join( settings.OPENAI_UPLOAD_STORAGE, name ), exist_ok=True )
    dst = os.path.join(os.path.join( settings.OPENAI_UPLOAD_STORAGE, name ), 'README.md')
    print(f"UPLOAD_OR_RETRIEV DST {dst}")
    name = dst.split('/')[-1];
    ts = OpenAIFile.objects.filter(name=name)
    if not ts :
        print(f" SRC={src} DST = {dst}")
        print(f"FILE NEEDST TO BE CREATED")
        shutil.copy2(src, dst)
        t1 = OpenAIFile(file=dst)
        t1.name = name
        t1.save()
    else :
        print(f"FILE EXISTS")
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

def chunk_mmd(lines):
    chunks = []
    current_chunk = []
    current_heading = None

    for line in lines:
        if re.match(r'^#{1,6} ', line):
            if current_chunk:
                chunks.append({
                    "heading": current_heading,
                    "content": ''.join(current_chunk).strip()
                })
            current_heading = line.strip()
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
    #s = ''
    #i = 0;
    #for i, chunk in enumerate(chunks ):
    #    s = s + json.dumps({ "id": f"chunk_{i}", "text": f"{chunk['heading']}\n{chunk['content']}" }) + "\n"
    #    i = i + 1 ;
    #    print(f"I = {i}")
    return s.encode('utf-8')





class OpenAIFile(models.Model) :
    date = models.DateTimeField(auto_now=True)
    checksum = models.CharField(blank=True, max_length=255)
    name = models.CharField(max_length=255,blank=True)
    path = models.CharField(max_length=255,blank=True)
    file_id = models.CharField(max_length=255,blank=True)
    file_ids = models.JSONField(default=list, null=True, blank=True)
    file = models.FileField( max_length=512, upload_to=hashed_upload_to, storage=upload_storage, validators=[validate_file_extension] )
    ntokens = models.IntegerField(default=0,null=True, blank=True)
    

    def __str__(self):
        return f"{self.name}"



    def save( self, *args, **kwargs ):
        is_new = self._state.adding  and not self.pk
        print(f"SAVE FILE ORIG {self.file}")
        name = f"{self.file}".split('/')[-1]
        super().save(*args, **kwargs)  # Save first, so file is processed
        print(f"SAVE FILE AFTER SUPER {self.file}")
        if is_new and self.file:
            print(f"SELF.FILE.NAME = { self.file.name}")
            #fn = hashed_upload_to(self , self.file.name )
            fn = self.file.name 
            print(f"FN = {fn}")
            self.name = self.file.name.split('/')[-1]
            src = self.file.path
            extension = src.split('.')[-1];
            if extension == 'pdf' :
                txt = mathpix( src ,format_out='mmd')
                print(f"TXT = {txt}")
            else :
                txt = ( open(src,'rb').read() ).decode('utf-8')
            chunks = chunk_mmd(txt)
            chunkdir = os.path.join( os.path.dirname( src ), 'chunks')
            os.makedirs( chunkdir, exist_ok=True )
            dst = os.path.join( chunkdir, os.path.basename( src) )
            #print(f"CHUNKS = {chunks}")
            if chunks :
                open( dst, "wb").write( chunks)
            else :
                shutil.copy2(src, dst)
            print(f"FN = {fn}")
            data = self.file.read()
            self.checksum = hashlib.md5(data).hexdigest()
            print(f"FILE_PATH = {self.file.path}")
            uploaded_file = openai.files.create( file=open( dst, "rb"), purpose="assistants")
            #self.file_id = uploaded_file.id
            self.file_ids = [uploaded_file.id ]
            self.path = os.path.dirname( self.file.path )
            encoding = tiktoken.encoding_for_model(settings.AI_MODEL)
            #self.ntokens = len( encoding.encode(data.decode('utf-8' )) )
            print(f"PATH = { self.path}")
            print(f"NOW AFTER CHUNKING NAME IS {self.name}")
            self.name = name
            super().save(*args, **kwargs) # Then update with true hashed path



@receiver(pre_delete, sender=OpenAIFile)
def custom_delete_openaifile(sender, instance, **kwargs):
    print(f"CUSTOM_DELETE_OPENAIFILE {instance.path} ")
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
                print(f"DELETED {instance.name}")
            except openai.NotFoundError as e:
                print(f"ERROR DELETING {instance.name}")
                pass

class VectorStore( models.Model ):
    checksum = models.CharField(blank=True, max_length=255)
    vector_store_id = models.CharField(max_length=255,blank=True)
    name =  models.CharField(max_length=255,unique=True)
    files = models.ManyToManyField( OpenAIFile )

    def __str__(self):
        return f"{self.name}"

    def file_ids(self, *args, **kwargs ):
        files = self.files
        ids = []
        for f in files.all():
            ids.extend( f.file_ids )
            #for file_id in f.file_ids :
            #    ids.append(file_id)
        print(f"IDS IN VECTOR_STORE IS {ids}")
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
        print(f"FILE_IDS = {file_ids}")
        vector_store_id = vs.vector_store_id
        vector_store =  client.vector_stores.retrieve(vector_store_id)
        vector_store_files = client.vector_stores.files.list( vector_store_id=vector_store.id)
        remote_ids = []
        for f in vector_store_files:
            remote_ids.append( f.id)
        print(f"REMOTE_IDS = {remote_ids}")
        #assert  set( file_ids) == set( remote_ids) , f"{file_ids} == {remote_ids} is false "
        return set( file_ids) == set( remote_ids) 



    def save( self, *args, **kwargs ):
        is_new = self._state.adding and not self.pk
        print(f"IS_NEW = {is_new}")
        super().save(*args,**kwargs)
        print(f"DID SUPER SAVE")
        if is_new :
            vector_store = client.vector_stores.create(name=self.name,metadata={"api_key": settings.AI_KEY[-8:] } )
            self.vector_store_id = vector_store.id
            super().save(*args,**kwargs)

@receiver(pre_delete, sender=VectorStore)
def custom_delete_vector_store(sender, instance, **kwargs):
    try :
        vector_store_id = instance.vector_store_id
        print(f"DELETE VECTOR_STORE{vector_store_id}")
        client.vector_stores.delete(vector_store_id=vector_store_id)
    except openai.NotFoundError as e:
        pass


class Assistant( models.Model ):
    name =   models.CharField(max_length=255,blank=True)
    instructions = models.TextField(blank=True)
    vector_stores = models.ManyToManyField( VectorStore )
    assistant_id = models.CharField(max_length=255,blank=True)
    json_field = models.JSONField( default=dict ,  blank=True, null=True)

    def __str__(self):
        return f"{self.name}"


    def save( self, *args, **kwargs ):
        is_new = self._state.adding and not self.pk
        if self.pk :
            old = Assistant.objects.get(pk=self.pk)
            old_instructions = old.instructions
        else :
            old_instructions = ''
        temperature = self.json_field.get('temperature', 0.2 )
        if self.instructions== '' :
            self.instructions = 'Answer only questions about the enclosed document. Do not offer helpful answers to questions that do not refer to the document. Be concise. If the question is irrelevant, answer with "That is not a question that is relevant to the document."'
        instructions = self.instructions
        super().save(*args,**kwargs)
        print(f"ASSISTANT_SAVE INSTRUCTIONS = {instructions}")
        if is_new :
            print(f"SETTING TEMPPERATUR TO {temperature}")
            print(f"SETTING INSTRUCTIONS TO {instructions}")
            assistant = client.beta.assistants.create( name=self.name,
                instructions=instructions, 
                model=settings.AI_MODEL, 
                temperature=temperature,
                tools=[{"type": "file_search"}],metadata={"api_key": settings.AI_KEY[-8:] } )
            self.assistant_id = assistant.id
            super().save(*args,**kwargs)
        else :
            if not old_instructions  ==  self.instructions :
                print(f"REVISE INSTRUCTIONS")
                assistant_id = self.assistant_id
                client.beta.assistants.update(assistant_id, instructions=instructions)




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
        print(f"ASSISTANT F = {f}")
        f = list( set( f) )
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

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'user'], name='unique_thread')
        ]
    

    def __str__(self):
        return f"{self.name}"




    def save( self, *args, **kwargs ):
        is_new = self._state.adding  and not self.pk
        super().save(*args, **kwargs)  # Save first, so file is processed
        if is_new  :
            thread = client.beta.threads.create(); 
            thread_id = thread.id
            self.thread_id = thread_id
            self.messages = []
            super().save(*args, **kwargs) # Then update with true hashed path

    def run_query( self, *args, **kwargs  ):
        last_messages = kwargs.get('last_messages',None)
        query= kwargs['query']
    
        """ last_messages is either None for auto or an integer for length of thread history to keep at OpenAI. 
        The entire history is kept in the local database"""
    
        assistant = self.assistant
        assistant_id = assistant.assistant_id
        thread = self
        thread_id = thread.thread_id
        print(f"QUERY_ID = {assistant_id} RUN_QUERY ")
    
        encoding = tiktoken.encoding_for_model(settings.AI_MODEL)
        try :
            openai.beta.threads.messages.create( thread_id=thread_id,  role="user", content=query )
        except Exception as err :
            return 'Error in thread'
        if last_messages == None :
            run = openai.beta.threads.runs.create( thread_id=thread_id, assistant_id=assistant_id )
        else :
            run = openai.beta.threads.runs.create( thread_id=thread_id, assistant_id=assistant_id ,  
                    truncation_strategy={ "type": "last_messages", "last_messages": last_messages })
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                raise Exception(f"Run failed. {run_status}")
            else:
                print("Waiting for completion...")
                time.sleep(1)
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        i = 0;
        for msg in messages.data[::-1]:  # newest last
            i = i + 1 
            if msg.role == "assistant":
                res = msg
        txt =   str( msg.content[0].text.value )
        txt = re.sub(r"【\d+:\d+†[^】]+】", "", txt)
        ntokens = len( encoding.encode(txt ) )
        txt = txt + f"<p/> *[{ntokens} tokens]*"
        tokens = encoding.encode(txt)
        print(f"RETGURN TOKENS = {len(tokens)} REPLY = {txt}")
        thread.messages.append({'user' : query, 'assistant' : txt, 'ntokens' : ntokens }) 
        thread.save()
        return txt






@receiver(pre_delete, sender=Assistant)
def custom_delete_assistant(sender, instance, **kwargs):
    pk = instance.pk
    assistant_id = instance.assistant_id
    assistant = openai.beta.assistants.retrieve(assistant_id)
    print(f"DELETE ASSISTANT {assistant}")
    tool_resources = assistant.tool_resources
    print(f"TOOL_RESOURCES = {tool_resources}")
    try :
        vector_store_id = tool_resources.file_search.vector_store_ids[0]
        print(f"VECTOR_STORES = {vector_store_id}")
        vector_store =  client.vector_stores.retrieve(vector_store_id)
        print(f"VECTOR_STORE = {vector_store}")
        print(f"VECTOR_STORE_NAME = {vector_store.name}")
        if vector_store.name == assistant_id : # THIS IS HERE BECAUSE MULTIPL VECTOR STORES CAN'T BE USED BY AN ASSISTANT
            client.vector_stores.delete(vector_store_id)
    except :
        pass
    client.beta.assistants.delete(assistant_id)


@receiver(m2m_changed, sender=Assistant.vector_stores.through)
def handle_assistants_changed(sender, instance, action, **kwargs):
    print(f"HANDLE_CHANGE_SENDER_ASSISTANT")
    if getattr(instance, '_updating_from_m2m', False):
        return
    instance._updating_from_m2m = True
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
            client.vector_stores.delete(vector_store_id)
            print(f"REMAINING VECTOR_STORES TO BE SET UP {vector_stores}")
        except :
            print(f"ERROR DELTING")
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
        print(f"IDS = {ids}")
        if len( ids ) < 2 :
            assistant = client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": ids }},
                metadata={"api_key": settings.AI_KEY[-8:] } 
                )
        else :
            vs = client.vector_stores.create( name=f"{assistant_id}", file_ids=file_ids, metadata={"api_key": settings.AI_KEY[-8:] } )
            assistant = client.beta.assistants.update(
                assistant_id=assistant_id,
                tool_resources={"file_search": {"vector_store_ids": [ vs.id ] }},
                metadata={"api_key": settings.AI_KEY[-8:] } 
                )

    instance.save()
    del instance._updating_from_m2m





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
        print(f"OLD_FILE_IDS = {old_file_ids} ")
        print(f"NEW_FILE_IDS = {new_file_ids} ")
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
        while True:
            file_list = client.vector_stores.files.list(vector_store_id=vector_store_id)
            print(f"FILE_LIST = {file_list}")
            statuses = [file.status for file in file_list.data]
            print(f"STATUSES = {statuses}")
            if all(status == "completed" for status in statuses):
                print("✅ All files processed and ready!")
                break
            elif any(status == "failed" for status in statuses):
                raise Exception(f"❌ Some files failed to process! {statuses}")
            else:
                print(f"⏳ Current statuses: {statuses} - Waiting...")
                time.sleep(5)  # Wait before polling again
        time.sleep(5)




        ids = list( set(ids ))
        pks = list( set(pks) )
        cksums = list( set( cksums) )
        cksums.sort()
        ckstring = ''.join(cksums).encode()
        checksum = hashlib.md5(ckstring).hexdigest()
        instance.checksum = checksum
        #others = VectorStore.objects.filter(checksum=checksum)
        npks =  list( OpenAIFile.objects.filter(file_id__in=ids).values_list('pk',flat=True)  )
        print(f"IDS = {ids} PKS = {pks}")
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

