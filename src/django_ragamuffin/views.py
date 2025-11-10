from django.shortcuts import render, get_object_or_404, redirect
from django.forms.models import model_to_dict
from django.utils import timezone 
import logging
from django.http import HttpResponseForbidden, JsonResponse
from django.conf import settings
from django import forms
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import time
import re

from .forms import QueryForm
from .utils import doarchive, CHOICES, get_assistant, mathfix, messages_to_pdf
from .models import create_or_retrieve_thread, QUser, get_current_model, ModeChoice
from django_ragamuffin.models import Assistant, Thread, Assistant, Message
logger = logging.getLogger(__name__)


class AssistantEditForm(forms.ModelForm):

    actual_instructions = forms.CharField(disabled=True, required=False, widget=forms.Textarea(attrs={'disabled': 'disabled'}),)
    directory_name = forms.CharField(required=False, help_text=mark_safe('<div class="instructions"> Change name of the directory </div> ') )
    

    def __init__(self, *args, **kwargs):
        self.custom_data = kwargs.pop("custom_data", {})
        self.local_files = kwargs.pop("local_files", {})
        super().__init__(*args, **kwargs)
        instance = self.instance
        # Set initial value for the readonly field
        #self.fields['actual_instructions'].initial = instance.get_instructions() + ' '.join( DEFAULT_INSTRUCTIONS.split() )  if self.instance.pk else "N/A"
        if self.instance.pk :
            try :
                instructions = ' '.join( instance.get_instructions().split() );
            except :
                instructions = ''
            directory_name = instance.name.split('.')[-1];
        self.fields['directory_name'].initial = instance.name.split('.')[-1];
        self.fields['actual_instructions'].initial = instructions if self.instance.pk else "N/A"
        self.fields['instructions'].label = 'Additional instructions'




    class Meta:
        model = Assistant
        fields = ['mode_choice','instructions','actual_instructions', 'temperature','directory_name']
        help_texts = {
            'directory_name' : "Only the last directory can be renmamed; all children will be renamed",
            'temperature': f"<p/>Default temperature = {settings.DEFAULT_TEMPERATURE}",
            'instructions' : f"Leave or make blank to inherit default; <br> Start the field with 'append: XXX...' to append 'XXX...' to default; <br>Any other non-blank string completely replaces the default instructions.'<br> The entire instructions used by the assistant is shown below <br> It is the result of merging or replacing the mode based instructions with additional instructions.",
            'actual_instructions' : 'This is the final instructions to the assistant which results from merging the mode based instructions with Additional Instructions'
        }

#def delete_file_view(request,pk):
#    if request.method == 'POST' and request.FILES.get('myfile'):
#        files = request.FILES.getlist('myfile')
#        for f in files :
#            filename = f.name 
#            assistant =  Assistant.objects.get(pk=pk)
#            file_url = assistant.delete_file( filename, f)
#            r = render(request, 'django_ragamuffin/upload.html', {'file_url': file_url})
#        return redirect(f"/django_ragamuffin/assistant/{pk}/edit/")
#
#    return render(request, 'django_ragamuffin/upload.html')


def upload_file_view(request,pk):
    if request.method == 'POST' and request.FILES.get('myfile'):
        files = request.FILES.getlist('myfile')
        for f in files :
            filename = f.name 
            assistant =  Assistant.objects.get(pk=pk)
            file_url = assistant.add_file( filename, f)
            r = render(request, 'django_ragamuffin/upload.html', {'file_url': file_url})
        return redirect(f"/django_ragamuffin/assistant/{pk}/edit/")

    return render(request, 'django_ragamuffin/upload.html')

