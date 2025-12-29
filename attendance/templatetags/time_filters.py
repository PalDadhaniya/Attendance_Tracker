from django import template

register = template.Library()

@register.filter
def format_duration(duration):
    """
    Converts timedelta to: '176 hrs 30 mins'
    """
    if not duration:
        return "0 hrs 0 mins"

    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    return f"{hours} hrs {minutes} mins"