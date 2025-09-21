from django import template
from django.utils.dateparse import parse_datetime
from django.utils.timesince import timesince
from django.utils.timezone import is_naive, make_aware, get_current_timezone


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

@register.filter
def humanize_datetime(value):
    """
    Convert a datetime string like '2025-09-21:13:07' to 'x minutes ago'.
    """
    if not value:
        return ""
    try :
        value = value.replace(":", " ", 1)  # "2025-09-21 13:07"
        dt = parse_datetime(value)
        if not dt:
            return value  # fallback: return raw string
        if is_naive(dt):
            dt = make_aware(dt, get_current_timezone())
        return f"{timesince(dt)} ago"
    except Exception as err :
        return str( value )
