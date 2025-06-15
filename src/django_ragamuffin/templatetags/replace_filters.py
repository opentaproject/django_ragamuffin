from django import template

register = template.Library()

@register.filter
def replace(value, args):
    args = [ '.,/','_,.']
    for a in args :
        old, new = a.split(',')
        value = value.replace(old, new)
    return value
    
