from django.shortcuts import render
from .forms import QueryForm

def query_view(request):
    response = None
    if request.method == 'POST':
        form = QueryForm(request.POST)
        if form.is_valid():
            query_text = form.cleaned_data['query']
            # simple response logic
            response = f"Received your query: {query_text}"
    else:
        form = QueryForm()
    return render(request, 'sidecar_openai/query_form.html', {'form': form, 'response': response})
