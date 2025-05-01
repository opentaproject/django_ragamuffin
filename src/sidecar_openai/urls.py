from django.urls import path
from . import views

urlpatterns = [
        path('query/<str:name>/', views.query_view, name='query'),
]
