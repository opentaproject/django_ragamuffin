from django.shortcuts import render
from django.http import HttpResponseForbidden
import json
from django.http import JsonResponse
import tiktoken
from django.core.files.storage import FileSystemStorage
from django.shortcuts import get_object_or_404, redirect, render
from sidecar_openai.models import OpenAIFile, VectorStore, Assistant,  Thread, hashed_upload_to, upload_or_retrieve_openai_file, get_current_model
import time
from sidecar_openai.models import create_or_retrieve_vector_store, create_or_retrieve_assistant, create_or_retrieve_thread
from .forms import QueryForm
from django.contrib.auth.models import User
from django.urls import reverse
import re
import markdown2
from .models import upload_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django import forms
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

CHOICES = {0 : 'Unread' ,
           1 : 'Incomplete' , 
           2 : 'Wrong', 
           3 : 'Irrelevant',
           4 : "Superficial." ,  
           5 : "Unhelpful", 
           6 : 'Partly Correct', 
           7 : 'Completely Correct'}




def upload_file_view(request,pk):
    if request.method == 'POST' and request.FILES.get('myfile'):
        uploaded_file = request.FILES['myfile']
        filename = uploaded_file.name 
        assistant =  Assistant.objects.get(pk=pk)
        file_url = assistant.add_file( filename, uploaded_file)
        r = render(request, 'sidecar_openai/upload.html', {'file_url': file_url})
        return redirect(f"/assistant/{pk}/edit/")

    return render(request, 'sidecar_openai/upload.html')

class AssistantEditForm(forms.ModelForm):

    actual_instructions = forms.CharField(disabled=True, required=False, widget=forms.Textarea(attrs={'disabled': 'disabled'}),)
    

    def __init__(self, *args, **kwargs):
        self.custom_data = kwargs.pop("custom_data", {})
        super().__init__(*args, **kwargs)
        instance = self.instance
        # Set initial value for the readonly field
        #self.fields['actual_instructions'].initial = instance.get_instructions() + ' '.join( DEFAULT_INSTRUCTIONS.split() )  if self.instance.pk else "N/A"
        if self.instance.pk :
            instructions = ' '.join( instance.get_instructions().split() );
        self.fields['actual_instructions'].initial = instructions if self.instance.pk else "N/A"
        print(f"SELF.CUSTOM_DATA = {self.custom_data}")




    class Meta:
        model = Assistant
        fields = ['instructions','actual_instructions', 'temperature']
        help_texts = {
            'temperature': f"<p/>Default temperature = {settings.DEFAULT_TEMPERATURE}",
            'instructions' : f"<b> Incremental instructions: </b>  <br>Leave or make blank to inherit default; <br> Start the field with 'append: XXX...' to append 'XXX...' to default; <br>Any other non-blank string completely replaces the default instructions.'<br> The entire instructions used by the assistant is shown below."

        }


def edit_assistant(request, pk):
    assistant = get_object_or_404(Assistant, pk=pk)
    if request.method == 'POST':
        form = AssistantEditForm(request.POST, instance=assistant )
        if form.is_valid():
            form.save()
            return redirect('edit_assistant', pk=assistant.pk)  # or another success URL
    else:
        form = AssistantEditForm(instance=assistant, custom_data=assistant.files() )
    print(f"FORM_CUSTOM_DATA = {form.custom_data}")
    return render(request, 'sidecar_openai/edit_assistant.html', {'form': form, 'assistant': assistant, 'custom_data' : form.custom_data  })


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
    choices = CHOICES
    choice = 0;
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
        if base == '' :
            return None
        print(f"BASE= {base}")
        subdir = name.split('.')[-1];
        print(f"SUBDIR = {subdir}")
        base_assistant = get_assistant( base, user );
        print(f"BASE_ASSITANT = {base_assistant}")
        if base_assistant :
            assistant = base_assistant.clone( name )
        else :
            assistant = None
        return assistant

    assistant = get_assistant( name, request.user  )
    if assistant == None :
         return HttpResponseForbidden(f"No assistant <b>{name} </b> exists.")
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
            try:
                if txt is None:
                    msg = thread.run_query(query=query, last_messages=last_messages, max_num_results=max_num_results)
                    txt = msg['assistant']
                    ntokens = msg['ntokens']
            except (KeyError, AttributeError, ValueError) as e:
                txt = f"ERROR {type(e).__name__}: {str(e)}"
            except Exception  as e:
                txt = f"ERROR {type(e).__name__}: {str(e)}"
            try :
                txtnew = mathfix(txt)
                txt = txtnew 
            except Exception as err  :
                txt = txt + f": Mathfix error {type(err).__name__} {str(err)}"
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
        'assistant_pk' : assistant.pk ,
        'max_num_results' : max_num_results,
        'last_messages' : last_messages ,
        'time_spent' : time_spent  })
    response.set_cookie('busy' , 'false')
    return response