def old_upload_file_view(request,pk):
    if request.method == 'POST' and request.FILES.get('myfile'):
        uploaded_file = request.FILES['myfile']
        filename = uploaded_file.name 
        assistant =  Assistant.objects.get(pk=pk)
        file_url = assistant.add_file( filename, uploaded_file)
        r = render(request, 'django_ragamuffin/upload.html', {'file_url': file_url})
        return redirect(f"/assistant/{pk}/edit/")

    return render(request, 'django_ragamuffin/upload.html')


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
    vss = assistant.get_vector_stores().all();
    for vs in vss:
        vs.delete();
    parent = assistant.parent();
    referer = request.META.get('HTTP_REFERER', '/')
    assistant.delete();
    if parent :
        path = '/query/' + parent.path();
    else :
        path = '/'
    return redirect( path)
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
        #print(f"OLD_TAIL = {old_tail} NEW_TAIL={new_tail}")
        if not old_tail == new_tail :
            def rename_assistants( assistant,  new_tail ):
                old_name = assistant.name;
                new = ( assistant.name.split('.')[:-1]  )
                if not new_tail  == None :
                    new.append(new_tail)
                    new_name = '.'.join(new)
                else :
                    new_name = old_name
                pattern = r'^%s\..+$' % old_name
                tree = Assistant.objects.filter(name__regex=pattern).all()
                p = r'^%s' % old_name 
                for a in tree :
                    n = re.sub( p , new_name, a.name)
                    a.name = n
                    a.save(update_fields=['name']);
                    if a.vector_stores.all():
                        vs = a.vector_stores.all()[0];
                        vs.name = n;
                        vs.save();
                n = re.sub( p, new_name, assistant.name)
                assistant.name = new_name
                a = assistant;
                a.save(update_fields=['name']);
                vs = a.vector_stores.all()[0];
                vs.name = n;
                vs.save();
                pattern = r'^%s(\..*$|$)' % old_name
                tree = Thread.objects.filter(name__regex=pattern).all()
                p = r'^%s' % old_name 
                for a in tree :
                    n = re.sub( p , new_name, a.name)
                    a.name = n
                    a.save(update_fields=['name']);
            rename_assistants( assistant, new_tail )           
            #threads = Thread.objects.filter(name=old_name)
            #if threads :
            #    for thread in threads :
            #        n = re.sub( p, new_name, thread.name)
            #        print(f"FINALLY {thread.name} ->  {n}")
            #        thread.name = new_name
            #        #thread.save(update_fields=['name'])


        
        logger.info(f"POST =  {request.POST}")
        post = request.POST
        if 'instructions' in post :
            assistant.instructions = post.getlist('instructions')[0]
            assistant.save(update_fields=['instructions'])
        if 'mode_choice' in post :
            pklist =  post.getlist('mode_choice') 
            logger.info(f"MODE_CHOICE = {pklist}")
            if len( pklist[0] ) > 0 :
                pk  = int( pklist[0] )
                logger.info(f"PK = {pk}")
                assistant.mode_choice_id = pk
                assistant.save(update_fields=['mode_choice'])
            else :
                assistant.mode_choice = None
            assistant.save(update_fields=['mode_choice'] )
        else :
            assistant.mode_choice = None
            assistant.save(update_fields=['mode_choice'] )
        if 'temperature' in post :
            temperature = post.getlist('temperature')
            logger.info(f"TEMPERATUR OBTAINED = {temperature}")
            if temperature == [] :
                temperature = settings.DEFAULT_TEMPERATURE
            else :
                temperature = temperature[0]
            assistant.temperature = temperature
        if not assistant.temperature :
            assistant.temperature = settings.DEFAULT_TEMPERATURE

        assistant.save()
        #form = AssistantEditForm(request.POST, instance=assistant )
        #if form.is_valid():
        #    form.save()
        return redirect('edit_assistant', pk=assistant.pk)  # or another success URL
    else:
        #print(f"ASSISTANT FILES = {assistant.files()}")
        form = AssistantEditForm(instance=assistant, custom_data=assistant.files(), local_files=assistant.local_files()  )
        if form.is_valid() :
            form.save()
            return redirect('edit_assistant', pk=assistant.pk)  # or another success URL
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
    #name = ( '.'.join( segments ) ).rstrip('.')
    choice = 0;
    index = int( request.POST.getlist('newmessage_index')[0] )
    #print(f"INDEX = {index}")
    #print(f"POST LIST THREAD = {request.POST.getlist('thread')}")
    #post_thread =  re.sub(r'\.','_',request.POST.getlist('thread')[0])
    #thread_name = ( '.'.join( post_thread.split('/')[3:] ) ).rstrip('.');
    #user , _ = QUser.objects.get_or_create(username=request.user.username)
    #print(f"USER = {user} {user.username}")
    #print(f"THREAD_NAME = {thread_name}")
    #threads = Thread.objects.filter(name=thread_name,user=user).all()
    #print(f"THREADS = {threads}")
    #thread = threads[0]
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
    try :
        message = Message.objects.get(pk=index)
        message.choice = choice;
        message.comment = comment;
        message.save(update_fields=['comment','choice'] );
        #if len( thread.messages) > 0 :
        #    try :
        #        thread.messages[index].update( {'comment': comment , 'choice' : choice })
        #        msg = thread.messages[index];
        #        thread.save();
        #        doarchive(thread, msg )
        #    except Exception as err :
        #        print(f"ERROR1 {str(err)}")
        return JsonResponse({"success": True,'index' : index ,'comment' : comment , 'choice' :choice  })
    except Exception as err :
        return JsonResponse({"success": False,'index' : index ,'comment' : 'error', 'choice' :choice  })


