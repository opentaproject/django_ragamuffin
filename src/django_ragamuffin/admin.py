from django.contrib import admin
from django.conf import settings
from django import forms
from .models import OpenAIFile  , VectorStore , Assistant, Thread, DEFAULT_INSTRUCTIONS, RemoteVectorStore


@admin.register(RemoteVectorStore)
class RemoteVectorStoreAdmin(admin.ModelAdmin):
    list_display = ('pk', 'checksum' ,'list_file_names', 'vector_store_id', 'vector_stores_pks', )
    list_display = ('pk', 'vector_store_id','checksum','list_file_names', 'vector_stores_pks', )

    def list_file_names(self, obj):
        return ", ".join(obj.file_names())

    list_file_names.short_description = "File Names"





@admin.register(OpenAIFile)
class OpenAIFileAdmin(admin.ModelAdmin):
    list_display = ('pk', 'name', 'file_ids', 'checksum', 'date')
    readonly_fields = ('checksum','name','path','file_ids')

@admin.register(VectorStore)
class VectorStoreAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'vsid', 'checksum', 'list_file_ids')  # Add your custom method here
    readonly_fields = ('checksum','vsid')

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ('name',)
        return self.readonly_fields  # creating a new object

    def list_file_ids(self, obj):
        return ", ".join(str(f.name) for f in obj.files.all())

    list_file_ids.short_description = "File Names"
    
class MyAssistantForm(forms.ModelForm):

    actual_instructions = forms.CharField(disabled=True, required=False, widget=forms.Textarea(attrs={'disabled': 'disabled'}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        # Set initial value for the readonly field
        #self.fields['actual_instructions'].initial = instance.get_instructions() + ' '.join( DEFAULT_INSTRUCTIONS.split() )  if self.instance.pk else "N/A"
        if self.instance.pk :
            instructions = ' '.join( instance.get_instructions().split() );
        self.fields['actual_instructions'].initial = instructions if self.instance.pk else "N/A"

    class Meta:
        model = Assistant
        fields = ['name','model','instructions','vector_stores','assistant_id','json_field','temperature','actual_instructions' ,]
        help_texts = {
            'temperature': f"Default temperature = {settings.DEFAULT_TEMPERATURE}",
            'instructions' : f"Leave blank for default; start with 'append: XXX...' to append 'XXX...' to default; Any other non-blank string completely replaces the default instructions.'"
        }


@admin.register(Assistant)
class AssistantAdmin(admin.ModelAdmin):
    form = MyAssistantForm 
    list_display = ('id', 'name','model', 'assistant_id', 'file_names','file_pks', 'list_vector_store_ids')  # Add your custom method here

    def list_vector_store_ids(self, obj):
        return ", ".join(str(f.name ) for f in obj.vector_stores.all())

    list_vector_store_ids.short_description = "VectorStore names"
    

class MyThreadForm(forms.ModelForm):
    class Meta:
        model = Assistant
        fields = '__all__'
        help_texts = {
            'max_tokens': f"Not implmented; it is unavailable as of openai 1.73.0 "
        }

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    form = MyThreadForm;
    list_display = ('id', 'name', 'user', 'thread_id', 'assistant')  # Add your custom method here

