"""میان‌افزار محدودسازی نرخ درخواست برای مسیرهای حساس (ضد brute-force و سوءاستفاده).

برای هر IP و مسیر، سقف درخواست در پنجرهٔ زمانی از تنظیمات RATELIMIT_RULES خوانده می‌شود.
وقتی سقف پر شود پاسخ 429 با پیام فارسی برمی‌گردد.
"""
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.translation import gettext as _


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.rules = getattr(settings, "RATELIMIT_RULES", {})

    def __call__(self, request):
        path = request.path.rstrip("/") or "/"
        rule = self.rules.get(path + "/") or self.rules.get(path)
        if rule:
            limit, window = rule
            key = f"rl:{path}:{client_ip(request)}"
            bucket = cache.get(key)
            now = time.monotonic()
            if bucket is None:
                bucket = [now, 0]
            if now - bucket[0] > window:
                bucket = [now, 0]
            bucket[1] += 1
            cache.set(key, bucket, window)
            if bucket[1] > limit:
                response = HttpResponse(
                    "درخواست‌های شما بیش از حد مجاز است؛ لطفاً چند دقیقه صبر کنید.",
                    status=429,
                    content_type="text/plain; charset=utf-8",
                )
                response["Retry-After"] = str(window)
                return response
        return self.get_response(request)
