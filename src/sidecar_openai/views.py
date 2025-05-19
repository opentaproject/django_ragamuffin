from django.shortcuts import render
from django.http import JsonResponse
import tiktoken
from django.shortcuts import redirect
from sidecar_openai.models import OpenAIFile, VectorStore, Assistant,  Thread, hashed_upload_to, upload_or_retrieve_openai_file
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

import openai 
from openai import OpenAI
from django.views.decorators.csrf import csrf_exempt
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


FILENAME = "../README.md"
@csrf_exempt
def query_view(request,subpath):
    segments = subpath.split('/')
    name = ( '.'.join( segments ) ).rstrip('.')
    choices = {0 : 'Unread' ,1 : 'Wrong' , 2 : 'Irrelevant', 3 : 'I did not understand.',  4 : "Too superficial." ,  5: "Somewhat helpful", 6 : 'Very helpful', }
    choice = 0;
    if name == '.feedback' :
        index = int( request.POST.getlist('newmessage_index')[0] )
        thread_name = ( '.'.join( ( request.POST.getlist('thread')[0] ).split('/')[2:] ) ).rstrip('.');
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
            print(f"I = {i}")
            comment = options[1];
            choice = i
            #if other :
            #    comment = comment + ' ' + other
        thread.messages[index].update( {'comment': comment , 'choice' : choice })
        msg = thread.messages[index];
        thread.save();
        #print(f"REDIRECT TO query/{thread_name}")
        #return redirect( f'query/{thread_name}')
        return JsonResponse({"success": True,'index' : index ,'comment' : comment , 'choice' :choice  })
    response = None
    user = request.user
    assistants = Assistant.objects.filter(name=name)
    if assistants :
        assistant = assistants[0]
        vs = assistant.vector_stores.all()[0]
    else :
        src = FILENAME
        name = src.split('/')[-1].split('.')[0]
        t1 = upload_or_retrieve_openai_file( name, src )
        vs = create_or_retrieve_vector_store( name, [t1])
        assistant = create_or_retrieve_assistant( name  , vs )
        instructions = 'Answer only questions about the enclosed document. Do not offer helpful answers to questions that do not refer to the document. Be concise. If the question is irrelevant, answer with "That is not a question that is relevant to the document."'
        assistant.instructions = instructions
        assistant.save()
    if assistant.model :
        model = assistant.model
    else :
        model = settings.AI_MODEL
    thread = create_or_retrieve_thread( assistant, name , user )
    data = request.POST;
    deletes = request.POST.getlist('delete-entry')
    if deletes :
        messages = thread.messages;
        ideletes = [int(i) for i in deletes ];
        print(f"IDELETES = {ideletes}")
        culled = [x for i,x in enumerate(messages) if i not in ideletes ]
        print(f"CULLED LENGTH = {len( culled)}")
        thread.messages= culled
        thread.save(update_fields=["messages","thread_id"])
        print(f"THREAD WAS SAVED")

    d = {'status' : 'pending' , 'result' : 'RESULT' }
    messages = thread.messages
    mindex = 0
    comment = ''
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
                    txt = thread.run_query(  query=query ,last_messages=3, max_num_results=5)
                    #txt = thread.run_query(  query=query ,last_messages=None, max_num_results=None )
            except Exception as e:
                txt = str(e);
            txt = mathfix( txt )
            html = mark_safe(txt )
            response = f" <h4> Query: </h4>  {query}  <h4> Response: </h4> {html}  "
            response = f"{html}"
    else:
        form = QueryForm()
    #print(f"REQUEST = {request.POST}")
    f = [ { 'index' : index, 'user' : item['user'] , 'assistant' : mark_safe( mathfix(item['assistant'] ) ), 'ntokens' : item['ntokens'], 'comment' : item.get('comment','') , 'choice' : item.get('choice',0), 'model' : item.get('model', model )   }  for index, item in enumerate( messages ) ];
    response = render(request, 'sidecar_openai/query_form.html', {'form': form, 'response': response,'messages' : f, 'name' : assistant.name , 'mindex' : mindex , 'comment' : comment, 'choices' : choices , 'choice' : choice , 'model' : model })
    response.set_cookie('busy' , 'false')
    return response
