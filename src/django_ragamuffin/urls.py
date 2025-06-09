from django.urls import path, re_path
from . import views
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
        re_path(r'^feedback/(?P<subpath>.*)$', views.feedback_view, name='feedback'),
        re_path(r'^query/(?P<subpath>.+)$', views.query_view, name='query'),
        path('assistant/<int:pk>/edit/', views.edit_assistant, name='edit_assistant'),
        path('upload/<int:pk>/', views.upload_file_view, name='upload'),
        path('assistant/<int:pk>/delete/', views.delete_assistant, name='delete_assistant'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
