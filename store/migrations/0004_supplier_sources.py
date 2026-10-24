from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("store", "0003_book_weight_grams_order_postal_tracking_code_and_more")]

    operations = [
        migrations.CreateModel(
            name="SupplierSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, verbose_name="نام منبع")),
                ("slug", models.SlugField(allow_unicode=True, unique=True, verbose_name="شناسه")),
                ("feed_url", models.URLField(blank=True, verbose_name="نشانی فید محصول")),
                ("format", models.CharField(choices=[("json", "JSON"), ("csv", "CSV")], default="json", max_length=8, verbose_name="قالب فید")),
                ("enabled", models.BooleanField(default=False, verbose_name="فعال")),
                ("update_store_prices", models.BooleanField(default=False, verbose_name="اعمال قیمت روی فروشگاه")),
                ("token_env_var", models.CharField(blank=True, max_length=120, verbose_name="نام متغیر محیطی توکن")),
                ("last_sync_at", models.DateTimeField(blank=True, null=True, verbose_name="آخرین همگام‌سازی")),
                ("last_sync_status", models.CharField(blank=True, max_length=16, verbose_name="نتیجه آخرین همگام‌سازی")),
                ("last_sync_message", models.TextField(blank=True, verbose_name="گزارش آخرین همگام‌سازی")),
            ],
            options={"verbose_name": "منبع تأمین کتاب", "verbose_name_plural": "منابع تأمین کتاب", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="SupplierOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_isbn", models.CharField(max_length=32, verbose_name="شابک منبع")),
                ("regular_price", models.PositiveIntegerField(verbose_name="قیمت بدون تخفیف منبع (تومان)")),
                ("sale_price", models.PositiveIntegerField(blank=True, null=True, verbose_name="قیمت تخفیف‌خورده منبع (تومان)")),
                ("stock", models.PositiveIntegerField(default=0, verbose_name="موجودی منبع")),
                ("product_url", models.URLField(blank=True, verbose_name="صفحه محصول در منبع")),
                ("checked_at", models.DateTimeField(auto_now=True, verbose_name="آخرین بررسی")),
                ("book", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supplier_offers", to="store.book", verbose_name="کتاب")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="store.suppliersource", verbose_name="منبع")),
            ],
            options={"verbose_name": "قیمت و موجودی تأمین‌کننده", "verbose_name_plural": "قیمت‌ها و موجودی تأمین‌کننده‌ها", "ordering": ["source__name", "book__title"]},
        ),
        migrations.AddConstraint(model_name="supplieroffer", constraint=models.UniqueConstraint(fields=("source", "book"), name="unique_supplier_offer_per_book")),
    ]
