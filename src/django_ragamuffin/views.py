from django.shortcuts import render
import pypandoc
from django.http import HttpResponseForbidden
from django.core.exceptions import PermissionDenied
import json
from django.http import JsonResponse, FileResponse
import tiktoken
from django.core.files.storage import FileSystemStorage
from django.shortcuts import get_object_or_404, redirect, render
from django_ragamuffin.models import OpenAIFile, VectorStore, Assistant,  Thread, hashed_upload_to, upload_or_retrieve_openai_file, get_current_model, DEFAULT_INSTRUCTIONS
import time
from django_ragamuffin.models import create_or_retrieve_vector_store, create_or_retrieve_assistant, create_or_retrieve_thread
from .forms import QueryForm
from django.contrib.auth.models import User
from django.urls import reverse
import re
import markdown2
from .models import upload_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django import forms
import subprocess
import tempfile
from pathlib import Path
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

head = " \
\\documentclass{article}\n\
\\usepackage{amsmath} \n\
\\usepackage[a4paper, right=2.5cm, left=2.0cm, top=1.5cm]{geometry} \n\
\\usepackage{graphicx} \n\
\\usepackage{mdframed} \n\
\\usepackage{amsmath} \n\
\\usepackage{fancyhdr,hyperref,mathrsfs}\n\
\\pagestyle{fancy}\n\
\\fancyhf{} \n\
\\providecommand{\\tightlist}{\n\
  \\setlength{\\itemsep}{0pt}\\setlength{\\parskip}{0pt}}\n\
\\begin{document} \n\
\\setlength{\parindent}{0pt} \n\
\\setlength{\parsep}{2pt} \n\
\\setlength{\\fboxsep}{5pt}   \n\
\\setlength{\\fboxrule}{0.5pt}"
tail = "\n\\end{document}"
boxhead = "\n\n\\fbox{\n\
\\parbox{\\dimexpr\\linewidth-2\\fboxsep-2\\fboxrule\\relax}{\n"
boxtail = "\n}}\n\\vspace{12pt}\n"

boxhead = "\n\n\\hspace*{-20pt}\\fbox{\n\
\\parbox{\\dimexpr\\linewidth-2\\fboxsep-2\\fboxrule\\relax}{\n"




#def break_after_all_equals(tex_content, max_length=80):
#
#    def break_equation(match):
#        full = match.group(0)
#        inner = match.group(1)
#
#        # Only process if line is long enough and has equal signs
#        if len(inner) < max_length or '=' not in inner:
#            return full
#
#        # Split on '=' and rejoin with '= \\' after each
#        parts = inner.split('=')
#        broken = parts[0].strip()
#        for part in parts[1:]:
#            broken += ' =  ' + part.strip()
#            print(f"broken={broken}")
#        return full.replace(inner, broken)
#
#    math_patterns = [
#        re.compile(r'\\\[(.*?)\\\]', re.DOTALL),
#        re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
#    ]
#
#    for pattern in math_patterns:
#        tex_content = pattern.sub(break_equation, tex_content)
#
#    return tex_content
#

MAX_OLD_QUERIES = 30
def mathfix( txt ):
    txt = re.sub(r"_","UNDERSCORE",txt)
    txt = re.sub(r"\\\(",'$',txt)
    txt = re.sub(r"\\\)",'$',txt)
    txt = re.sub(r"\\\[",'LEFTBRAK',txt)
    txt = re.sub(r"\\\]",'RIGHTBRAK',txt)
    txt = markdown2.markdown( txt )
    txt = re.sub(r"LEFTBRAK",'<p/>$\\;',txt)
    txt = re.sub(r"RIGHTBRAK",'\\;$<p/>',txt)
    txt = re.sub(r"UNDERSCORE",'_',txt)
    txt = markdown2.markdown(txt)
    return txt


def tex_to_pdf(tex_code , output_dir="output", jobname="document"):
    # Create a temp directory for compilation
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    tex_file = output_path / f"{jobname}.tex"
    with tex_file.open("w") as f:
        f.write(tex_code )
    
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_file.name],
        cwd=output_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    return output_path / f"{jobname}.pdf"


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
        r = render(request, 'django_ragamuffin/upload.html', {'file_url': file_url})
        return redirect(f"/assistant/{pk}/edit/")

    return render(request, 'django_ragamuffin/upload.html')

