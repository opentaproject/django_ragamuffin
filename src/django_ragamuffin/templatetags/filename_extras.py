import os
from django import template

register = template.Library()

@register.filter
def strip_extension(filename):
    return os.path.splitext(filename)[0]
