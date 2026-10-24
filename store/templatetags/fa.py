from django import template

register = template.Library()

_DIGIT_MAP = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")


@register.filter(is_safe=True)
def fa_num(value):
    """قیمت با جداکنندهٔ هزارگان و ارقام فارسی؛ مثل ۵۷۰,۰۰۰."""
    try:
        text = f"{int(value):,}"
    except (TypeError, ValueError):
        return value
    return text.translate(_DIGIT_MAP)