class AssistantEditForm(forms.ModelForm):

    actual_instructions = forms.CharField(disabled=True, required=False, widget=forms.Textarea(attrs={'disabled': 'disabled'}),)
    directory_name = forms.CharField(required=False, help_text=mark_safe('<div class="instructions"> Change name of the directory </div> ') )
    

    def __init__(self, *args, **kwargs):
        self.custom_data = kwargs.pop("custom_data", {})
        super().__init__(*args, **kwargs)
        instance = self.instance
        # Set initial value for the readonly field
        #self.fields['actual_instructions'].initial = instance.get_instructions() + ' '.join( DEFAULT_INSTRUCTIONS.split() )  if self.instance.pk else "N/A"
        if self.instance.pk :
            instructions = ' '.join( instance.get_instructions().split() );
            directory_name = instance.name.split('.')[-1];
        self.fields['directory_name'].initial = instance.name.split('.')[-1];
        self.fields['actual_instructions'].initial = instructions if self.instance.pk else "N/A"




    class Meta:
        model = Assistant
        fields = ['instructions','actual_instructions', 'temperature','directory_name']
        help_texts = {
            'directory_name' : "Only the last directory can be renmamed; all children will be renamed",
            'temperature': f"<p/>Default temperature = {settings.DEFAULT_TEMPERATURE}",
            'instructions' : f"<b> Incremental instructions: </b>  <br>Leave or make blank to inherit default; <br> Start the field with 'append: XXX...' to append 'XXX...' to default; <br>Any other non-blank string completely replaces the default instructions.'<br> The entire instructions used by the assistant is shown below."

        }





def delete_assistant(request, pk):
    assistant = get_object_or_404(Assistant, pk=pk)
    children = assistant.children()
    if children :
        referer = request.META.get('HTTP_REFERER', '/')
        return redirect( referer )
        #return HttpResponseForbidden("You cannot delete an assistant with children.")
    threads = assistant.threads.all();
    for thread in threads :
        thread.delete();
    parent = assistant.parent();
    referer = request.META.get('HTTP_REFERER', '/')
    path = parent.path();
    assistant.delete();
    return redirect('/query/' + path)
    #return render(request, 'django_ragamuffin/edit_assistant.html', {'form': form, 'assistant': assistant, 'custom_data' : form.custom_data  })

def edit_assistant(request, pk):
    assistant = get_object_or_404(Assistant, pk=pk)
    if request.method == 'POST':
        deletions = request.POST.getlist('deletion')
        if deletions :
            for f in deletions :
                #print(f"DELETE THE FILE {f}")
                assistant.delete_file(f)
        new_tail = request.POST.getlist('directory_name',[None])[0]
        old_tail = assistant.name.split('.')[-1];
        if True or not old_tail == new_tail :
            old_name = assistant.name;
            new = ( assistant.name.split('.')[:-1]  )
            new.append(new_tail)
            new_name = '.'.join(new)
            pattern = r'^%s\..+$' % old_name


            tree = Assistant.objects.filter(name__regex=pattern).all()
            p = r'^%s' % old_name 
            for a in tree :
                n = re.sub( p , new_name, a.name)
                a.name = n
                a.save(update_fields=['name']);
            n = re.sub( p, new_name, assistant.name)
            assistant.name = new_name
            
            pattern = r'^%s(\..*$|$)' % old_name
            tree = Thread.objects.filter(name__regex=pattern).all()
            p = r'^%s' % old_name 
            for a in tree :
                n = re.sub( p , new_name, a.name)
                a.name = n
                a.save(update_fields=['name']);
            #threads = Thread.objects.filter(name=old_name)
            #if threads :
            #    for thread in threads :
            #        n = re.sub( p, new_name, thread.name)
            #        print(f"FINALLY {thread.name} ->  {n}")
            #        thread.name = new_name
            #        #thread.save(update_fields=['name'])


        form = AssistantEditForm(request.POST, instance=assistant )
        if form.is_valid():
            form.save()
            return redirect('edit_assistant', pk=assistant.pk)  # or another success URL
    else:
        form = AssistantEditForm(instance=assistant, custom_data=assistant.files() )
    #print(f"FORM_CUSTOM_DATA = {form.custom_data}")
    return render(request, 'django_ragamuffin/edit_assistant.html', {'form': form, 'assistant': assistant, 'custom_data' : form.custom_data  })




