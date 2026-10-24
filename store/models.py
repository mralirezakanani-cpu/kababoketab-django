from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.urls import reverse

class Category(models.Model):
    name = models.CharField("نام موضوع", max_length=120)
    slug = models.SlugField(unique=True, allow_unicode=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    class Meta:
        ordering = ["name"]
        verbose_name = "موضوع"
        verbose_name_plural = "موضوع‌ها"
    def __str__(self): return self.name

class Publisher(models.Model):
    name = models.CharField("نام ناشر", max_length=160)
    slug = models.SlugField(unique=True, allow_unicode=True)
    class Meta:
        ordering = ["name"]
        verbose_name = "ناشر"
        verbose_name_plural = "ناشرها"
    def __str__(self): return self.name

class Author(models.Model):
    name = models.CharField("نام نویسنده", max_length=160)
    slug = models.SlugField(unique=True, allow_unicode=True)
    bio = models.TextField("زندگی‌نامه", blank=True)
    class Meta:
        ordering = ["name"]
        verbose_name = "نویسنده"
        verbose_name_plural = "نویسنده‌ها"
    def __str__(self): return self.name

class Book(models.Model):
    title = models.CharField("عنوان", max_length=240)
    slug = models.SlugField(unique=True, allow_unicode=True)
    code = models.CharField("کد کتاب", max_length=40, blank=True)
    isbn = models.CharField("شابک", max_length=32, blank=True)
    author = models.ForeignKey(Author, null=True, blank=True, on_delete=models.SET_NULL, related_name="books")
    translator = models.CharField("مترجم", max_length=160, blank=True)
    publisher = models.ForeignKey(Publisher, null=True, blank=True, on_delete=models.SET_NULL, related_name="books")
    categories = models.ManyToManyField(Category, blank=True, related_name="books", verbose_name="موضوع‌ها")
    description = models.TextField("معرفی کتاب", blank=True)
    price = models.PositiveIntegerField("قیمت (تومان)")
    sale_price = models.PositiveIntegerField("قیمت با تخفیف (تومان)", null=True, blank=True)
    stock = models.PositiveIntegerField("موجودی", default=0)
    weight_grams = models.PositiveIntegerField("وزن (گرم)", default=0)
    pages = models.PositiveIntegerField("تعداد صفحه", null=True, blank=True)
    publication_year = models.PositiveSmallIntegerField("سال انتشار شمسی", null=True, blank=True)
    publication_year_gregorian = models.PositiveSmallIntegerField("سال انتشار میلادی", null=True, blank=True)
    format_size = models.CharField("قطع", max_length=60, blank=True)
    cover_type = models.CharField("نوع جلد", max_length=60, blank=True)
    edition_number = models.PositiveSmallIntegerField("سری چاپ", null=True, blank=True)
    cover_url = models.URLField("نشانی تصویر جلد", blank=True)
    is_featured = models.BooleanField("پیشنهاد ویژه", default=False)
    diamonds_reward = models.PositiveSmallIntegerField("الماس خرید", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "کتاب"
        verbose_name_plural = "کتاب‌ها"
    def __str__(self): return self.title
    @property
    def current_price(self): return self.sale_price if self.sale_price is not None else self.price
    @property
    def discount_amount(self): return max(0, self.price - self.current_price)
    @property
    def discount_percent(self):
        return round((self.price - self.current_price) * 100 / self.price) if self.price else 0
    def get_absolute_url(self): return reverse("book_detail", args=[self.slug])

class SupplierSource(models.Model):
    """A supplier catalog exposed as an authorized JSON or CSV feed."""
    FORMAT_CHOICES = [("json", "JSON"), ("csv", "CSV"), ("qoqnoosp_xlsx", "فایل رسمی محصولات ققنوس (ZIP/XLSX)"), ("cheshmehdis_api", "API رسمی پخش چشمه"), ("gbook_html", "صفحات محصول کتاب گستر (gbook.ir)")]
    name = models.CharField("نام منبع", max_length=120)
    slug = models.SlugField("شناسه", unique=True, allow_unicode=True)
    feed_url = models.URLField("نشانی فید محصول", blank=True)
    format = models.CharField("قالب فید", max_length=16, choices=FORMAT_CHOICES, default="json")
    enabled = models.BooleanField("فعال", default=False)
    update_store_prices = models.BooleanField("اجازهٔ اعمال قیمت و موجودی روی فروشگاه", default=False)
    use_for_price = models.BooleanField("مرجع انتخاب قیمت", default=True)
    use_for_stock = models.BooleanField("مرجع انتخاب موجودی", default=True)
    priority = models.PositiveSmallIntegerField("اولویت در قیمت‌های برابر", default=100)
    offer_ttl_hours = models.PositiveSmallIntegerField("اعتبار داده (ساعت)", default=24)
    token_env_var = models.CharField("نام متغیر محیطی توکن", max_length=120, blank=True)
    last_sync_at = models.DateTimeField("آخرین همگام‌سازی", null=True, blank=True)
    last_sync_status = models.CharField("نتیجه آخرین همگام‌سازی", max_length=16, blank=True)
    last_sync_message = models.TextField("گزارش آخرین همگام‌سازی", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "منبع تأمین کتاب"
        verbose_name_plural = "منابع تأمین کتاب"

    def __str__(self): return self.name

class SupplierOffer(models.Model):
    source = models.ForeignKey(SupplierSource, on_delete=models.CASCADE, related_name="offers", verbose_name="منبع")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="supplier_offers", verbose_name="کتاب")
    source_isbn = models.CharField("شابک منبع", max_length=32)
    regular_price = models.PositiveIntegerField("قیمت بدون تخفیف منبع (تومان)")
    sale_price = models.PositiveIntegerField("قیمت تخفیف‌خورده منبع (تومان)", null=True, blank=True)
    stock = models.PositiveIntegerField("موجودی منبع", default=0)
    product_url = models.URLField("صفحه محصول در منبع", blank=True)
    checked_at = models.DateTimeField("آخرین بررسی", auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "book"], name="unique_supplier_offer_per_book")]
        ordering = ["source__name", "book__title"]
        verbose_name = "قیمت و موجودی تأمین‌کننده"
        verbose_name_plural = "قیمت‌ها و موجودی تأمین‌کننده‌ها"

    def __str__(self): return f"{self.book} — {self.source}"

