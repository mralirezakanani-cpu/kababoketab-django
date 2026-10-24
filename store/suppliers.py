"""کانکتورهای واقعی تأمین‌کننده‌ها — داده‌های قیمت و موجودی از منابع رسمی.

هر تابع ردیف‌های استاندارد زیر را برمی‌گرداند:
  isbn, regular_price (تومان), sale_price (تومان یا None), stock,
  external_id, url, title, publisher, author, translator, pages,
  publication_year, cover_type, format_size, weight_grams, cover_url
منابع:
  * ققنوس (qoqnoosp.com) — فایل ZIP/XLSX رسمی موجودی
  * پخش چشمه (server.cheshmehdis.com/api/v1) — REST API رسمی سایت پخش چشمه
  * کتاب گستر (gbook.ir) — sitemap → صفحات محصول → JSON-LD
"""
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote, urlparse

USER_AGENT = "Mozilla/5.0 (compatible; KababBookSupplierSync/2.0; +kababoketab.ir)"
FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def http_get(url, timeout=30, accept="*/*"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def rial_to_toman(amount):
    """قیمت ریال منابع به تومان (مضرب ۱۰ رند می‌شود)."""
    if amount in (None, ""):
        return None
    amount = int(str(amount).translate(FA_DIGITS).replace(",", "").strip())
    return (amount + 5) // 10 if amount % 10 else amount // 10


def normalize_isbn(value):
    value = str(value or "").translate(FA_DIGITS)
    return re.sub(r"[^0-9Xx]", "", value).upper()


def _int_or(value, default=None):
    try:
        return int(float(str(value).translate(FA_DIGITS).strip() or default if default is not None else str(value).translate(FA_DIGITS).strip()))
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------------
# پخش چشمه — API رسمی جست‌وجوی سایت
# ----------------------------------------------------------------------
CHESHMEHDIS_API = "https://server.cheshmehdis.com/api/v1/search"


def fetch_cheshmehdis(max_pages=None, page_size=200, sleep_seconds=0.4, include_non_books=False):
    """صفحه‌بندی کامل کاتالوگ پخش چشمه با قیمت (ریال) و موجودی واقعی."""
    page = 1
    total_pages = None
    seen = 0
    while True:
        url = (f"{CHESHMEHDIS_API}?page={page}&count={page_size}"
               "&category=%5B%5D&brand=%5B%5D&author=%5B%5D&translator=%5B%5D&book_size=%5B%5D&cover_type=%5B%5D")
        payload = json.loads(http_get(url, timeout=45, accept="application/json").decode("utf-8"))
        if isinstance(payload, str):
            raise ValueError(f"خطای سرور چشمه در صفحهٔ {page}: {payload[:120]}")
        items = payload.get("items") or {}
        data = items.get("data") if isinstance(items, dict) else items
        if total_pages is None:
            total = int(payload.get("total") or 0)
            total_pages = int(payload.get("latest_page") or (total + page_size - 1) // page_size or 1)
        for item in data or []:
            seen += 1
            if not include_non_books and str(item.get("product_type") or "").strip() != "کتاب":
                continue
            isbn = normalize_isbn(item.get("isbn"))
            if not isbn:
                continue
            regular = rial_to_toman(item.get("price"))
            if not regular:
                continue
            special = rial_to_toman(item.get("special_price"))
            if special is not None and special <= 0:
                special = None
            qty = _int_or(item.get("qty"), 0) or 0
            if str(item.get("status") or "") != "1":
                qty = 0
            slug = str(item.get("slug") or "").strip()
            brand = str((item.get("brand_name") or (item.get("get_brand") or {}).get("name") or "")).strip()
            yield {
                "isbn": isbn,
                "regular_price": regular,
                "sale_price": special,
                "stock": max(0, qty),
                "external_id": f"CH-{item.get('main_code') or item.get('id')}",
                "url": f"https://cheshmehdis.com/product/{quote(slug)}/list" if slug else "",
                "title": str(item.get("name") or "").strip(),
                "publisher": brand,
                "author": str(item.get("author") or "").strip(),
                "translator": str(item.get("translator") or "").strip(),
                "pages": _int_or(item.get("page_count")),
                "publication_year": _int_or(item.get("publish_year")),
                "cover_type": str(item.get("cover_type") or "").strip(),
                "format_size": str(item.get("book_size") or "").strip(),
                "weight_grams": _int_or(item.get("weight"), 0) or 0,
                "cover_url": str(item.get("intro_image") or "").strip(),
            }
        if total_pages is None or page >= total_pages:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(sleep_seconds)


# ----------------------------------------------------------------------
# کتاب گستر (gbook.ir) — sitemap → صفحات محصول → JSON-LD
# ----------------------------------------------------------------------
GBOOK_SITEMAP_INDEX = "https://gbook.ir/sitemap.xml"
GBOOK_CHUNK_RE = re.compile(r"<loc>(https://gbook\.ir/sitemap/[^<]*sitemap-catalogs\.xml)</loc>")
GBOOK_PRODUCT_RE = re.compile(r"<loc>(https://gbook\.ir/shop/catalog-[^<]+)</loc>")
LD_JSON_RE = re.compile(r'application/ld\+json[^>]*>(.*?)</script>', re.S)


def gbook_catalog_chunks():
    """فهرست chunkهای sitemap محصولات کتاب گستر (به ترتیب پایدار)."""
    body = http_get(GBOOK_SITEMAP_INDEX, timeout=30).decode("utf-8", "replace")
    chunks = sorted(set(GBOOK_CHUNK_RE.findall(body)))
    return chunks


def gbook_chunk_urls(chunk_url):
    body = http_get(chunk_url, timeout=45).decode("utf-8", "replace")
    return sorted(set(GBOOK_PRODUCT_RE.findall(body)))


def _parse_gbook_page(url, html):
    match = LD_JSON_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None
    if str(data.get("@type") or "") != "Book":
        return None
    isbn = normalize_isbn(data.get("isbn"))
    if not isbn:
        return None
    offers = data.get("offers") or {}
    price = rial_to_toman(offers.get("Price") or offers.get("price"))
    if not price:
        return None
    stock = 0 if ("بدون موجودی" in html or "OutOfStock" in html) else 1
    return {
        "isbn": isbn,
        "regular_price": price,
        "sale_price": None,
        "stock": stock,
        "external_id": f"GB-{re.search(r'catalog-(\d+)', url).group(1) if re.search(r'catalog-(\d+)', url) else ''}",
        "url": url,
        "title": str(data.get("name") or "").strip(),
        "publisher": "",
        "author": "",
        "translator": "",
        "pages": _int_or(data.get("numberOfPages")),
        "publication_year": None,
        "cover_type": "",
        "format_size": "",
        "weight_grams": _int_or(str(data.get("weight") or "").split(" ")[0], 0) or 0,
        "cover_url": "",
    }


def fetch_gbook(max_products=None, sleep_seconds=0.35, chunk=None, rotate_daily=True, include_urls=None):
    """دریافت قیمت/موجودی از صفحات محصول کتاب گستر.

    chunk: اندیس chunk مشخص؛ rotate_daily: هر روز یک chunk (چرخشی) برای بار منصفانه.
    include_urls: اگر داده شود فقط همین نشانی‌ها خوانده می‌شود.
    """
    if include_urls is None:
        chunks = gbook_catalog_chunks()
        if not chunks:
            raise ValueError("هیچ sitemap محصولی برای کتاب گستر پیدا نشد")
        if chunk is not None:
            selected = [chunks[chunk % len(chunks)]]
        elif rotate_daily:
            day_index = datetime.now().timetuple().tm_yday
            selected = [chunks[day_index % len(chunks)]]
        else:
            selected = chunks
        include_urls = []
        for chunk_url in selected:
            include_urls.extend(gbook_chunk_urls(chunk_url))
    count = 0
    for url in include_urls:
        if max_products and count >= max_products:
            break
        try:
            html = http_get(url, timeout=30).decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            yield {"_error": f"{url}: {exc}"}
            continue
        row = _parse_gbook_page(url, html)
        count += 1
        if row:
            yield row
        time.sleep(sleep_seconds)


def iter_source_rows(source, max_pages=None, max_products=None, sleep_seconds=0.4, gbook_chunk=None):
    """بر اساس قالب منبع، ردیف‌های استاندارد را برمی‌گرداند."""
    host = urlparse(source.feed_url).hostname or ""
    if source.format == "cheshmehdis_api":
        if host and host not in {"server.cheshmehdis.com"}:
            raise ValueError("قالب cheshmehdis_api فقط روی دامنهٔ رسمی server.cheshmehdis.com معتبر است")
        return fetch_cheshmehdis(max_pages=max_pages, sleep_seconds=sleep_seconds)
    if source.format == "gbook_html":
        if host and host not in {"gbook.ir", "www.gbook.ir"}:
            raise ValueError("قالب gbook_html فقط روی دامنهٔ رسمی gbook.ir معتبر است")
        return fetch_gbook(max_products=max_products, sleep_seconds=sleep_seconds, chunk=gbook_chunk)
    raise ValueError(f"قالب {source.format} پشتیبانی نمی‌شود")
