from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.urls import path, reverse
from datetime import timedelta
from .models import Article, Author, Book, Category, Coupon, CouponRedemption, KebabAccount, KebabLedger, Membership, MembershipPlan, Order, OrderItem, PodcastEpisode, Publisher, ReturnRequest, Review, ShippingRate, StoreSetting, SupportTicket, SummaryTopic, SupplierOffer, SupplierSource, WalletAccount, WalletTransaction, WheelPrize
from .wallet_services import process_wallet_transaction, settle_order_discounts

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    change_list_template = "admin/store/book/change_list.html"
    list_display = ("title", "author", "publisher", "price", "sale_price", "stock", "weight_grams", "diamonds_reward", "is_featured")
    list_filter = ()
    def get_list_filter(self, request):
        return ()
    search_fields = ("title", "isbn", "code", "author__name")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("categories",)
    list_editable = ("price", "sale_price", "stock", "is_featured")
    list_per_page = 40
    inlines = []

class SupplierOfferInline(admin.TabularInline):
    model = SupplierOffer
    extra = 0
    can_delete = False
    fields = ("source", "source_isbn", "regular_price", "sale_price", "stock", "checked_at", "product_url")
    readonly_fields = fields
    show_change_link = True
    max_num = 0

BookAdmin.inlines = [SupplierOfferInline]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "premium", "published", "created_at")
    list_filter = ("premium", "published", "topics")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("topics",)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    change_form_template = "admin/store/order/change_form.html"
    list_display = ("tracking_code", "customer_name", "phone", "status", "postal_tracking_code", "created_at", "received_at")
    search_fields = ("tracking_code", "postal_tracking_code", "customer_name", "phone")
    list_filter = ("status", "shipping_method")
    list_per_page = 40
    readonly_fields = ("tracking_code", "created_at", "subtotal", "shipping_cost", "coupon_discount", "wallet_amount")
    fieldsets = (
        ("مشتری و دریافت", {"fields": ("user", "customer_name", "phone", "email", "address", "postal_code", "customer_note")}),
        ("وضعیت سفارش", {"fields": ("tracking_code", "status", "shipping_method", "postal_tracking_code", "received_at")}),
        ("مبالغ", {"fields": ("subtotal", "coupon", "coupon_discount", "wallet_amount", "shipping_cost")}),
        ("زمان", {"fields": ("created_at",)}),
    )
    inlines = []

    def save_model(self, request, obj, form, change):
        previous = Order.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if previous != obj.status:
                settle_order_discounts(obj, obj.status, request.user)

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("book", "title_snapshot", "unit_price", "quantity")
    max_num = 0

OrderAdmin.inlines = [OrderItemInline]

class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "user", "created_at", "closed")
    list_filter = ("closed", "created_at")
    search_fields = ("subject", "message", "reply", "user__username", "user__email")
    list_editable = ("closed",)
    readonly_fields = ("user", "subject", "message", "created_at")

class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("order", "created_at", "approved")
    list_filter = ("approved", "created_at")
    search_fields = ("order__tracking_code", "order__customer_name", "reason")
    list_editable = ("approved",)
    readonly_fields = ("order", "reason", "created_at")

for model in (Review, MembershipPlan, Membership, OrderItem, SummaryTopic, KebabLedger):
    admin.site.register(model)

@admin.register(KebabAccount)
class KebabAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "points", "total_earned", "last_spin_at", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = ("points", "total_earned", "last_spin_at")
    def has_add_permission(self, request): return False

@admin.register(WheelPrize)
class WheelPrizeAdmin(admin.ModelAdmin):
    list_display = ("label", "kind", "amount", "weight", "active")
    list_editable = ("amount", "weight", "active")
    list_filter = ("kind", "active")

@admin.register(StoreSetting)
class StoreSettingAdmin(admin.ModelAdmin):
    list_display = ("announcement", "kebab_per_10000", "wheel_cooldown_days", "free_shipping_threshold", "updated_at")
    fieldsets = (
        ("اعلان سایت", {"fields": ("announcement",), "description": "خالی باشد نمایش داده نمی‌شود"}),
        ("سیخ کباب و گردونه", {"fields": ("kebab_per_10000", "wheel_cooldown_days")}),
        ("روانشناسی فروش", {"fields": ("free_shipping_threshold",), "description": "خرید بالای این مبلغ، ارسال رایگان می‌گیرد؛ ۰ یعنی غیرفعال"}),
    )
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

