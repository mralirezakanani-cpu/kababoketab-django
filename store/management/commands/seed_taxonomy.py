from django.core.management.base import BaseCommand
from django.utils.text import slugify
from store.models import Category, SummaryTopic, Publisher

BOOK_CATEGORIES = {
    "ادبیات": ["ادبیات داستانی", "رمان", "داستان کوتاه", "ادبیات غیرداستانی", "ادبیات ملل", "شعر", "سبک‌های ادبی"],
    "علوم و فناوری": ["کتاب‌های آموزشی", "دانستنی‌ها", "مهندسی", "علوم انسانی", "علوم تجربی", "کسب‌وکار"],
    "هنر": ["طراحی", "طنز", "کارگردانی", "معماری", "آشپزی", "عکاسی", "موسیقی", "بازیگری", "داستان‌نویسی", "سینما و تئاتر", "فیلمنامه", "نقاشی"],
    "کودک و نوجوان": [],
    "مرجع و سرگرمی": ["دایرةالمعارف", "کتاب‌های مصور", "کتاب‌های مرجع"],
}
SUMMARY_TOPICS = [
    "کارآفرینی", "علم", "اقتصاد", "پول و سرمایه‌گذاری", "روابط عاطفی", "فرزندپروری",
    "زندگی‌نامه", "دین و عرفان", "سیاست", "سلامت و تغذیه", "تاریخ", "مدیریت و رهبری",
    "روان‌شناسی", "فناوری", "جامعه و فرهنگ", "کار و موفقیت", "خلاقیت", "بازاریابی",
    "پیشرفت فردی", "مهارت‌های ارتباطی", "انگیزه و الهام", "بهره‌وری", "طبیعت و محیط‌زیست",
    "آموزش", "فلسفه", "هنر", "ادبیات",
]
PUBLISHERS = ["چشمه", "ققنوس", "فنی ایران نردبان", "قدیانی", "نگاه", "افق", "ثالث", "نی", "پرتقال", "سوره مهر", "کانون پرورش فکری"]

class Command(BaseCommand):
    help = "Create the initial book categories and diamond summary topics."
    def handle(self, *args, **options):
        for parent_name, children in BOOK_CATEGORIES.items():
            parent, _ = Category.objects.get_or_create(slug=slugify(parent_name, allow_unicode=True), defaults={"name": parent_name})
            for name in children:
                child, _ = Category.objects.get_or_create(slug=slugify(name, allow_unicode=True), defaults={"name": name, "parent": parent})
                if child.parent_id is None:
                    child.parent = parent
                    child.save(update_fields=["parent"])
        for name in SUMMARY_TOPICS:
            SummaryTopic.objects.get_or_create(slug=slugify(name, allow_unicode=True), defaults={"name": name})
        for name in PUBLISHERS:
            Publisher.objects.get_or_create(slug=slugify(name, allow_unicode=True), defaults={"name": name})
        self.stdout.write(self.style.SUCCESS("Book categories, publishers and summary topics are ready."))
