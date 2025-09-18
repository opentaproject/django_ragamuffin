from django import template

register = template.Library()

@register.filter
def replace(value, args):
    args = [ '.,/','_,.']
    for a in args :
        old, new = a.split(',')
        value = value.replace(old, new)
    return value
    
@register.filter
def username_from_email(value):
    """Return the part of the email before the '@'."""
    return value.split('@')[0] if value else ''