admin.site.register(SupportTicket, SupportTicketAdmin)
admin.site.register(ReturnRequest, ReturnRequestAdmin)

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "value", "active", "starts_at", "expires_at", "usage_limit")
    list_filter = ("active", "discount_type")
    search_fields = ("code",)
    readonly_fields = ("created_at",)
    fieldsets = (
        ("تعریف کد", {"fields": ("code", "active", "discount_type", "value", "maximum_discount")} ),
        ("شرایط", {"fields": ("minimum_order", "starts_at", "expires_at", "usage_limit", "per_customer_limit")} ),
        ("زمان", {"fields": ("created_at",)}),
    )

@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "order", "user", "discount_amount", "status", "created_at")
    list_filter = ("status", "coupon")
    search_fields = ("coupon__code", "order__tracking_code", "phone", "email")
    readonly_fields = tuple(f.name for f in CouponRedemption._meta.fields)
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(WalletAccount)
class WalletAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "updated_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
    readonly_fields = ("user", "balance", "created_at", "updated_at")
    def has_add_permission(self, request): return False

@admin.action(description="تأیید درخواست شارژ انتخاب‌شده")
def approve_wallet_topups(modeladmin, request, queryset):
    count = sum(bool(process_wallet_transaction(entry.pk, request.user, approve=True)) for entry in queryset.filter(status="pending", kind="topup"))
    modeladmin.message_user(request, f"{count} درخواست شارژ تأیید شد.")

@admin.action(description="رد درخواست شارژ انتخاب‌شده")
def reject_wallet_topups(modeladmin, request, queryset):
    count = sum(bool(process_wallet_transaction(entry.pk, request.user, approve=False)) for entry in queryset.filter(status="pending", kind="topup"))
    modeladmin.message_user(request, f"{count} درخواست شارژ رد شد.")

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "direction", "amount", "status", "created_at", "processed_by")
    list_filter = ("kind", "direction", "status", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "order__tracking_code", "note")
    readonly_fields = tuple(f.name for f in WalletTransaction._meta.fields)
    actions = (approve_wallet_topups, reject_wallet_topups)
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(SupplierSource)
class SupplierSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "format", "enabled", "use_for_price", "use_for_stock", "update_store_prices", "priority", "last_sync_at", "last_sync_status")
    list_filter = ("enabled", "format", "update_store_prices", "use_for_price", "use_for_stock")
    search_fields = ("name", "slug", "feed_url")
    readonly_fields = ("last_sync_at", "last_sync_status", "last_sync_message")
    fieldsets = (
        ("مشخصات منبع", {"fields": ("name", "slug", "enabled")}),
        ("اتصال فید مجاز", {"fields": ("feed_url", "format", "token_env_var")}),
        ("سیاست مرجع", {"fields": ("use_for_price", "use_for_stock", "update_store_prices", "priority", "offer_ttl_hours")}),
        ("آخرین همگام‌سازی", {"fields": ("last_sync_at", "last_sync_status", "last_sync_message")}),
    )

@admin.register(SupplierOffer)
class SupplierOfferAdmin(admin.ModelAdmin):
    list_display = ("book", "source", "regular_price", "sale_price", "stock", "checked_at")
    list_filter = ("source",)
    search_fields = ("book__title", "book__isbn", "source_isbn")
    readonly_fields = ("checked_at",)
    list_per_page = 40

@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ("code", "price", "per_kg_cost", "active")
    list_editable = ("price", "per_kg_cost", "active")

@admin.register(PodcastEpisode)
class PodcastEpisodeAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "published", "created_at")
    list_filter = ("published", "topic")
    search_fields = ("title", "description")

admin.site.site_header = "مدیریت کباب و کتاب"
admin.site.site_title = "مدیریت فروشگاه"
admin.site.index_title = "مدیریت کتاب‌ها، سفارش‌ها و محتوا"

User = get_user_model()
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class StoreUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "is_staff", "is_active", "date_joined")
    search_fields = ("username", "first_name", "last_name", "email")
    list_filter = ("is_staff", "is_active", "date_joined")
    ordering = ("-date_joined",)