FILENAME = "../README.md"
@csrf_exempt
@login_required
def query_view(request,subpath):
    subpath_ = re.sub( r"\.","_",subpath )
    segments = subpath_.split('/')
    subdomain = request.META["HTTP_HOST"].split(".")[0].split(":")
    if subdomain  :
       subdomain = subdomain[0]
    else :
       subdomain = ''
    #print(f"SUBDOMAIN = {subdomain}")
    last_messages = settings.LAST_MESSAGES;
    max_num_results = settings.MAX_NUM_RESULTS;
    name = ( '.'.join( segments ) ).rstrip('.')
    choices = CHOICES
    choice = 0;
    response = None
    user,  created  = QUser.objects.get_or_create(username=request.user.username,subdomain=subdomain)
    if created :
        user.is_staff = request.user.is_staff
        user.save();
    quser, _  = QUser.objects.get_or_create(username=request.user.username,subdomain=subdomain)
    assistant = get_assistant(name, quser)
    if not assistant :
        return HttpResponseForbidden(f"No assistant <b>{name} </b> exists.")
    model = get_current_model( quser)
    thread = create_or_retrieve_thread( assistant, name , quser )
    data = request.POST;
    keeps = request.POST.getlist('keep',choices.keys() )
    if 'delete' in request.POST.getlist('action') :
        deletes = request.POST.getlist('entry')
        #print(f"DELETES = {deletes}")
        dmessages = Message.objects.filter(pk__in=deletes);
        #print(f"DMESSAGES = {dmessages}")
        dmessages.delete();
        response = redirect(f"/django_ragamuffin/query/{assistant.name}/")
    elif 'filter' in request.POST.getlist('action' ) :
        response = redirect(f"/django_ragamuffin/query/{assistant.name}/")
    d = {'status' : 'pending' , 'result' : 'RESULT' }
    if  user.is_staff : 
        base_msgs = list( Message.objects.filter(thread__name=name) ) or []
    else :
        base_msgs = list( thread.thread_messages.all() ) or []
    uname = thread.user.username if getattr(thread, "user", None) else ""
    messages = []
    for _mm in base_msgs:
        m =  model_to_dict(_mm , fields=[f.name for f in _mm._meta.fields])
        #if isinstance(_m, dict):
        #    m = dict(_m)
        m["username"] = _mm.username()
        m["pk"] = _mm.pk
        m["date"] = str( _mm.date)
        if m['choice'] == None :
            m['choice'] = 0;
        messages.append(m)


    if 'print' in request.POST.getlist('action') :
        prints = request.POST.getlist('entry')
        if prints :
            response = messages_to_pdf( assistant , messages , prints )
            return response
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
                if query.strip()  == message['query'].strip() :
                    txt = "*You already asked that!*<p/>" + message['response']
                    comment = message.get('comment','')
                    choice = message.get('choice','0')
                    mindex = mindex - 1;
                    ntokens = message.get('ntokens')
                    date = message.get('date',None)
                    break
            try:
                if txt is None:
                    msg = thread.run_query(query=query, last_messages=last_messages, max_num_results=max_num_results)
                    txt = msg['assistant']
                    summary = msg.get('summary','NONE3')
                    ntokens = msg['ntokens']
            except (KeyError, AttributeError, ValueError) as e:
                txt = f"ERROR2 {type(e).__name__}: {str(e)}"
            except Exception  as e:
                txt = f"ERROR3 {type(e).__name__}: {str(e)}"
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
    keeps =  [ int(i) for i in keeps ]
    resolved_choices = [(i, choices[i]) for i in keeps]
    f_ = [ {  'user' : ( item['query'] ).strip() ,  'pk' : item['pk'] ,
       'response' : mark_safe( mathfix(item['response'] ) ).strip(),
       'username' : item.get('username',''),
       'ntokens' : item['ntokens'],
       'comment' : item.get('comment','').strip() ,
       'choice' : item.get('choice',0),
       'model' : item.get('model', model) ,  
       'max_num_results' : item.get('max_num_results' , max_num_results ),
       'last_messages' : item.get('last_messages' , last_messages)  ,
       'summary' : item.get('summary','None'),
       'response_id' : item.get('response_id','None'),
       'previous_response_id' : item.get('previous_response_id',None),
       'date' : item.get('date',None),
       'time_spent' : item.get('time_spent', time_spent) }  for index, item in enumerate( messages )  ] 
    # Sort by 'date' (descending). Items with missing dates come first.
    try:
        f_.sort(key=lambda x: x.get('date') or "", reverse=True)
    except Exception:
        pass
    ff = [ item for item in f_ if item.get('choice',0)  in keeps ]
    if ff:
        summary = ff[-1].get('summary','None')
    else :
        summary = ''
    try :
        if  len( query.strip() ) == 0 :
            summary = ''
    except :
        summary = ''
    f = [ { **item, 'index' : index}   for index,item in enumerate(ff)]
    children = assistant.children();
    parent = assistant.parent();
    date =  timezone.localtime(timezone.now()).strftime("%Y-%m-%d:%H:%M")
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
        'choice' : 0,
        'ntokens' : ntokens,
        'summary' : summary,
        'keeps' : keeps,
        'date' : date,
        'model' : model ,
        'resolved_choices' : resolved_choices,
        'assistant_pk' : assistant.pk ,
        'max_num_results' : max_num_results,
        'last_messages' : last_messages ,
        'time_spent' : time_spent  })
    response.set_cookie('busy' , 'false')
    return response
