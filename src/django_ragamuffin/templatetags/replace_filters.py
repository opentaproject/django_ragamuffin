from django import template
from django.utils.dateparse import parse_datetime
from django.utils.timesince import timesince, timeuntil
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware, get_current_timezone
from django.utils.html import strip_tags
from django.utils import timezone
import re


register = template.Library()

@register.filter
def replace(value, args):
    args = [ '.,/','_,.']
    for a in args :
        old, new = a.split(',')
        value = value.replace(old, new)
    return value

@register.filter(name="clean_snippet")
def clean_snippet(value, length=30):
    if value is None:
        return ""
    s = str(value)
    s = strip_tags(s)

    # 1) strip leading blanks
    s = s.lstrip()

    # 2) replace any newline variation with a single space
    s = re.sub(r"\r\n|\r|\n", " ", s)

    # (optional) collapse multiple spaces
    s = re.sub(r"\s{2,}", " ", s)

    # 3) truncate to desired length (default 30)
    try:
        n = int(length)
    except (TypeError, ValueError):
        n = 30

    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"
    
@register.filter
def username_from_email(value):
    """Return the part of the email before the '@'."""
    return value.split('@')[0] if value else ''

@register.filter
def old_humanize_datetime(value):
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
        d = f"{timesince(dt)} ago"
        d = d.replace('hours','h,')

        return d

    except Exception as err :
        return str( value )

@register.filter
def humanize_datetime(value):
    """
    Humanize an ISO-like datetime string into 'x minutes ago' or 'in x minutes'.
    Example input: '2025-09-22 20:04:13.667166+00:00'
    """
    if not value:
        return ""

    # Parse the string into datetime
    dt = parse_datetime(str(value))
    if not dt:
        return value  # fallback if parsing fails

    # Ensure timezone-aware in current tz
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    now = timezone.localtime(timezone.now())

    if dt <= now:
        d = f"{timesince(dt, now)} ago"
    else:
        d = f"in {timeuntil(dt, now)}"
    d = d.replace('hours','h')
    d = d.replace('minutes','m')
    d = d.replace(',','')
    d = '+' + d.replace(' ago','')
    return d

@register.filter
def localtime_no_microseconds(value):
    """
    Humanize an ISO-like datetime string into 'x minutes ago' or 'in x minutes'.
    Example input: '2025-09-22 20:04:13.667166+00:00'
    """
    if not value:
        return ""

    # Parse the string into datetime
    dt = parse_datetime(str(value))
    if not dt:
        return value  # fallback if parsing fails

    # Ensure timezone-aware in current tz
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.strftime("%Y-%m-%d:%H:%M:%S")

    #if dt <= now:
    #    return f"{timesince(dt, now)} ago"
    #else:
    #    return f"in {timeuntil(dt, now)}"

