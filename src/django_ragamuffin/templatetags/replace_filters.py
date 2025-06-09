from django import template

register = template.Library()

@register.filter
def replace(value, args):
    args = [ '.,/','_,.']
    print(f"VALUE = {value} args={args}")
    for a in args :
        old, new = a.split(',')
        value = value.replace(old, new)
    print(f"VALUE = {value}")
    return value
    
