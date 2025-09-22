from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.shortcuts import render
from django_ragamuffin.models import Thread, Message

def login_view(request):
    if request.user.is_authenticated :
        threads = Thread.objects.all();
        print(f"THREADS = {threads}")
        for thread in threads.all() :
            print(f"THREAD = {thread}")
            previous = None
            for msg in thread.messages :
                print(f"MSG = {msg}")
                query = msg['user'];
                response = msg['assistant'];
                model = msg['model']
                ntokens = msg['ntokens']
                time_spent = msg['time_spent']
                response_id = msg.get('response_id',None)
                last_messages = msg['last_messages']
                summary = msg.get('summary','')
                comment = msg.get('comment','')
                choice = msg.get('choice',0)
                instructions = msg.get('instructions','no instructions')
                previous_response_id = msg.get('previous_response_id',None)
                mhash = msg.get('hash')
                print(f"QUERY = {query}")
                print(f"RESPONSE = {response}")
                print(f"MODEL = {model}")
                print(f"ntokens = {ntokens}")
                print(f"time_spent = {time_spent}")
                print(f"response_id = {response_id}")
                print(f"LAST_MESSAGES = {last_messages}")
                print(f"SUMMARY = {summary}")
                print(f"comment = {comment}")
                print(f"choice = {choice}")
                print(f"instructions = {instructions}")
                print(f"previous_response_id ={previous_response_id}")
                print(f"MHASH = {mhash}")
                message , created = Message.objects.get_or_create(
                    query=msg.get('user',''),
                    response=response,
                    choice=choice,
                    summary=summary,
                    previous=previous,
                    ntokens=ntokens,
                    model=model,
                    time_spent=time_spent,
                    last_messages=last_messages,
                    response_id=response_id,
                    instructions=instructions,
                    previous_response_id=previous_response_id,
                    mhash=mhash)


                message.save();
                message.thread = thread;
                message.previous = previous
                message.save(update_fields=['thread','previous'])
                previous = message

        return HttpResponse("You are already logged in ")
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username'),
            password=request.POST.get('password')
        )
        if user:
            login(request, user)
            return HttpResponse("Logged in")
        else:
            return HttpResponse("Invalid credentials")
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return HttpResponse("Logged out")
