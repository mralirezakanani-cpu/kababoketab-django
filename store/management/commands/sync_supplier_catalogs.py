import csv
import hashlib
import io
import json
import os
import re
import zipfile
from collections import defaultdict
from datetime import timedelta
import urllib.error
import urllib.request
from urllib.parse import urlparse

import openpyxl

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from store.models import Book, SupplierOffer, SupplierSource
from store.suppliers import iter_source_rows, normalize_isbn

MAX_FEED_BYTES = 15 * 1024 * 1024


def normalize_isbn(value):
    value = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    return re.sub(r"[^0-9Xx]", "", value).upper()


def as_toman(value, unit):
    if value in (None, ""):
        return None
    normalized = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    normalized = normalized.replace(",", "").replace("٬", "").strip()
    amount = int(normalized)
    if amount < 0:
        raise ValueError("قیمت نمی‌تواند منفی باشد")
    if unit == "rial":
        if amount % 10:
            raise ValueError("قیمت ریالی باید مضرب ۱۰ باشد تا به تومان تبدیل شود")
        amount //= 10
    return amount


def read_feed(source):
    parsed = urlparse(source.feed_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("نشانی فید باید HTTPS باشد")
    if source.format == "qoqnoosp_xlsx" and parsed.hostname not in {"qoqnoosp.com", "www.qoqnoosp.com"}:
        raise ValueError("قالب ZIP/XLSX ققنوس فقط برای دامنه رسمی qoqnoosp.com مجاز است")
    accept = "application/x-zip-compressed, application/zip, */*" if source.format == "qoqnoosp_xlsx" else "application/json, text/csv"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KababBookSupplierSync/1.0)", "Accept": accept}
    if source.token_env_var:
        token = os.environ.get(source.token_env_var)
        if not token:
            raise ValueError(f"متغیر محیطی {source.token_env_var} تنظیم نشده است")
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(source.feed_url, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(MAX_FEED_BYTES + 1)
        if len(body) > MAX_FEED_BYTES:
            raise ValueError("حجم فید از حد ۱۵ مگابایت بیشتر است")
        charset = response.headers.get_content_charset() or "utf-8-sig"
    if source.format == "qoqnoosp_xlsx":
        try:
            archive_context = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile as exc:
            raise ValueError("فایل دریافتی از ققنوس ZIP معتبر نیست") from exc
        with archive_context as archive:
            member = next((name for name in archive.namelist() if name.endswith("/کتب موجود.xlsx")), None)
            if not member:
                raise ValueError("فایل کتب موجود.xlsx در ZIP پیدا نشد")
            if archive.getinfo(member).file_size > 40 * 1024 * 1024:
                raise ValueError("فایل فهرست محصولات از حد ۴۰ مگابایت بیشتر است")
            workbook = openpyxl.load_workbook(io.BytesIO(archive.read(member)), read_only=True, data_only=True)
            try:
                sheet = workbook.active
                iterator = sheet.iter_rows(values_only=True)
                header = next(iterator, None)
                if not header:
                    raise ValueError("فهرست محصولات خالی است")
                columns = {str(value or "").strip(): index for index, value in enumerate(header)}
                required = {"شابك", "نام كتاب", "پشت جلد", "كدكالا سيستم", "ناشر", "فعال"}
                missing = required - columns.keys()
                if missing:
                    raise ValueError(f"ستون‌های لازم در فهرست ققنوس نیست: {', '.join(sorted(missing))}")

                def val(row, name):
                    return row[columns[name]] if name in columns and columns[name] < len(row) else None

                # Duplicate ISBNs occur in the supplier export. Keep the most
                # recently received/current system record; code breaks same-day ties.
                selected = {}
                for row in iterator:
                    title = str(val(row, "نام كتاب") or "").strip()
                    if not title:
                        continue
                    isbn = normalize_isbn(val(row, "شابك"))
                    external_id = str(val(row, "كدكالا سيستم") or val(row, "كدكتابSort") or "").strip()
                    key = f"isbn:{isbn}" if isbn else (f"code:{external_id}" if external_id else "")
                    if not key:
                        continue
                    receive_date = str(val(row, "تاريخ تحويل") or "")
                    code_digits = re.sub(r"\D", "", external_id)
                    rank = (receive_date, int(code_digits or 0))
                    record = {
                        "isbn": isbn, "title": title, "regular_price": val(row, "پشت جلد"),
                        "currency": "rial",
                        "stock": 1 if str(val(row, "فعال") or "").strip() == "فعال" else 0,
                        "author": val(row, "مولف"), "translator": val(row, "مترجم"),
                        "publisher": val(row, "ناشر"), "pages": val(row, "تعداد صفحات"),
                        "weight_grams": val(row, "وزن"), "publication_year": val(row, "سال چاپ"),
                        "edition_number": val(row, "نوبت چاپ"), "format_size": val(row, "قطع"),
                        "cover_type": val(row, "نوع جلد"), "category": val(row, "گروه"),
                        "cover_url": (
                            f"https://qoqnoosp.com/Images/Goods/BigImages/{external_id}.jpg"
                            if re.fullmatch(r"\d+", external_id) else ""
                        ),
                        "external_id": external_id, "_rank": rank,
                    }
                    if key not in selected or rank > selected[key]["_rank"]:
                        selected[key] = record
                return list(selected.values())
            finally:
                workbook.close()
    decoded = body.decode(charset)
    if source.format == "json":
        data = json.loads(decoded)
        if isinstance(data, dict):
            data = data.get("items", data.get("products"))
        if not isinstance(data, list):
            raise ValueError("ساختار JSON باید آرایه یا شیء دارای items/products باشد")
        return data
    return list(csv.DictReader(io.StringIO(decoded)))


class Command(BaseCommand):
    help = "دریافت قیمت و موجودی کتاب‌ها از فید مجاز تأمین‌کننده‌ها (JSON/CSV) با تطبیق شابک"

    def add_arguments(self, parser):
        parser.add_argument("--source", help="شناسه منبع برای اجرای تکی")
        parser.add_argument("--apply", action="store_true", help="قیمت و موجودی سایت را از منابع علامت‌خورده نیز به‌روزرسانی کن")
        parser.add_argument("--max-pages", type=int, default=None, help="سقف صفحه برای منبع‌های صفحه‌بندی‌شده (تست)")
        parser.add_argument("--max-products", type=int, default=None, help="سقف محصول برای منبع‌های صفحه‌محور مثل کتاب گستر (تست)")
        parser.add_argument("--sleep", type=float, default=0.4, help="فاصلهٔ مودبانه بین درخواست‌ها به ثانیه")
        parser.add_argument("--import-new", action="store_true", help="کتاب‌های جدید منبع (که با شابک در فروشگاه نیستند) را نیز اضافه کن")
        parser.add_argument("--gbook-chunk", type=int, default=None, help="اندیس chunk مشخص sitemap کتاب گستر")

    def handle(self, *args, **options):
        self.max_pages = options["max_pages"]
        self.max_products = options["max_products"]
        self.sleep_seconds = options["sleep"]
        self.import_new = options["import_new"]
        self.gbook_chunk = options["gbook_chunk"]
        self.ensure_default_sources()
        sources = SupplierSource.objects.filter(enabled=True)
        if options["source"]:
            sources = sources.filter(slug=options["source"])
        if not sources.exists():
            raise CommandError("منبع فعالی پیدا نشد. ابتدا در پنل مدیریت یک منبع با فید HTTPS بسازید و فعال کنید.")
        succeeded = 0
        for source in sources:
            succeeded += int(self.sync_one(source))
        if options["apply"] and succeeded:
            updated = self.apply_references()
            self.stdout.write(self.style.SUCCESS(f"{updated} کتاب با سیاست منابع مرجع در کاتالوگ فروشگاه به‌روزرسانی شد."))

    def ensure_default_sources(self):
        SupplierSource.objects.get_or_create(
            slug="qoqnoosp",
            defaults={
                "name": "پخش ققنوس",
                "feed_url": "https://qoqnoosp.com/Downloads/available-products.zip",
                "format": "qoqnoosp_xlsx",
                "enabled": True,
                "use_for_price": True,
                "use_for_stock": True,
                "update_store_prices": True,
            },
        )
        SupplierSource.objects.get_or_create(
            slug="cheshmehdis",
            defaults={
                "name": "پخش چشمه",
                "feed_url": "https://server.cheshmehdis.com/api/v1/search",
                "format": "cheshmehdis_api",
                "enabled": True,
                "use_for_price": True,
                "use_for_stock": True,
                "update_store_prices": True,
                "priority": 20,
            },
        )
        SupplierSource.objects.get_or_create(
            slug="gbook",
            defaults={
                "name": "کتاب گستر (gbook)",
                "feed_url": "https://gbook.ir/sitemap.xml",
                "format": "gbook_html",
                "enabled": True,
                "use_for_price": True,
                "use_for_stock": True,
                "update_store_prices": True,
                "priority": 30,
            },
        )

    def sync_one(self, source):
        try:
            if not source.feed_url:
                raise ValueError("نشانی فید تنظیم نشده است")
            if source.format in ("cheshmehdis_api", "gbook_html"):
                rows = list(iter_source_rows(
                    source, max_pages=self.max_pages, max_products=self.max_products,
                    sleep_seconds=self.sleep_seconds, gbook_chunk=self.gbook_chunk,
                ))
                rows = [row for row in rows if "_error" not in row]
                if self.import_new and source.format == "cheshmehdis_api":
                    imported, import_errors = self.import_books_from_rows(rows, source)
                    self.stdout.write(f"ورود کتاب‌های جدید {source.name}: {imported} اضافه/به‌روز شد؛ {import_errors} ردیف رد شد.")
            else:
                rows = read_feed(source)
                if source.format == "qoqnoosp_xlsx":
                    imported, import_errors = self.import_qoqnoosp_books(rows)
                    self.stdout.write(f"فهرست ققنوس: {imported} کتاب اضافه/به‌روز شد؛ {import_errors} ردیف به علت نبود قیمت یا داده نامعتبر رد شد.")
            books = {normalize_isbn(book.isbn): book for book in Book.objects.exclude(isbn="")}
            books_by_code = {book.code: book for book in Book.objects.exclude(code="")}
            matched = invalid = 0
            for row in rows:
                try:
                    isbn = normalize_isbn(row.get("isbn") or row.get("ISBN") or row.get("shabak"))
                    external_raw = str(row.get("external_id") or "").strip()
                    external_code = external_raw if "-" in external_raw else (f"QQ-{external_raw}" if external_raw else "")
                    book = books.get(isbn) if isbn else books_by_code.get(external_code)
                    if not book:
                        continue
                    if "price" not in row and "regular_price" not in row:
                        raise ValueError("فیلد price یا regular_price وجود ندارد")
                    regular = as_toman(row.get("regular_price", row.get("price")), row.get("currency", "toman").lower())
                    sale_raw = row.get("sale_price", row.get("discount_price"))
                    sale = as_toman(sale_raw, row.get("currency", "toman").lower()) if sale_raw not in (None, "") else None
                    stock_raw = row.get("stock", row.get("quantity", 0))
                    if isinstance(stock_raw, str) and stock_raw.strip().lower() in {"true", "yes", "in_stock", "موجود", "موجود است"}:
                        stock = 1
                    elif isinstance(stock_raw, str) and stock_raw.strip().lower() in {"false", "no", "out_of_stock", "ناموجود", "ناموجود است"}:
                        stock = 0
                    else:
                        stock = int(str(stock_raw).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
                    if regular is None or stock < 0 or (sale is not None and sale > regular):
                        raise ValueError("قیمت یا موجودی نامعتبر است")
                    with transaction.atomic():
                        SupplierOffer.objects.update_or_create(
                            source=source, book=book,
                            defaults={"source_isbn": isbn or f"NOISBN-{external_raw}", "regular_price": regular, "sale_price": sale,
                                      "stock": stock, "product_url": str(row.get("url", row.get("product_url", "")))[:200]},
                        )
                    matched += 1
                except (TypeError, ValueError, OverflowError):
                    invalid += 1
            if not matched:
                raise ValueError("هیچ شابک معتبری از فید با کتاب‌های فروشگاه تطبیق نکرد؛ تغییری در فروشگاه اعمال نشد")
            message = f"{matched} پیشنهاد قیمت/موجودی ثبت شد؛ {invalid} رکورد نامعتبر رد شد."
            source.last_sync_at = timezone.now()
            source.last_sync_status = "موفق"
            source.last_sync_message = message
            source.save(update_fields=["last_sync_at", "last_sync_status", "last_sync_message"])
            self.stdout.write(self.style.SUCCESS(f"{source.name}: {message}"))
            return True
        except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            source.last_sync_at = timezone.now()
            source.last_sync_status = "خطا"
            source.last_sync_message = str(exc)[:2000]
            source.save(update_fields=["last_sync_at", "last_sync_status", "last_sync_message"])
            self.stderr.write(self.style.ERROR(f"{source.name}: {exc}"))
            return False

    def import_books_from_rows(self, rows, source):
        """ورود کتاب‌های جدید منابع صفحه‌بندی‌شده (چشمه) با تطبیق شابک؛ ققنوس مسیر مخصوص خودش را دارد."""
        from django.utils.text import slugify
        from store.models import Author, Category, Publisher

        publishers = {self.name_key(obj.name): obj for obj in Publisher.objects.all()}
        authors = {self.name_key(obj.name): obj for obj in Author.objects.all()}
        categories = {self.name_key(obj.name): obj for obj in Category.objects.all()}
        existing_isbn = {normalize_isbn(book.isbn): book for book in Book.objects.exclude(isbn="") if normalize_isbn(book.isbn)}
        existing_code = {book.code: book for book in Book.objects.exclude(code="")}
        pending_publishers, pending_authors, pending_categories = [], [], []
        pending_books, updated_books, category_pairs, offers = [], [], [], []
        errors = 0

        def make_slug(prefix, name):
            digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
            return f"{prefix}-{digest}"

        for row in rows:
            try:
                title = str(row.get("title") or "").strip()
                price = int(row.get("regular_price") or 0)
                isbn = normalize_isbn(row.get("isbn"))
                external_raw = str(row.get("external_id") or "").strip()
                if not title or price <= 0 or not isbn:
                    errors += 1
                    continue
                code = external_raw or f"{source.slug.upper()}-{hashlib.sha1(title.encode()).hexdigest()[:10]}"
                stock = max(0, int(row.get("stock") or 0))

                publisher_name = str(row.get("publisher") or "").strip()[:160] or "نامشخص"
                pub_key = self.name_key(publisher_name)
                publisher = publishers.get(pub_key)
                if publisher is None:
                    publisher = Publisher(name=publisher_name, slug=make_slug("pub", pub_key))
                    publishers[pub_key] = publisher
                    pending_publishers.append(publisher)

                author_name = str(row.get("author") or "").strip()[:160]
                author = None
                if author_name:
                    auth_key = self.name_key(author_name)
                    author = authors.get(auth_key)
                    if author is None:
                        author = Author(name=author_name, slug=make_slug("aut", auth_key))
                        authors[auth_key] = author
                        pending_authors.append(author)

                book = existing_isbn.get(isbn) or existing_code.get(code)
                if book is None:
                    base_slug = slugify(title, allow_unicode=True)[:34].strip("-") or "book"
                    book = Book(slug=f"{base_slug}-{isbn[-10:]}")
                    pending_books.append(book)
                else:
                    updated_books.append(book)
                book.title = title[:240]
                book.code = code[:40]
                book.isbn = isbn[:32]
                book.publisher = publisher
                book.author = author
                book.translator = str(row.get("translator") or "").strip()[:160]
                book.price = price
                book.sale_price = None if book.pk is None else book.sale_price
                book.stock = stock
                book.pages = row.get("pages")
                book.weight_grams = int(row.get("weight_grams") or 0)
                publication_year = row.get("publication_year")
                book.publication_year = publication_year if publication_year is not None and 1200 <= publication_year <= 1405 else None
                book.format_size = str(row.get("format_size") or "").strip()[:60]
                book.cover_type = str(row.get("cover_type") or "").strip()[:60]
                cover_url = str(row.get("cover_url") or "").strip()
                if cover_url and (not book.cover_url or book.cover_url.startswith("https://server.cheshmehdis.com/storage/")):
                    book.cover_url = cover_url
                if isbn:
                    existing_isbn[isbn] = book
                existing_code[code] = book
                offers.append(SupplierOffer(
                    source=source, book=book, source_isbn=isbn,
                    regular_price=price, sale_price=row.get("sale_price"), stock=stock,
                    product_url=str(row.get("url") or "")[:200],
                ))
            except (TypeError, ValueError, OverflowError):
                errors += 1

        Publisher.objects.bulk_create(pending_publishers, batch_size=500, ignore_conflicts=True)
        Author.objects.bulk_create(pending_authors, batch_size=500, ignore_conflicts=True)
        publisher_map = {self.name_key(obj.name): obj for obj in Publisher.objects.all()}
        author_map = {self.name_key(obj.name): obj for obj in Author.objects.all()}
        for book in pending_books + updated_books:
            book.publisher = publisher_map.get(self.name_key(book.publisher.name), book.publisher)
            book.author = author_map.get(self.name_key(book.author.name), book.author) if book.author else None
        Book.objects.bulk_create(pending_books, batch_size=500)
        Book.objects.bulk_update(updated_books, ["title", "code", "isbn", "publisher", "author", "translator", "price", "sale_price", "stock", "pages", "weight_grams", "publication_year", "format_size", "cover_type", "cover_url"], batch_size=500)
        SupplierOffer.objects.bulk_create(
            offers, batch_size=500, update_conflicts=True,
            unique_fields=["source", "book"],
            update_fields=["source_isbn", "regular_price", "sale_price", "stock", "product_url", "checked_at"],
        )
        return len(pending_books) + len(updated_books), errors

    def import_qoqnoosp_books(self, rows):
        """Import current product facts from the distributor's public availability workbook."""
        from django.utils.text import slugify
        from store.models import Author, Category, Publisher

        source = SupplierSource.objects.get(slug="qoqnoosp")
        publishers = {self.name_key(obj.name): obj for obj in Publisher.objects.all()}
        authors = {self.name_key(obj.name): obj for obj in Author.objects.all()}
        categories = {self.name_key(obj.name): obj for obj in Category.objects.all()}
        existing_isbn = {normalize_isbn(book.isbn): book for book in Book.objects.exclude(isbn="") if normalize_isbn(book.isbn)}
        existing_code = {book.code: book for book in Book.objects.exclude(code="")}
        pending_publishers, pending_authors, pending_categories = [], [], []
        pending_books, updated_books, category_pairs, offers = [], [], [], []
        errors = 0

        def make_slug(prefix, name):
            digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
            return f"{prefix}-{digest}"

        def number(value, default=None):
            if value in (None, ""):
                return default
            try:
                return int(float(str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace(",", "").strip()))
            except (TypeError, ValueError, OverflowError):
                return default

        for row in rows:
            try:
                title = str(row.get("title") or "").strip()
                rial = number(row.get("regular_price"))
                if not title or rial is None or rial <= 0:
                    errors += 1
                    continue
                if rial % 10:
                    # Round the supplier's rial value to the nearest toman.
                    price = (rial + 5) // 10
                else:
                    price = rial // 10
                isbn = normalize_isbn(row.get("isbn"))
                external_id = str(row.get("external_id") or "").strip()
                if not isbn and not external_id:
                    errors += 1
                    continue
                code = f"QQ-{external_id}" if external_id else f"QQ-{hashlib.sha1(title.encode()).hexdigest()[:10]}"

                publisher_name = str(row.get("publisher") or "نامشخص").strip()[:160]
                pub_key = self.name_key(publisher_name)
                publisher = publishers.get(pub_key)
                if publisher is None:
                    publisher = Publisher(name=publisher_name, slug=make_slug("qpub", pub_key))
                    publishers[pub_key] = publisher
                    pending_publishers.append(publisher)

                author_name = str(row.get("author") or "").strip()[:160]
                author = None
                if author_name:
                    auth_key = self.name_key(author_name)
                    author = authors.get(auth_key)
                    if author is None:
                        author = Author(name=author_name, slug=make_slug("qaut", auth_key))
                        authors[auth_key] = author
                        pending_authors.append(author)

                category_name = str(row.get("category") or "").strip()[:120]
                category = None
                if category_name:
                    cat_key = self.name_key(category_name)
                    category = categories.get(cat_key)
                    if category is None:
                        category = Category(name=category_name, slug=make_slug("qcat", cat_key))
                        categories[cat_key] = category
                        pending_categories.append(category)

                book = existing_isbn.get(isbn) if isbn else None
                book = book or existing_code.get(code)
                if book is None:
                    base_slug = slugify(title, allow_unicode=True)[:34].strip("-") or "book"
                    book = Book(slug=f"{base_slug}-{external_id[-10:] or hashlib.sha1(title.encode()).hexdigest()[:10]}")
                    pending_books.append(book)
                else:
                    updated_books.append(book)
                book.title = title[:240]
                book.code = code[:40]
                book.isbn = isbn[:32]
                book.publisher = publisher
                book.author = author
                book.translator = str(row.get("translator") or "").strip()[:160]
                book.price = price
                book.sale_price = None if book.pk is None else book.sale_price
                book.stock = int(row.get("stock") or 0)
                book.pages = number(row.get("pages"), None)
                book.weight_grams = number(row.get("weight_grams"), 0) or 0
                publication_year = number(row.get("publication_year"), None)
                book.publication_year = publication_year if publication_year is not None and 1200 <= publication_year <= 1405 else None
                book.edition_number = number(row.get("edition_number"), None)
                book.format_size = str(row.get("format_size") or "").strip()[:60]
                book.cover_type = str(row.get("cover_type") or "").strip()[:60]
                cover_url = str(row.get("cover_url") or "").strip()
                if cover_url and (
                    not book.cover_url
                    or book.cover_url.startswith("https://qoqnoosp.com/Images/Goods/BigImages/")
                ):
                    book.cover_url = cover_url
                if isbn:
                    existing_isbn[isbn] = book
                existing_code[code] = book
                if category:
                    category_pairs.append((book, category))
                offers.append(SupplierOffer(
                    source=source, book=book, source_isbn=isbn or f"NOISBN-{external_id}",
                    regular_price=price, sale_price=None, stock=book.stock, product_url="",
                ))
            except (TypeError, ValueError, OverflowError):
                errors += 1

        Publisher.objects.bulk_create(pending_publishers, batch_size=500, ignore_conflicts=True)
        Author.objects.bulk_create(pending_authors, batch_size=500, ignore_conflicts=True)
        Category.objects.bulk_create(pending_categories, batch_size=500, ignore_conflicts=True)
        # Refresh foreign keys for entities that may have collided with older records.
        publisher_map = {self.name_key(obj.name): obj for obj in Publisher.objects.all()}
        author_map = {self.name_key(obj.name): obj for obj in Author.objects.all()}
        category_map = {self.name_key(obj.name): obj for obj in Category.objects.all()}
        for book in pending_books + updated_books:
            book.publisher = publisher_map.get(self.name_key(book.publisher.name), book.publisher)
            book.author = author_map.get(self.name_key(book.author.name), book.author) if book.author else None
        Book.objects.bulk_create(pending_books, batch_size=500)
        Book.objects.bulk_update(updated_books, ["title", "code", "isbn", "publisher", "author", "translator", "price", "sale_price", "stock", "pages", "weight_grams", "publication_year", "edition_number", "format_size", "cover_type", "cover_url"], batch_size=500)
        through = Book.categories.through
        through.objects.bulk_create(
            [through(book_id=book.pk, category_id=category_map[self.name_key(category.name)].pk) for book, category in category_pairs if book.pk],
            batch_size=1000, ignore_conflicts=True,
        )
        SupplierOffer.objects.bulk_create(
            offers, batch_size=500, update_conflicts=True,
            unique_fields=["source", "book"],
            update_fields=["source_isbn", "regular_price", "sale_price", "stock", "product_url", "checked_at"],
        )
        return len(pending_books) + len(updated_books), errors

    @staticmethod
    def name_key(value):
        value = str(value or "").translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"}))
        return " ".join(value.split()).casefold()

    def apply_references(self):
        """Pick one coherent price pair and conservative inventory per book."""
        sources = list(SupplierSource.objects.filter(enabled=True, update_store_prices=True))
        if not sources:
            self.stdout.write("هیچ منبعی اجازهٔ اعمال روی قیمت/موجودی فروشگاه ندارد؛ پیشنهادها فقط ذخیره شدند.")
            return 0
        source_by_id = {source.pk: source for source in sources}
        offers_by_book = defaultdict(list)
        for offer in SupplierOffer.objects.filter(source__in=sources).select_related("source", "book"):
            ttl = timedelta(hours=max(1, offer.source.offer_ttl_hours))
            if offer.checked_at >= timezone.now() - ttl:
                offers_by_book[offer.book_id].append(offer)

        books = {
            book.pk: book
            for book in Book.objects.filter(supplier_offers__source__in=sources).distinct()
        }
        changed_books = []
        for book_id, offers in offers_by_book.items():
            price_offers = [offer for offer in offers if source_by_id[offer.source_id].use_for_price]
            stock_offers = [offer for offer in offers if source_by_id[offer.source_id].use_for_stock]
            updates = {}
            if price_offers:
                best_price = min(
                    price_offers,
                    key=lambda offer: (
                        offer.sale_price if offer.sale_price is not None else offer.regular_price,
                        source_by_id[offer.source_id].priority,
                        offer.checked_at,
                    ),
                )
                updates["price"] = best_price.regular_price
                updates["sale_price"] = best_price.sale_price
            if stock_offers:
                # Do not add independent supplier inventories together; use the
                # largest confirmed quantity available from one source.
                best_stock = max(
                    stock_offers,
                    key=lambda offer: (
                        offer.stock,
                        -source_by_id[offer.source_id].priority,
                        offer.checked_at,
                    ),
                )
                updates["stock"] = best_stock.stock
            if updates:
                book = books.get(book_id)
                if not book:
                    continue
                modified = False
                for field, value in updates.items():
                    if getattr(book, field) != value:
                        setattr(book, field, value)
                        modified = True
                if modified:
                    changed_books.append(book)
        if changed_books:
            # The reference policy always derives all three values for books
            # with offers, so batch writes instead of issuing one UPDATE per book.
            Book.objects.bulk_update(changed_books, ["price", "sale_price", "stock"], batch_size=100)
        return len(changed_books)
