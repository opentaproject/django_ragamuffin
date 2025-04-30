from django import forms

class QueryForm(forms.Form):
    query = forms.CharField(
        label='',
        widget=forms.Textarea(attrs={
            'rows': 2,
            'cols' : 60,
            'placeholder': 'Enter your query...'
        })
    )
