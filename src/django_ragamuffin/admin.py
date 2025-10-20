from django.contrib import admin
from django.db.models import Count, OuterRef, Subquery
from django.conf import settings
from django import forms
from .models import OpenAIFile  , VectorStore , Assistant, Thread, DEFAULT_INSTRUCTIONS, RemoteVectorStore, QUser, Mode, ModeChoice, Message


@admin.register(RemoteVectorStore)
class RemoteVectorStoreAdmin(admin.ModelAdmin):
    list_display = ('pk', 'checksum' ,'list_file_names', 'vector_store_id', 'vector_stores_pks', )
    list_display = ('pk', 'vector_store_id','checksum','list_file_names', 'vector_stores_pks', )

    def list_file_names(self, obj):
        return ", ".join(obj.file_names())

    list_file_names.short_description = "File Names"



@admin.register(QUser)
class QUserAdmin(admin.ModelAdmin):

    def messages(self,obj):
        return len( obj.messages() )

    list_display = ('pk', 'username', 'is_staff','messages')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # annotate each user with a count of related messages
        return qs.annotate(message_count=Count('thread__thread_messages'))

    @admin.display(ordering='message_count')
    def messages(self, obj):
        return obj.message_count



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
    
class AssistantForm(forms.ModelForm):

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
        fields = ['name','mode_choice','instructions','vector_stores','assistant_id','json_field','temperature','actual_instructions' ,]
        help_texts = {
            'temperature': f"Default temperature = {settings.DEFAULT_TEMPERATURE}",
            'instructions' : f"Leave blank for default; start with 'append: XXX...' to append 'XXX...' to default; Any other non-blank string completely replaces the default instructions.'"
        }


class AssistantSubdomainListFilter(admin.SimpleListFilter):
    title = 'subdomain'
    parameter_name = 'subdomain'

    def lookups(self, request, model_admin):
        subs = (
            Message.objects.exclude(subdomain__isnull=True)
            .exclude(subdomain='')
            .values_list('subdomain', flat=True)
            .distinct()
            .order_by('subdomain')
        )
        return [(s, s) for s in subs]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(threads__thread_messages__subdomain=value).distinct()
        return queryset


@admin.register(Assistant)
class AssistantAdmin(admin.ModelAdmin):
    form = AssistantForm
    list_display = ('id', 'name', 'mode_choice', 'assistant_id', 'subdomain', 'file_names', 'file_pks')
    list_filter = (AssistantSubdomainListFilter,)
    #list_display = ('id', 'name', 'mode_choice', 'assistant_id', 'file_names','file_pks', 'file_ids', 'remote_files','list_vector_store_ids')  # Add your custom method here

    def list_vector_store_ids(self, obj):
        return ", ".join(str(f.name ) for f in obj.vector_stores.all())

    list_vector_store_ids.short_description = "VectorStore names"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        latest_subdomain = Subquery(
            Message.objects
            .filter(thread__assistant=OuterRef('pk'))
            .exclude(subdomain__isnull=True)
            .exclude(subdomain='')
            .order_by('-date')
            .values('subdomain')[:1]
        )
        return qs.annotate(last_subdomain=latest_subdomain)

    def subdomain(self, obj):
        return getattr(obj, 'last_subdomain', '') or ''
    subdomain.short_description = 'Subdomain'
    subdomain.admin_order_field = 'last_subdomain'


class MyThreadForm(forms.ModelForm):
    class Meta:
        model = Thread
        fields = '__all__'

class MyMessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = '__all__'

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    form = MyThreadForm;
    list_display = ('id', 'name', 'user', 'thread_id', 'assistant')  # Add your custom method here

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    form = MyMessageForm
    list_display = ('id',  'thread', 'subdomain')  # Add your custom method here
    list_filter = ('subdomain',)



@admin.register(ModeChoice)
class ModeChoiceAdmin(admin.ModelAdmin):
    list_display = ("label", "key")
    search_fields = ("label", "key")

@admin.register(Mode)
class ModeAdmin(admin.ModelAdmin):
    list_display = ("choice", "short_text")
    search_fields = ("choice__label", "text")
    autocomplete_fields = ("choice",)  # nice if you have many choices

    def short_text(self, obj):
        return (obj.text or "")[:60]
    short_text.short_description = "Text"
