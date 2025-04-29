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
import markdown
from django.utils.safestring import mark_safe

import openai 
from openai import OpenAI


FILENAME = "../README.md"
def query_view(request):
    response = None
    user = request.user
    src = FILENAME
    t1 = upload_or_retrieve_openai_file( src )
    vs = create_or_retrieve_vector_store( src , [t1] )
    instructions = 'Answer only questions about the enclosed document. Do not offer helpful answers to questions that do not refer to the document. Be concise. If the question is irrelevant, answer with "The question look interesting to you, but that is not what we are talking about."'
    assistant = create_or_retrieve_assistant( src, vs )
    assistant.instructions = instructions
    assistant.save()
    thread = create_or_retrieve_thread( assistant, src, user )
    print(f"THREAD = {thread}")

    print(f"VS = {vs}")
    if request.method == 'POST':
        form = QueryForm(request.POST)
        if form.is_valid():
            assistant_id = assistant.assistant_id # replace with your actual assistant ID
            ass = openai.beta.assistants.retrieve(assistant_id)
            print("Assistant Name:", ass.name)
            print("Instructions:\n", ass.instructions)
            query = form.cleaned_data['query']
            txt = thread.run_query(  query=query )
            html = mark_safe(markdown.markdown(txt)) 
            # simple response logic
            response = f"{query} {html} "
    else:
        form = QueryForm()
    return render(request, 'sidecar_openai/query_form.html', {'form': form, 'response': response})
