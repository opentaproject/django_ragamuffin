from django.urls import path, re_path
from . import views,admin
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
        #path(r'^feedback/(?P<subpath>.*)$', views.feedback_view, name='feedback'),
        #path(r'^query/(?P<subpath>.+)$', views.query_view, name='query'),
        #path(r'^assistant/<int:pk>/edit/', views.edit_assistant, name='edit_assistant'),
        #path(r'^upload/<int:pk>/', views.upload_file_view, name='upload'),
        #path(r'^assistant/<int:pk>/delete/', views.delete_assistant, name='delete_assistant'),
        re_path(r'^feedback/(?P<subpath>.*)$', views.feedback_view, name='feedback'),
        re_path(r'^query/(?P<subpath>.+)$', views.query_view, name='query'),
        re_path(r'^assistant/(?P<pk>\d+)/edit/$', views.edit_assistant, name='edit_assistant'),
        re_path(r'^upload/(?P<pk>\d+)/$', views.upload_file_view, name='upload'),
        re_path(r'^assistant/(?P<pk>\d+)/delete/$', views.delete_assistant, name='delete_assistant'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