FILENAME = "../README.md"
@csrf_exempt
@login_required
def feedback_view(request,subpath):
    #print(f"SUBPATH IN FEEDBACK= {subpath}")
    #print(f"SUBPATH IN QUERYVIEW = {subpath}")
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
    #print(f"SUBPATH IN QUERYVIEW = {subpath}")
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
        #print(f"BASE= {base}")
        subdir = name.split('.')[-1];
        #print(f"SUBDIR = {subdir}")
        base_assistant = get_assistant( base, user );
        #print(f"BASE_ASSITANT = {base_assistant}")
        if base_assistant :
            assistant = base_assistant.clone( name )
        else :
            assistant = None
        return assistant

    assistant = get_assistant( name, request.user  )
    if assistant == None :
        if request.user.is_staff :
            assistant = Assistant(name=name);
            assistant.save();
        else :
            return HttpResponseForbidden(f"No assistant <b>{name} </b> exists.")
    model = assistant.model
    thread = create_or_retrieve_thread( assistant, name , user )
    data = request.POST;
    if 'delete' in request.POST.getlist('action') :
        deletes = request.POST.getlist('entry')
        if deletes :
            messages = thread.messages;
            ideletes = [int(i) for i in deletes ];
            culled = [x for i,x in enumerate(messages) if i not in ideletes ]
            thread.messages= culled
            thread.save(update_fields=["messages","thread_id"])
    elif 'print' in request.POST.getlist('action') :
        prints = request.POST.getlist('entry')

        def thread_to_pdf( thread , prints ):
            messages = thread.messages;
            iprints = [int(i) for i in prints ];
            ps = [(i,x) for i,x in enumerate(messages) if i in iprints ]

            file = open("/tmp/tmp.tex","w");
            file.write(head)
            for (i,p) in ps :
                msg = p;
                q = msg['user'];
                r = msg['assistant']
                r =  mark_safe( mathfix(r)  );
                r = pypandoc.convert_text( r ,'latex', format='html+raw_tex', extra_args=["--wrap=preserve"]  )
                def pandoc_fix(r) :
                    r = re.sub(r'\\\$','$',r);
                    r = re.sub(r'\\\(','$',r);
                    r = re.sub(r'\\\)','R',r);
                    r = re.sub(r'\\_','_',r);
                    r = re.sub(r'textbackslash *','',r)
                    r = re.sub(r'\\textquotesingle',"\'",r)
                    r = re.sub(r'\\{','{',r);
                    r = re.sub(r'\\}','}',r);
                    r = re.sub(r'\\\^','^',r);
                    r = re.sub(r'\\textgreater','>',r)
                    r = re.sub(r'textasciitilde','',r)
                    r = re.sub(r'{}','',r)
                    r = re.sub(r'{\[}','[',r);
                    r = re.sub(r'{\]}',']',r);
                    r = re.sub(r'\\;\$','\\]',r)
                    r = re.sub(r'\$\\;','\\[',r)
                    r = re.sub(r'section{','section*{\\\\textbullet \\\\hspace{5px} ',r)
                    #r = break_after_all_equals( r , max_length=10)
                    return r
                r = pandoc_fix(r)
                choice = msg.get('choice',0)
                v = CHOICES[choice]
                time_spent = msg.get('time_spent',0);
                model = msg.get('model','None')
                #file.write(f"\\fancyhead[R]{{ \\hspace{{1cm}} \\textbf{{ {name} }} }}\n");
                file.write(f"\\fancyhead[R]{{\\makebox[0pt][l]{{\\hspace{{-4cm}}\\textbf{{ {name} }}}} }} ")
                file.write(boxhead)
                #file.write(f"\n\\textbf{{Assistant: {name} }}\n\\vspace{{8pt}}\n\n")
                file.write(f"\n\\textbf{{Question {i} :}} {q}\n{boxtail}\n\\textbf{{Response:}} {r}\n")
                file.write(f"\n\\vspace{{8pt}}\n") 
                file.write(f"\n\\textbf{{tokens={msg.get('ntokens',0)} dt={time_spent} model={model} choice={choice} {v} }} \\vspace{{12pt}} \n\n " )
            file.write(tail)
            file.close();
            try :
                file  = open("/tmp/tmp.tex","rb")
                s = file.read();
                s = s.decode('utf-8')
                pdf = tex_to_pdf(s,"/tmp/")
                pdf_path = "/tmp/document.pdf"
                return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
            except  Exception as err :
                tex_path = "/tmp/tmp.tex"
                return FileResponse(open(tex_path, 'rb'), content_type='application/tex')


        if prints :
            response = thread_to_pdf( thread , prints )
            return response


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
                    ntokens = message.get('ntokens')
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
    p = assistant.parent();
    children = assistant.children();
    parent = assistant.parent();
    response = render(request, 'django_ragamuffin/query_form.html', {
        'parent' : parent,
        'children' : children,
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