class Review(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField("امتیاز", choices=[(i, str(i)) for i in range(1, 6)])
    body = models.TextField("دیدگاه")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["book", "user"], name="one_review_per_user_book")]
        verbose_name = "دیدگاه"
        verbose_name_plural = "دیدگاه‌ها"
    def __str__(self): return f"{self.user} — {self.book}"

class SummaryTopic(models.Model):
    name = models.CharField("موضوع خلاصه", max_length=120, unique=True)
    slug = models.SlugField(unique=True, allow_unicode=True)
    class Meta:
        ordering = ["name"]
        verbose_name = "موضوع خلاصه"
        verbose_name_plural = "موضوع‌های خلاصه"
    def __str__(self): return self.name

class PodcastEpisode(models.Model):
    title = models.CharField("عنوان اپیزود", max_length=240)
    topic = models.ForeignKey(SummaryTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="episodes")
    description = models.TextField("توضیحات", blank=True)
    audio_url = models.URLField("نشانی فایل صوتی", blank=True)
    published = models.BooleanField("منتشر شده", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "اپیزود پادکست"
        verbose_name_plural = "اپیزودهای پادکست"
    def __str__(self): return self.title

class Article(models.Model):
    title = models.CharField("عنوان مقاله", max_length=240)
    slug = models.SlugField(unique=True, allow_unicode=True)
    excerpt = models.TextField("خلاصه", blank=True)
    body = models.TextField("متن مقاله")
    cover_url = models.URLField("نشانی تصویر", blank=True)
    premium = models.BooleanField("ویژهٔ اعضا", default=False)
    topics = models.ManyToManyField(SummaryTopic, blank=True, related_name="articles", verbose_name="موضوع‌ها")
    published = models.BooleanField("منتشر شده", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "مقاله"
        verbose_name_plural = "مقاله‌ها"
    def __str__(self): return self.title

class MembershipPlan(models.Model):
    PERIODS = [("month", "یک‌ماهه"), ("quarter", "سه‌ماهه"), ("year", "یک‌ساله")]
    title = models.CharField("عنوان", max_length=100)
    period = models.CharField("مدت", max_length=16, choices=PERIODS, unique=True)
    days = models.PositiveSmallIntegerField("تعداد روز")
    price = models.PositiveIntegerField("قیمت (تومان)")
    active = models.BooleanField("فعال", default=True)
    def __str__(self): return self.title
    class Meta:
        verbose_name = "پلن عضویت الماسی"
        verbose_name_plural = "پلن‌های عضویت الماسی"

class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT)
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    def __str__(self): return f"{self.user} — {self.plan}"
    class Meta:
        verbose_name = "عضویت الماسی"
        verbose_name_plural = "عضویت‌های الماسی"

class WalletAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet", verbose_name="مشتری")
    balance = models.PositiveIntegerField("موجودی (تومان)", default=0)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)
    class Meta:
        verbose_name = "کیف پول"
        verbose_name_plural = "کیف پول‌ها"
    def __str__(self): return f"کیف پول {self.user} — {self.balance:,} تومان"

