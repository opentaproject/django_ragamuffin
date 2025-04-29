from django import forms

class QueryForm(forms.Form):
    query = forms.CharField(
        label='',
        widget=forms.Textarea(attrs={
            'rows': 2,
            'style': 'width: 300;',
            'placeholder': 'Enter your query...'
        })
    )
