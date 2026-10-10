# django-ragamuffin

`django-ragamuffin` adds OpenAI-backed document retrieval and conversational
querying to Django applications. It supports assistant-specific instructions,
uploaded document collections, multimodal query context, reasoning models, and
optional Mathpix PDF extraction.

## Requirements

- Python 3.11 or newer
- Django 5.2.17 or newer, below Django 6.1
- OpenAI Python SDK 3.6.0 or newer
- PostgreSQL

## Installation

```bash
pip install django-ragamuffin
```

Add `grappelli` before Django's admin application, then add Ragamuffin and its
database router to your Django settings:

```python
INSTALLED_APPS = [
    "grappelli",
    "django.contrib.admin",
    # The rest of the Django applications...
    "django_ragamuffin",
]

DATABASE_ROUTERS = [
    "django_ragamuffin.db_routers.RagamuffinRouter",
]

DJANGO_RAGAMUFFIN_DB = "django_ragamuffin"
OPENAI_UPLOAD_STORAGE = "/subdomain-data/query"
USE_CHATGPT = True

AI_MODEL = "gpt-6.1-sol"
AI_MODELS = {
    "staff": AI_MODEL,
    "default": AI_MODEL,
}
EFFORT = "medium"
```

Configure the OpenAI API key in the process environment:

```bash
export OPENAI_API_KEY="..."
```

The package includes its Django migrations. Apply them only through the
deployment's approved database-migration procedure.

Add the application URLs:

```python
from django.urls import include, path

urlpatterns = [
    path("grappelli/", include("grappelli.urls")),
    path("django_ragamuffin/", include("django_ragamuffin.urls")),
]
```

## Optional Mathpix extraction

Set `USE_MATHPIX=True` and provide `APP_ID` and `APP_KEY` to enable Mathpix PDF
conversion. Without those credentials, Mathpix integration remains disabled.

## License

MIT