class Coupon(models.Model):
    DISCOUNT_TYPES = [("percent", "درصدی"), ("fixed", "مبلغ ثابت")]
    code = models.CharField("کد تخفیف", max_length=40, unique=True)
    discount_type = models.CharField("نوع تخفیف", max_length=10, choices=DISCOUNT_TYPES, default="percent")
    value = models.PositiveIntegerField("درصد یا مبلغ (تومان)", validators=[MinValueValidator(1)])
    maximum_discount = models.PositiveIntegerField("سقف تخفیف (تومان)", null=True, blank=True)
    minimum_order = models.PositiveIntegerField("حداقل مبلغ کتاب‌ها (تومان)", default=0)
    starts_at = models.DateTimeField("شروع اعتبار", null=True, blank=True)
    expires_at = models.DateTimeField("پایان اعتبار", null=True, blank=True)
    usage_limit = models.PositiveIntegerField("سقف کل استفاده", null=True, blank=True)
    per_customer_limit = models.PositiveSmallIntegerField("سقف استفاده برای هر مشتری", default=1, validators=[MinValueValidator(1)])
    active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کدهای تخفیف"
    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.discount_type == "percent" and self.value > 100:
            raise ValidationError({"value": "تخفیف درصدی نمی‌تواند بیشتر از ۱۰۰ باشد."})
        if self.starts_at and self.expires_at and self.expires_at <= self.starts_at:
            raise ValidationError({"expires_at": "پایان اعتبار باید بعد از شروع آن باشد."})
    def __str__(self): return self.code

class CouponRedemption(models.Model):
    STATUSES = [("reserved", "رزروشده برای سفارش"), ("used", "مصرف‌شده"), ("released", "آزادشده")]
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions", verbose_name="کد تخفیف")
    order = models.OneToOneField("Order", on_delete=models.CASCADE, related_name="coupon_redemption", verbose_name="سفارش")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="coupon_redemptions", verbose_name="مشتری")
    phone = models.CharField("موبایل", max_length=20, blank=True)
    email = models.EmailField("ایمیل", blank=True)
    discount_amount = models.PositiveIntegerField("مبلغ تخفیف (تومان)")
    status = models.CharField("وضعیت", max_length=12, choices=STATUSES, default="reserved")
    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "مصرف کد تخفیف"
        verbose_name_plural = "مصرف کدهای تخفیف"
    def __str__(self): return f"{self.coupon.code} — {self.order.tracking_code}"

