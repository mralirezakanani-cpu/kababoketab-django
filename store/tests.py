"""تست‌های فروشگاه کباب و کتاب — هر بخش پس از تغییر باید سبز بماند."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import (
    Book, Category, Order, OrderItem, Publisher, Review, ShippingRate, StoreSetting,
    KebabAccount, KebabLedger, WalletAccount, WalletTransaction, WheelPrize, Coupon,
    Author,
)

User = get_user_model()


class SetupMixin:
    @classmethod
    def setUpTestData(cls):
        cls.settings_obj = StoreSetting.load()
        cls.settings_obj.kebab_per_10000 = 1
        cls.settings_obj.wheel_cooldown_days = 3
        cls.settings_obj.free_shipping_threshold = 0
        cls.settings_obj.save()
        cls.publisher = Publisher.objects.create(name="نشر آزمون", slug="test-pub")
        cls.author = Author.objects.create(name="نویسنده آزمون", slug="test-author")
        cls.category = Category.objects.create(name="رمان", slug="roman")
        cls.book = Book.objects.create(
            title="کتاب آزمون", slug="test-book", price=100_000, sale_price=90_000,
            stock=5, weight_grams=500, publisher=cls.publisher, author=cls.author,
            pages=200, publication_year=1400,
        )
        cls.book.categories.add(cls.category)
        cls.cheap = Book.objects.create(title="ارزان", slug="cheap-book", price=20_000, stock=10, publisher=cls.publisher)
        cls.cheap.categories.add(cls.category)
        cls.out = Book.objects.create(title="ناموجود", slug="out-book", price=50_000, stock=0)
        ShippingRate.objects.create(code="post_insured", price=60_000, per_kg_cost=10_000)
        ShippingRate.objects.create(code="pickup", price=0)
        cls.user = User.objects.create_user(username="buyer", password="pass-123456", first_name="خریدار", last_name="تستی")
        WalletAccount.objects.create(user=cls.user, balance=500_000)
        cls.kebab = KebabAccount.objects.create(user=cls.user)
        cls.prize_points = WheelPrize.objects.create(label="۵ سیخ", kind="points", amount=5, weight=100, active=True)
        cls.prize_none = WheelPrize.objects.create(label="شانس بعد", kind="none", amount=0, weight=1, active=True)

    def setUp(self):
        self.client = Client()


class PublicPagesTests(SetupMixin, TestCase):
    def test_home_ok(self):
        r = self.client.get(reverse("home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "کباب و کتاب")

    def test_book_list_sorts(self):
        for sort in ("popular", "cheap", "expensive", "rating", "newest"):
            r = self.client.get(reverse("book_list"), {"sort": sort})
            self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("book_list"), {"sort": "cheap"})
        books = list(r.context["books"])
        self.assertEqual(books[0].pk, self.cheap.pk)

    def test_book_list_filters(self):
        r = self.client.get(reverse("book_list"), {"category": self.category.slug})
        self.assertContains(r, "کتاب آزمون")
        r = self.client.get(reverse("book_list"), {"stock": "1"})
        self.assertNotContains(r, "out-book")
        r = self.client.get(reverse("book_list"), {"decade": "1400"})
        self.assertContains(r, "کتاب آزمون")
        r = self.client.get(reverse("book_list"), {"min_price": "50000", "max_price": "150000"})
        self.assertNotContains(r, "cheap-book")

    def test_book_detail_elements(self):
        r = self.client.get(self.book.get_absolute_url())
        self.assertContains(r, "گارانتی ۱۰ روزه")
        self.assertContains(r, "قیمت فعلی")

    def test_static_pages_ok(self):
        for name in ("kebab", "pledge", "bank_accounts", "faq", "about", "terms", "privacy", "shipping_info", "return_policy", "postal_tracking"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 200, name)

    def test_order_lookup_finds_order(self):
        Order.objects.create(tracking_code="ABC123", customer_name="م", phone="09120000000", shipping_method="pickup", subtotal=10_000)
        r = self.client.get(reverse("order_lookup"), {"code": "ABC123", "phone": "09120000000"})
        self.assertContains(r, "ABC123")


class CartTests(SetupMixin, TestCase):
    def test_add_update_remove(self):
        r = self.client.post(reverse("cart_add", args=[self.book.pk]), {"quantity": 2})
        self.assertEqual(self.client.session["cart"][str(self.book.pk)], 2)
        self.client.post(reverse("cart_update", args=[self.book.pk]), {"quantity": 1})
        self.assertEqual(self.client.session["cart"][str(self.book.pk)], 1)
        self.client.post(reverse("cart_remove", args=[self.book.pk]))
        self.assertNotIn(str(self.book.pk), self.client.session["cart"])

    def test_add_clamps_to_stock(self):
        r = self.client.post(reverse("cart_add", args=[self.book.pk]), {"quantity": 99})
        self.assertEqual(self.client.session["cart"][str(self.book.pk)], 5)

    def test_cannot_add_out_of_stock(self):
        self.client.post(reverse("cart_add", args=[self.out.pk]), {"quantity": 1})
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_stale_cart_lines_are_cleaned(self):
        s = self.client.session
        s["cart"] = {str(self.out.pk): 1, "999999": 2, str(self.book.pk): 99}
        s.save()
        r = self.client.get(reverse("cart"))
        self.assertEqual(self.client.session["cart"], {str(self.book.pk): 5})


class CheckoutTests(SetupMixin, TestCase):
    def _fill_cart(self):
        s = self.client.session
        s["cart"] = {str(self.book.pk): 2}
        s.save()

    def test_guest_order_pending(self):
        self._fill_cart()
        r = self.client.post(reverse("checkout"), {
            "customer_name": "مشتری مهمان", "phone": "09120000000",
            "address": "تهران", "postal_code": "1234567890", "shipping_method": "post_insured", "use_wallet": "",
        })
        self.assertRedirects(r, reverse("order_confirmation"))
        order = Order.objects.get(tracking_code=Order.objects.latest("pk").tracking_code)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.items.count(), 1)
        # 2 × 90,000 + 60,000 ارسال
        self.assertEqual(order.subtotal, 180_000)
        self.assertEqual(order.shipping_cost, 60_000)
        self.book.refresh_from_db()
        self.assertEqual(self.book.stock, 5)  # کسر موجودی هنگام پرداخت واقعی/تسویه انجام می‌شود

    def test_wallet_paid_order_awards_kebab(self):
        self.client.force_login(self.user)
        self._fill_cart()
        r = self.client.post(reverse("checkout"), {
            "customer_name": "خریدار تستی", "phone": "09120000000",
            "address": "تهران", "shipping_method": "pickup", "use_wallet": "on",
        })
        order = Order.objects.latest("pk")
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.wallet_amount, order.total)
        self.kebab.refresh_from_db()
        wallet = WalletAccount.objects.get(user=self.user)
        # ۱۸۰٬۰۰۰ تومان → ۱۸ سیخ
        self.assertEqual(self.kebab.points, 18)
        self.assertTrue(KebabLedger.objects.filter(order=order, kind="purchase").exists())
        self.assertEqual(wallet.balance, 500_000 - order.total)

    def test_percent_coupon_with_cap(self):
        Coupon.objects.create(code="SAVE10", discount_type="percent", value=50, maximum_discount=20_000, per_customer_limit=1)
        self._fill_cart()
        r = self.client.post(reverse("checkout"), {
            "customer_name": "م", "phone": "09120000000", "address": "تهران",
            "shipping_method": "pickup", "coupon_code": "SAVE10", "use_wallet": False,
        })
        order = Order.objects.latest("pk")
        self.assertEqual(order.coupon_discount, 20_000)  # سقف اعمال شد نه ۹۰٬۰۰۰

    def test_free_shipping_threshold(self):
        self.settings_obj.free_shipping_threshold = 150_000
        self.settings_obj.save()
        self._fill_cart()
        self.client.post(reverse("checkout"), {
            "customer_name": "م", "phone": "09120000000", "address": "تهران",
            "postal_code": "1234567890", "shipping_method": "post_insured", "use_wallet": "",
        })
        order = Order.objects.latest("pk")
        self.assertEqual(order.shipping_cost, 0)


class KebabWheelTests(SetupMixin, TestCase):
    def test_wheel_awards_points(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("wheel_spin"))
        self.assertRedirects(r, reverse("kebab"))
        self.kebab.refresh_from_db()
        self.assertEqual(self.kebab.points, 5)
        self.assertTrue(KebabLedger.objects.filter(kind="wheel").exists())

    def test_wheel_cooldown(self):
        self.client.force_login(self.user)
        self.client.post(reverse("wheel_spin"))
        self.kebab.refresh_from_db()
        self.kebab.last_spin_at = timezone.now()
        self.kebab.save()
        r = self.client.post(reverse("wheel_spin"), follow=True)
        messages = [str(m) for m in r.context["messages"]]
        self.assertTrue(any("نرسیده" in m for m in messages))

    def test_leaderboard_page(self):
        self.kebab.total_earned = 42
        self.kebab.save()
        r = self.client.get(reverse("kebab"))
        self.assertContains(r, "فعال‌ترین کاربران")

    def test_kebab_revoked_on_cancel(self):
        from .wallet_services import settle_order_discounts
        order = Order.objects.create(user=self.user, tracking_code="KEBAB1", customer_name="م", phone="09120000000", shipping_method="pickup", subtotal=100_000, status="paid")
        settle_order_discounts(order, "paid")
        self.kebab.refresh_from_db()
        self.assertEqual(self.kebab.points, 10)
        settle_order_discounts(order, "cancelled")
        self.kebab.refresh_from_db()
        self.assertEqual(self.kebab.points, 0)


class AuthTests(SetupMixin, TestCase):
    def test_register_login(self):
        r = self.client.post(reverse("register"), {"username": "newuser", "password1": "Strong-Pass-99", "password2": "Strong-Pass-99"})
        self.assertRedirects(r, reverse("home"))
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_review_requires_login_and_upsert(self):
        r = self.client.post(self.book.get_absolute_url(), {"rating": 5, "body": "عالی بود"})
        self.assertRedirects(r, reverse("login") + f"?next={self.book.get_absolute_url()}")
        self.client.force_login(self.user)
        self.client.post(self.book.get_absolute_url(), {"rating": 5, "body": "عالی بود"})
        self.client.post(self.book.get_absolute_url(), {"rating": 4, "body": "خوب بود"})
        self.assertEqual(Review.objects.filter(book=self.book, user=self.user).count(), 1)
        self.assertEqual(Review.objects.get(book=self.book, user=self.user).rating, 4)


class SecurityBaselineTests(SetupMixin, TestCase):
    def test_admin_requires_login(self):
        r = self.client.get("/admin/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    def test_wallet_page_requires_login(self):
        r = self.client.get(reverse("wallet"))
        self.assertEqual(r.status_code, 302)

    def test_xss_escaped_in_book_title(self):
        evil = Book.objects.create(title="<script>alert(1)</script>", slug="evil-book", price=1)
        r = self.client.get(evil.get_absolute_url())
        self.assertNotContains(r, "<script>alert(1)</script>")
        r = self.client.get(reverse("book_list"), {"q": "<script>"})
        self.assertEqual(r.status_code, 200)

    def test_order_lookup_without_match_shows_error(self):
        r = self.client.get(reverse("order_lookup"), {"code": "NOPE", "phone": "09120000000"})
        self.assertContains(r, "پیدا نشد")


class RateLimitAndSecurityTests(SetupMixin, TestCase):
    def test_rate_limit_blocks_after_threshold(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(15):
            r = self.client.post(reverse("login"), {"username": "x", "password": "y"})
        r = self.client.post(reverse("login"), {"username": "x", "password": "y"})
        self.assertEqual(r.status_code, 429)

    def test_rate_limit_not_applied_to_public_pages(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(6):
            r = self.client.get(reverse("home"))
        self.assertEqual(r.status_code, 200)

    def test_security_headers(self):
        r = self.client.get(reverse("home"))
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertTrue(r.headers.get("X-Content-Type-Options", "").lower() in ("nosniff", ""))

    def test_weak_password_rejected(self):
        r = self.client.post(reverse("register"), {"username": "weakpw", "password1": "1234567890", "password2": "1234567890"})
        form = r.context["form"]
        self.assertFalse(form.is_valid())
        self.assertTrue(any("عددی" in str(err) or "numeric" in str(err).lower() for errs in form.errors.values() for err in errs) or form.errors)
