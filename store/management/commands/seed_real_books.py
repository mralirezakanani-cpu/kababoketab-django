from django.core.management.base import BaseCommand
from django.utils.text import slugify
from store.models import Author, Book, Category, Publisher

PRODUCTS = [
    {
        "title": "نامزد آقای مترجم", "code": "204109", "author": "ژوائو خیس",
        "translator": "پدیده الماسی", "isbn": "978-6220113546",
        "pages": 166, "publication_year": 1405, "publication_year_gregorian": 2015,
        "format_size": "رقعی", "cover_type": "شومیز", "edition_number": 3,
        "price": 540000, "sale_price": 375300, "diamonds_reward": 375,
        "cover_url": "https://kababoketab.ir/wp-content/uploads/2026/10/36df8182a4f0497eb6a0daef3d196b6f.jpg",
        "is_featured": True,
    },
    {"title": "لی لی و باغ های جهنم", "price": 220000, "sale_price": 152900, "is_featured": True},
    {"title": "شصت سالگی", "price": 490000, "sale_price": 340550, "is_featured": True},
    {"title": "دوشنبه: پیش به سوی غار دزدان", "price": 550000, "sale_price": 382250, "is_featured": True},
    {"title": "پسری که با اژدها آواز می خواند 5", "price": 195000, "sale_price": 135525, "is_featured": True},
]

class Command(BaseCommand):
    help = "Import verified sample book listings observed on Kabab o Ketab."
    def handle(self, *args, **options):
        publisher, _ = Publisher.objects.get_or_create(slug="nashr-cheshmeh", defaults={"name": "نشر چشمه"})
        fiction, _ = Category.objects.get_or_create(slug=slugify("ادبیات داستانی", allow_unicode=True), defaults={"name": "ادبیات داستانی"})
        for item in PRODUCTS:
            data = item.copy()
            title = data.pop("title")
            author_name = data.pop("author", "")
            author = None
            if author_name:
                author, _ = Author.objects.get_or_create(slug=slugify(author_name, allow_unicode=True), defaults={"name": author_name})
            book, _ = Book.objects.update_or_create(slug=slugify(title, allow_unicode=True), defaults={
                "title": title, "publisher": publisher, "author": author, "stock": 1, **data,
            })
            book.categories.add(fiction)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(PRODUCTS)} live book listings."))
