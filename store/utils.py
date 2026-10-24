import re


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone(value):
    """Normalize Persian numerals and common visual separators for lookups."""
    value = str(value or "").translate(_PERSIAN_DIGITS).strip()
    return re.sub(r"[\s\-()]+", "", value)
