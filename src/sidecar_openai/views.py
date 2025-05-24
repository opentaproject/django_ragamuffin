from django.shortcuts import render
import json
from django.http import JsonResponse
import tiktoken
from django.shortcuts import redirect
from sidecar_openai.models import OpenAIFile, VectorStore, Assistant,  Thread, hashed_upload_to, upload_or_retrieve_openai_file, get_current_model
import time
from sidecar_openai.models import create_or_retrieve_vector_store, create_or_retrieve_assistant, create_or_retrieve_thread
from .forms import QueryForm
from django.contrib.auth.models import User
from django.urls import reverse
import re
import markdown2
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
import shutil
import os
import markdown
from django.utils.safestring import mark_safe
import string, random

import openai 
from openai import OpenAI
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

import asyncio

MAX_OLD_QUERIES = 30
def mathfix( txt ):
    txt = re.sub(r"_","UNDERSCORE",txt)
    txt = re.sub(r"\\\(",'$',txt)
    txt = re.sub(r"\\\)",'$',txt)
    txt = re.sub(r"\\\[",'LEFTBRAK',txt)
    txt = re.sub(r"\\\]",'RIGHTBRAK',txt)
    txt = markdown2.markdown( txt )
    txt = re.sub(r"LEFTBRAK",'<p/>$',txt)
    txt = re.sub(r"RIGHTBRAK",'$ <p/>',txt)
    txt = re.sub(r"UNDERSCORE",'_',txt)
    txt = markdown2.markdown(txt)
    return txt


def get_hash() :
 characters = string.ascii_letters + string.digits  # a-zA-Z0-9
 h = ''.join(random.choices(characters, k=8))
 return h


def doarchive( thread, msg ):
    assistant = thread.assistant;
    h = msg.get('hash',get_hash() )
    subdir =  assistant.name.split('.')
    p = os.path.join('/subdomain-data','openai','queries', *subdir,thread.user.username,)
    os.makedirs(p, exist_ok=True )
    fn = f"{p}/{h}.json"
    msgsave = msg
    msgsave.update({'name' : assistant.name,'hash' : h })
    with open(fn, "w") as f:
        json.dump(msgsave,  f , indent=2)


FILENAME = "../README.md"
@csrf_exempt
@login_required
def feedback_view(request,subpath):
    print(f"SUBPATH IN FEEDBACK= {subpath}")
    print(f"SUBPATH IN QUERYVIEW = {subpath}")
    subpath_ = re.sub( r"\.","_",subpath )
    segments = subpath_.split('/')
    last_messages = settings.LAST_MESSAGES;
    max_num_results = settings.MAX_NUM_RESULTS;
    name = ( '.'.join( segments ) ).rstrip('.')
    choices = {0 : 'Unread' ,
               1 : 'Incomplete' , 
               2 : 'Wrong', 
               3 : 'Irrelevant',
               4 : "Superficial." ,  
               5 : "Unhelpful", 
               6 : 'Partly Correct', 
               7 : 'Completely Correct'}
    choice = 0;
    index = int( request.POST.getlist('newmessage_index')[0] )
    post_thread =  re.sub(r'\.','_',request.POST.getlist('thread')[0])
    thread_name = ( '.'.join( post_thread.split('/')[2:] ) ).rstrip('.');
    threads = Thread.objects.filter(name=thread_name,user=request.user)
    thread = threads[0]
    comment = ''
    comments =  request.POST.getlist('comment')
    options  =  request.POST.getlist('option' );
    choice= 0
    if comments :
        comment = comments[0]
    elif options :
        i = int( options[0] );
        comment = options[1];
        choice = i
    if len( thread.messages) > 0 :
        thread.messages[index].update( {'comment': comment , 'choice' : choice })
        msg = thread.messages[index];
        thread.save();
        doarchive(thread, msg )
    return JsonResponse({"success": True,'index' : index ,'comment' : comment , 'choice' :choice  })







