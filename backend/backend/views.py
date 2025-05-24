from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.shortcuts import render

def login_view(request):
    if request.user.is_authenticated :
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
