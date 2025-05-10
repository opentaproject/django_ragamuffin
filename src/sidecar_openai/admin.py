from django.contrib import admin
from django.conf import settings
from django import forms
from .models import OpenAIFile  , VectorStore , Assistant, Thread

@admin.register(OpenAIFile)
class OpenAIFileAdmin(admin.ModelAdmin):
    list_display = ('pk', 'name', 'file_ids', 'checksum', 'date')
    readonly_fields = ('checksum','name','path','file_ids')

@admin.register(VectorStore)
class VectorStoreAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'vector_store_id', 'checksum', 'list_file_ids')  # Add your custom method here
    readonly_fields = ('checksum','vector_store_id')

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ('name',)
        return self.readonly_fields  # creating a new object

    def list_file_ids(self, obj):
        return ", ".join(str(f.name) for f in obj.files.all())

    list_file_ids.short_description = "File Names"
    
class MyAssistantForm(forms.ModelForm):
    class Meta:
        model = Assistant
        fields = '__all__'
        help_texts = {
            'temperature': f"Default temperature = {settings.DEFAULT_TEMPERATURE}"
        }


@admin.register(Assistant)
class AssistantAdmin(admin.ModelAdmin):
    form = MyAssistantForm 
    list_display = ('id', 'name', 'assistant_id', 'file_names','file_pks', 'list_vector_store_ids')  # Add your custom method here

    def list_vector_store_ids(self, obj):
        return ", ".join(str(f.name ) for f in obj.vector_stores.all())

    list_vector_store_ids.short_description = "VectorStore names"
    

class MyThreadForm(forms.ModelForm):
    class Meta:
        model = Assistant
        fields = '__all__'
        help_texts = {
            'max_tokens': f"default max_tokens = {settings.MAX_TOKENS}"
        }

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    form = MyThreadForm;
    list_display = ('id', 'name', 'user', 'thread_id', 'assistant')  # Add your custom method here