class KababBookAdminSite(admin.AdminSite):
    site_header = "مدیریت کباب و کتاب"
    site_title = "مدیریت فروشگاه"
    index_title = "داشبورد فروشگاه"

    def get_app_list(self, request, app_label=None):
        apps = super().get_app_list(request, app_label)
        sections = {
            "سفارش‌ها و پشتیبانی": {"Order", "SupportTicket", "ReturnRequest", "Review", "CouponRedemption"},
            "کتاب‌ها و محتوا": {"Book", "Category", "Publisher", "Author", "Article", "PodcastEpisode", "SummaryTopic"},
            "قیمت و تأمین‌کننده‌ها": {"SupplierSource", "SupplierOffer"},
            "مشتریان و امتیاز": {"WalletAccount", "WalletTransaction", "KebabAccount", "KebabLedger", "WheelPrize", "MembershipPlan", "Membership"},
            "پیکربندی فروشگاه": {"StoreSetting", "ShippingRate", "Coupon"},
        }
        sectioned = []
        used = set()
        for title, model_names in sections.items():
            models = []
            for app in apps:
                if app["app_label"] != "store":
                    continue
                for model in app["models"]:
                    if model["object_name"] in model_names:
                        models.append(model)
                        used.add(model["object_name"])
            if models:
                sectioned.append({"name": title, "app_label": "store", "app_url": "/admin/store/", "has_module_perms": True, "models": models})
        leftovers = []
        for app in apps:
            if app["app_label"] != "store":
                continue
            models = [m for m in app["models"] if m["object_name"] not in used]
            leftovers.extend(models)
        if leftovers:
            sectioned.append({"name": "سایر", "app_label": "store", "app_url": "/admin/store/", "has_module_perms": True, "models": leftovers})
        for app in apps:
            if app["app_label"] == "auth":
                app["name"] = "مدیران پنل"
                sectioned.append(app)
        return sectioned

    def get_urls(self):
        custom_urls = [
            path("store/", self.admin_view(self.index), name="store-dashboard"),
            path("store/customers/", self.admin_view(self.customer_list_view), name="store-customers"),
            path("store/orders/", self.admin_view(self.order_search_view), name="store-orders"),
            path("store/order/<int:order_id>/print/", self.admin_view(self.print_order_view), name="store-order-print"),
            path("store/customers/detail/", self.admin_view(self.customer_detail_view), name="store-customer-detail"),
            path("store/suppliers/sync/", self.admin_view(self.supplier_sync_view), name="store-supplier-sync"),
        ]
        return custom_urls + super().get_urls()

    def supplier_sync_view(self, request):
        """اجرای همگام‌سازی منبع از داخل پنل (صفحهٔ مدیریت قیمت)."""
        from django.core.management import call_command
        from .models import SupplierSource as SS

        if request.method == "POST" and request.user.has_perm("store.change_suppliersource"):
            slug = request.POST.get("source", "")
            apply_flag = request.POST.get("apply") == "on"
            try:
                call_command("sync_supplier_catalogs", source=slug if slug else None, apply=apply_flag)
                self.message_user(request, f"همگام‌سازی {slug or 'همهٔ منبع‌ها'} انجام شد.")
            except Exception as exc:
                self.message_user(request, f"خطا در همگام‌سازی: {exc}", level=messages.ERROR)
            return redirect(reverse("admin:store-supplier-sync"))
        sources = SS.objects.all().order_by("name")
        context = {
            **self.each_context(request), "title": "مدیریت قیمت و تأمین‌کننده‌ها",
            "sources": sources, "opts": SS._meta, "has_permission": True,
        }
        return TemplateResponse(request, "admin/store_suppliers.html", context)

    def customer_list_view(self, request):
        term = request.GET.get("q", "").strip()
        orders = Order.objects.select_related("user").order_by("-created_at")
        if term:
            orders = orders.filter(
                Q(customer_name__icontains=term) | Q(phone__icontains=term) |
                Q(email__icontains=term) | Q(user__username__icontains=term) |
                Q(user__first_name__icontains=term) | Q(user__last_name__icontains=term)
            )
        customers_by_phone = {}
        users_with_orders = set()
        for order in orders[:1000]:
            key = order.phone or f"order:{order.pk}"
            customer = customers_by_phone.setdefault(key, {
                "name": order.customer_name, "phone": order.phone, "email": order.email,
                "order_count": 0, "latest_order": order, "user": order.user,
            })
            customer["order_count"] += 1
            if not customer["email"] and order.email:
                customer["email"] = order.email
            if not customer["user"] and order.user:
                customer["user"] = order.user
            if order.user_id:
                users_with_orders.add(order.user_id)
        users = User.objects.filter(is_staff=False).order_by("-date_joined")
        if term:
            users = users.filter(
                Q(username__icontains=term) | Q(first_name__icontains=term) |
                Q(last_name__icontains=term) | Q(email__icontains=term)
            )
        for user in users[:1000]:
            if user.pk in users_with_orders:
                continue
            key = f"user:{user.pk}"
            customers_by_phone[key] = {
                "name": (user.get_full_name() or user.username), "phone": "",
                "email": user.email, "order_count": 0, "latest_order": None,
                "user": user, "user_id": user.pk,
            }
        customers = sorted(customers_by_phone.values(), key=lambda row: row["latest_order"].created_at if row["latest_order"] else row["user"].date_joined, reverse=True)
        page = Paginator(customers, 30).get_page(request.GET.get("page"))
        context = {
            **self.each_context(request), "title": "جست‌وجوی مشتریان",
            "query": term, "page_obj": page, "customers": page.object_list,
            "opts": Order._meta, "has_permission": True,
        }
        return TemplateResponse(request, "admin/store_customers.html", context)

    def order_search_view(self, request):
        term = request.GET.get("q", "").strip()
        start = parse_date(request.GET.get("from", ""))
        end = parse_date(request.GET.get("to", ""))
        orders = Order.objects.select_related("user").prefetch_related("items").order_by("-created_at")
        if term:
            orders = orders.filter(
                Q(tracking_code__icontains=term) | Q(phone__icontains=term) |
                Q(customer_name__icontains=term) | Q(user__username__icontains=term) |
                Q(user__first_name__icontains=term) | Q(user__last_name__icontains=term)
            )
        if start:
            orders = orders.filter(created_at__date__gte=start)
        if end:
            orders = orders.filter(created_at__date__lte=end)
        context = {
            **self.each_context(request), "title": "جست‌وجوی سفارش‌ها",
            "query": term, "start_date": request.GET.get("from", ""),
            "end_date": request.GET.get("to", ""), "orders": orders[:500],
            "opts": Order._meta, "has_permission": True,
        }
        return TemplateResponse(request, "admin/store_orders.html", context)

    def print_order_view(self, request, order_id):
        order = Order.objects.prefetch_related("items").get(pk=order_id)
        context = {
            **self.each_context(request), "title": f"چاپ سفارش {order.tracking_code}",
            "order": order, "items": order.items.all(),
        }
        return TemplateResponse(request, "admin/store_order_print.html", context)

    def customer_detail_view(self, request):
        phone = request.GET.get("phone", "").strip()
        user_id = request.GET.get("user_id", "").strip()
        account = User.objects.filter(pk=user_id, is_staff=False).first() if user_id.isdigit() else None
        orders = Order.objects.filter(user=account).select_related("user").prefetch_related("items").order_by("-created_at") if account else (Order.objects.filter(phone=phone).select_related("user").prefetch_related("items").order_by("-created_at") if phone else Order.objects.none())
        first_order = orders.first()
        user = account or (first_order.user if first_order else None)
        emails = sorted({email for email in orders.values_list("email", flat=True) if email})
        tickets = user.tickets.order_by("-created_at") if user else SupportTicket.objects.none()
        context = {
            **self.each_context(request), "title": "پرونده مشتری",
            "phone": phone, "first_order": first_order, "orders": orders,
            "emails": emails, "customer_user": user, "tickets": tickets,
            "opts": Order._meta, "has_permission": True,
        }
        return TemplateResponse(request, "admin/store_customer_detail.html", context)

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        now = timezone.now()
        month_ago = now - timedelta(days=30)
        paid_statuses = ("paid", "preparing", "shipped", "delivered")
        paid_orders = Order.objects.filter(status__in=paid_statuses, created_at__gte=month_ago)
        revenue = paid_orders.aggregate(v=Sum("subtotal"), n=Sum("coupon_discount"))
        extra_context["store_dashboard"] = {
            "pending_orders": Order.objects.filter(status="pending").count(),
            "open_tickets": SupportTicket.objects.filter(closed=False).count(),
            "returns_waiting": ReturnRequest.objects.filter(approved=False).count(),
            "reviews_count": Review.objects.count(),
            "pending_topups": WalletTransaction.objects.filter(kind="topup", status="pending").count(),
            "active_coupons": Coupon.objects.filter(active=True).count(),
            "recent_orders": Order.objects.prefetch_related("items").order_by("-created_at")[:10],
            "out_of_stock": Book.objects.filter(stock=0).count(),
            "low_stock": Book.objects.filter(stock__gt=0, stock__lte=3).count(),
            "month_orders": paid_orders.count(),
            "month_revenue": max(0, (revenue["v"] or 0) - (revenue["n"] or 0)),
            "suppliers": SupplierSource.objects.all().order_by("name"),
            "kebab_users": KebabAccount.objects.filter(points__gt=0).count(),
        }
        return super().index(request, extra_context)

admin.site.index_template = "admin/store_index.html"


