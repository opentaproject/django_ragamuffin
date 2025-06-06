from django import template

register = template.Library()

@register.filter
def replace(value, args):
    old, new = args.split(',')
    res = value.replace(old, new)
    print(f"RES = {res}")
    return res