FILENAME = "../README.md"
@csrf_exempt
@login_required
def query_view(request,subpath):
    print(f"SUBPATH IN QUERYVIEW = {subpath}")
    subpath_ = re.sub( r"\.","_",subpath )
    segments = subpath_.split('/')
    last_messages = settings.LAST_MESSAGES;
    max_num_results = settings.MAX_NUM_RESULTS;
    name = ( '.'.join( segments ) ).rstrip('.')
    choices = {0 : 'Unread' ,
               1 : 'Incomplete' , 
               2 : 'Wrong', 
               3 : 'Irrelevant',
               4 : "Superficial." ,  
               5 : "Unhelpful", 
               6 : 'Partly Correct', 
               7 : 'Completely Correct'}
    choice = 0;
    #if name == '.feedback' :
    #    index = int( request.POST.getlist('newmessage_index')[0] )
    #    post_thread =  re.sub(r'\.','_',request.POST.getlist('thread')[0])
    #    thread_name = ( '.'.join( post_thread.split('/')[2:] ) ).rstrip('.');
    #    threads = Thread.objects.filter(name=thread_name,user=request.user)
    #    thread = threads[0]
    #    comment = ''
    #    comments =  request.POST.getlist('comment')
    #    options  =  request.POST.getlist('option' );
    #    choice= 0
    #    if comments :
    #        comment = comments[0]
    #    elif options :
    #        i = int( options[0] );
    #        comment = options[1];
    #        choice = i
    #    thread.messages[index].update( {'comment': comment , 'choice' : choice })
    #    msg = thread.messages[index];
    #    thread.save();
    #    doarchive(thread, msg )
    #    return JsonResponse({"success": True,'index' : index ,'comment' : comment , 'choice' :choice  })
    response = None
    user = request.user


    def setup_default_assistant(src):
        name = src.split('/')[-1].split('.')[0]
        t1 = upload_or_retrieve_openai_file( name, src )
        vs = create_or_retrieve_vector_store( name, [t1])
        assistant = create_or_retrieve_assistant( name  , vs )
        return assistant

    def get_assistant( name, user ):
        assistants = Assistant.objects.filter(name=name)
        if assistants :
            assistant = assistants[0];
            return assistant
        base = '.'.join(name.split('.')[:-1])
        subdir = name.split('.')[-1];
        base_assistant = get_assistant( base, user );
        if base_assistant :
            assistant = base_assistant.clone( name )
        else :
            assistant = None
        return assistant

    def oldget_assistant( name , user ):
        assistants = Assistant.objects.filter(name=name)
        assistant_exists = False
        if assistants :
            assistant = assistants[0]
            vss = assistant.vector_stores.all()
            if vss :
                vs = vss[0]
                assistant_exists = True
        if not assistant_exists :
            if assistants :
                assistants[0].delete();
            assistant = setup_default_assistant( FILENAME );
            assistant.save()

        old_model = None
        if assistant.model :
            old_model = assistant.model
        new_model =  model = get_current_model( user )
        if not new_model == old_model :
            assistant.model = model
            assistant.save();
        return assistant

    assistant = get_assistant( name, request.user  )
    model = assistant.model
    thread = create_or_retrieve_thread( assistant, name , user )
    data = request.POST;
    deletes = request.POST.getlist('delete-entry')
    if deletes :
        messages = thread.messages;
        ideletes = [int(i) for i in deletes ];
        culled = [x for i,x in enumerate(messages) if i not in ideletes ]
        thread.messages= culled
        thread.save(update_fields=["messages","thread_id"])
    d = {'status' : 'pending' , 'result' : 'RESULT' }
    messages = thread.messages
    mindex = 0
    comment = ''
    time_spent = 0;
    now = time.time();
    ntokens = 0;
    if request.method == 'POST':
        form = QueryForm(request.POST)
        if form.is_valid():
            assistant_id = assistant.assistant_id 
            query = form.cleaned_data['query']
            txt = None
            for i,message in enumerate( messages ) :
                mindex = i+1;
                if query.strip()  == message['user'].strip() :
                    txt = "*You already asked that!*<p/>" + message['assistant']
                    comment = message.get('comment','')
                    choice = message.get('choice','0')
                    mindex = mindex - 1;
                    break
            try :
                if txt == None :
                    msg = thread.run_query(  query=query ,last_messages=last_messages, max_num_results=max_num_results)
                    txt = msg['assistant']
                    ntokens = msg['ntokens']
            except Exception as e:
                print(f"TXT = {txt}")
                txt = f"ERROR  {type(e).__name__} {str(e) }";
            txt = mathfix( txt )
            html = mark_safe(txt )
            response = f" <h4> Query: </h4>  {query}  <h4> Response: </h4> {html}  "
            response = f"{html}"
    else:
        form = QueryForm()
    time_spent = int( ( time.time() - now  ) + 0.5 )
    f = [ { 'index' : index, 'user' : item['user'] , 
       'assistant' : mark_safe( mathfix(item['assistant'] ) ),
       'ntokens' : item['ntokens'],
       'comment' : item.get('comment','') ,
       'choice' : item.get('choice',0),
       'model' : item.get('model', model) ,  
       'max_num_results' : item.get('max_num_results' , max_num_results ),
       'last_messages' : item.get('last_messages' , last_messages)  ,
       'time_spent' : item.get('time_spent', time_spent) }  for index, item in enumerate( messages ) ];
    response = render(request, 'sidecar_openai/query_form.html', {
        'form': form,
        'response': response,
        'messages' : f,
        'name' : assistant.name ,
        'mindex' : mindex ,
        'comment' : comment,
        'choices' : choices ,
        'choice' : choice ,
        'ntokens' : ntokens,
        'model' : model ,
        'max_num_results' : max_num_results,
        'last_messages' : last_messages ,
        'time_spent' : time_spent  })
    response.set_cookie('busy' , 'false')
    return response
