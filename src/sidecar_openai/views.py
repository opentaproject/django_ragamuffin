from django.shortcuts import render
from sidecar_openai.models import OpenAIFile, VectorStore, Assistant,  Thread, hashed_upload_to, upload_or_retrieve_openai_file
from sidecar_openai.models import create_or_retrieve_vector_store, create_or_retrieve_assistant, create_or_retrieve_thread
from .forms import QueryForm
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
import shutil
import os




FILENAME = "../README.md"
def query_view(request):
    response = None
    user = request.user
    src = FILENAME
    t1 = upload_or_retrieve_openai_file( src )
    vs = create_or_retrieve_vector_store( src , [t1] )
    assistant = create_or_retrieve_assistant( src, vs )
    thread = create_or_retrieve_thread( assistant, src, user )
    print(f"THREAD = {thread}")

    print(f"VS = {vs}")
    if request.method == 'POST':
        form = QueryForm(request.POST)
        if form.is_valid():
            query_text = form.cleaned_data['query']
            # simple response logic
            response = f"Received your query: {query_text}"
    else:
        form = QueryForm()
    return render(request, 'sidecar_openai/query_form.html', {'form': form, 'response': response})