class Order(models.Model):
    STATUS = [("pending", "در انتظار پرداخت"), ("paid", "پرداخت‌شده"), ("preparing", "در حال آماده‌سازی"), ("shipped", "ارسال‌شده"), ("delivered", "تحویل‌شده"), ("cancelled", "لغوشده"), ("refunded", "مستردشده")]
    SHIPPING = [("tehran_express", "پیک ویژه تهران با بیمه"), ("tehran_courier", "پیک تهران (بازهٔ ۱۵ تا ۲۱)"), ("post_insured", "پست پیشتاز با بسته‌بندی ویژه و بیمه"), ("post_standard", "پست پیشتاز با بسته‌بندی معمولی"), ("freight", "باربری سفارش حجیم"), ("pickup", "تحویل حضوری تهران")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    tracking_code = models.CharField("کد سفارش", max_length=24, unique=True)
    customer_name = models.CharField("نام تحویل‌گیرنده", max_length=150)
    phone = models.CharField("شماره موبایل", max_length=20)
    email = models.EmailField("ایمیل", blank=True)
    address = models.TextField("نشانی", blank=True)
    postal_code = models.CharField("کد پستی", max_length=20, blank=True)
    customer_note = models.TextField("یادداشت مشتری", blank=True)
    postal_tracking_code = models.CharField("کد رهگیری پستی", max_length=40, blank=True)
    shipping_method = models.CharField("روش ارسال", max_length=24, choices=SHIPPING)
    received_at = models.DateTimeField("تاریخ دریافت", null=True, blank=True)
    status = models.CharField("وضعیت", max_length=16, choices=STATUS, default="pending")
    subtotal = models.PositiveIntegerField("جمع کالا (تومان)")
    shipping_cost = models.PositiveIntegerField("هزینه ارسال (تومان)", default=0)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders", verbose_name="کد تخفیف")
    coupon_discount = models.PositiveIntegerField("مبلغ تخفیف (تومان)", default=0)
    wallet_amount = models.PositiveIntegerField("پرداخت از کیف پول (تومان)", default=0)
    stock_released = models.BooleanField("موجودی بازگردانده شده", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
    @property
    def total(self): return max(0, self.subtotal - self.coupon_discount) + self.shipping_cost
    @property
    def remaining_payment(self): return max(0, self.total - self.wallet_amount)
    def __str__(self): return self.tracking_code

class ShippingRate(models.Model):
    code = models.CharField("روش ارسال", max_length=24, choices=Order.SHIPPING, unique=True)
    price = models.PositiveIntegerField("هزینه (تومان)")
    per_kg_cost = models.PositiveIntegerField("هزینه هر کیلوگرم اضافه (تومان)", default=0)
    active = models.BooleanField("فعال", default=True)
    def __str__(self): return f"{self.get_code_display()} — {self.price} تومان"
    class Meta:
        verbose_name = "هزینه ارسال"
        verbose_name_plural = "هزینه‌های ارسال"
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    book = models.ForeignKey(Book, null=True, on_delete=models.SET_NULL)
    title_snapshot = models.CharField("عنوان کتاب", max_length=240)
    unit_price = models.PositiveIntegerField("قیمت واحد (تومان)")
    quantity = models.PositiveSmallIntegerField("تعداد")
    @property
    def line_total(self): return self.unit_price * self.quantity
    def __str__(self): return self.title_snapshot

class WalletTransaction(models.Model):
    KINDS = [("topup", "درخواست شارژ"), ("order_payment", "پرداخت سفارش"), ("refund", "بازگشت وجه سفارش"), ("adjustment", "اصلاح مدیریتی"), ("wheel_prize", "جایزهٔ گردونهٔ شانس")]
    DIRECTIONS = [("credit", "افزایش"), ("debit", "کاهش")]
    STATUSES = [("pending", "در انتظار بررسی"), ("posted", "ثبت‌شده"), ("rejected", "ردشده")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wallet_transactions", verbose_name="مشتری")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT, related_name="wallet_transactions", verbose_name="سفارش")
    kind = models.CharField("نوع گردش", max_length=20, choices=KINDS)
    direction = models.CharField("جهت", max_length=8, choices=DIRECTIONS)
    amount = models.PositiveIntegerField("مبلغ (تومان)", validators=[MinValueValidator(1)])
    status = models.CharField("وضعیت", max_length=10, choices=STATUSES, default="pending")
    note = models.CharField("توضیح", max_length=240, blank=True)
    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)
    processed_at = models.DateTimeField("تاریخ پردازش", null=True, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="processed_wallet_transactions", verbose_name="مدیر پردازش‌کننده")
    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["order", "kind"], condition=models.Q(order__isnull=False), name="unique_wallet_order_kind")]
        verbose_name = "گردش کیف پول"
        verbose_name_plural = "گردش‌های کیف پول"
    def __str__(self): return f"{self.get_kind_display()} — {self.amount:,} تومان"

