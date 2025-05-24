from django.urls import path, re_path
from . import views

urlpatterns = [
        re_path(r'^feedback/(?P<subpath>.*)$', views.feedback_view, name='feedback'),
        re_path(r'^query/(?P<subpath>.+)$', views.query_view, name='query'),
]
