from django import forms

class QueryForm(forms.Form):
    query = forms.CharField(label='Your Query', max_length=200)