class SupportTicket(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets")
    subject = models.CharField("موضوع", max_length=180)
    message = models.TextField("پیام")
    reply = models.TextField("پاسخ پشتیبانی", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed = models.BooleanField("بسته شده", default=False)
    def __str__(self): return self.subject
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تیکت پشتیبانی"
        verbose_name_plural = "تیکت‌های پشتیبانی"

class ReturnRequest(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="return_requests")
    reason = models.TextField("شرح مغایرت یا ایراد")
    created_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField("تأیید شده", default=False)
    def __str__(self): return f"مرجوعی {self.order}"
    class Meta:
        verbose_name = "درخواست مرجوعی"
        verbose_name_plural = "درخواست‌های مرجوعی"


class StoreSetting(models.Model):
    """تنظیمات فروشگاه — فقط یک رکورد (pk=1) نگهداری می‌شود."""
    announcement = models.CharField("اعلان نوار بالا", max_length=300, blank=True, help_text="خالی باشد نمایش داده نمی‌شود")
    kebab_per_10000 = models.PositiveSmallIntegerField("سیخ کباب به‌ازای هر ۱۰٬۰۰۰ تومان خرید", default=1)
    wheel_cooldown_days = models.PositiveSmallIntegerField("فاصلهٔ مجاز چرخش گردونه (روز)", default=3)
    free_shipping_threshold = models.PositiveIntegerField("سقف ارسال رایگان (تومان؛ ۰=غیرفعال)", default=0)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)
    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"
    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
    @classmethod
    def load(cls):
        obj = cls.objects.filter(pk=1).first()
        if obj is None:
            obj = cls(pk=1)
            obj.save()
        return obj
    def __str__(self): return "تنظیمات فروشگاه"


class KebabAccount(models.Model):
    """حساب امتیاز سیخ کباب هر مشتری."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kebab_account", verbose_name="مشتری")
    points = models.PositiveIntegerField("سیخ کباب فعلی", default=0)
    total_earned = models.PositiveIntegerField("مجموع کسب‌شده", default=0)
    last_spin_at = models.DateTimeField("آخرین چرخش گردونه", null=True, blank=True)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    class Meta:
        verbose_name = "حساب سیخ کباب"
        verbose_name_plural = "حساب‌های سیخ کباب"
    def __str__(self): return f"سیخ کباب {self.user} — {self.points}"


class WheelPrize(models.Model):
    KINDS = [("points", "سیخ کباب"), ("wallet", "اعتبار کیف پول"), ("none", "بدون جایزه")]
    label = models.CharField("برچسب روی گردونه", max_length=80)
    kind = models.CharField("نوع جایزه", max_length=10, choices=KINDS, default="none")
    amount = models.PositiveIntegerField("مقدار جایزه (سیخ یا تومان)", default=0)
    weight = models.PositiveSmallIntegerField("وزن شانس", default=10, help_text="احتمال نسبی؛ عدد بزرگ‌تر = شانس بیشتر")
    active = models.BooleanField("فعال", default=True)
    class Meta:
        ordering = ["pk"]
        verbose_name = "جایزهٔ گردونه"
        verbose_name_plural = "جوایز گردونهٔ شانس"
    def __str__(self): return self.label


class KebabLedger(models.Model):
    KINDS = [("purchase", "خرید سفارش"), ("wheel", "گردونهٔ شانس"), ("adjustment", "اصلاح مدیریتی")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="kebab_ledger", verbose_name="مشتری")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="kebab_entries", verbose_name="سفارش")
    kind = models.CharField("نوع", max_length=12, choices=KINDS)
    points_change = models.IntegerField("تغییر امتیاز (مثبت/منفی)")
    reason = models.CharField("توضیح", max_length=240, blank=True)
    created_at = models.DateTimeField("تاریخ", auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["order", "kind"], condition=models.Q(order__isnull=False) & models.Q(kind="purchase"), name="unique_kebab_per_order")]
        verbose_name = "گردش سیخ کباب"
        verbose_name_plural = "گردش‌های سیخ کباب"
    def __str__(self): return f"{self.get_kind_display()} {self.points_change:+d} — {self.user}"







