from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import CheckoutExtrasForm, CheckoutForm, RegisterForm, ReturnRequestForm, ReviewForm, TicketForm, WalletTopUpForm
from .models import Article, Book, Category, Coupon, CouponRedemption, KebabAccount, KebabLedger, Membership, MembershipPlan, Order, OrderItem, Publisher, Review, StoreSetting, SupportTicket, ReturnRequest, ShippingRate, SummaryTopic, WalletAccount, WalletTransaction, WheelPrize
from .utils import normalize_phone
from .wallet_services import award_kebab_for_order, settle_order_discounts
import secrets
import random
from datetime import timedelta

SORT_OPTIONS = {
    "newest": ("-created_at", "-pk"),
    "cheap": ("_current_price", "pk"),
    "expensive": ("-_current_price", "-pk"),    "popular": ("-sold_count", "-created_at", "-pk"),
    "rating": ("-avg_rating", "-created_at", "-pk"),
}

def home(request):
    bestsellers = Book.objects.annotate(sold_count=Sum("orderitem__quantity", filter=Q(orderitem__order__status__in=("paid", "preparing", "shipped", "delivered")))).filter(sold_count__gt=0).order_by("-sold_count", "title")[:8]
    publishers = (Publisher.objects.filter(books__stock__gt=0).annotate(book_count=Sum("books__stock")).distinct().order_by("-book_count", "name")[:6])
    publisher_rows = []
    for publisher in publishers:
        rows = (Book.objects.filter(publisher=publisher, stock__gt=0).order_by("-created_at")[:8])
        if rows:
            publisher_rows.append({"publisher": publisher, "books": rows})
    topics = SummaryTopic.objects.all()[:12]
    kebab_leaders = (KebabAccount.objects.select_related("user").filter(total_earned__gt=0).order_by("-total_earned", "-points")[:10])
    return render(request, "store/home.html", {
        "featured": Book.objects.filter(is_featured=True, stock__gt=0)[:8],
        "bestsellers": bestsellers,
        "newest": Book.objects.filter(stock__gt=0)[:8],
        "articles": Article.objects.filter(published=True)[:4],
        "free_summary": Article.objects.filter(published=True, premium=False).first(),
        "categories": Category.objects.filter(parent__isnull=True)[:8],
        "publisher_rows": publisher_rows,
        "topics": topics,
        "kebab_leaders": kebab_leaders,
        "settings": StoreSetting.load(),
    })

def book_list(request):
    books = Book.objects.select_related("author", "publisher").all()
    query = request.GET.get("q", "").strip(); category = request.GET.get("category", ""); publisher = request.GET.get("publisher", "")
    if query: books = books.filter(Q(title__icontains=query) | Q(author__name__icontains=query) | Q(translator__icontains=query) | Q(publisher__name__icontains=query) | Q(isbn__icontains=query))
    selected_obj = None
    if category:
        selected_obj = Category.objects.filter(pk=int(category)).first() if category.isdigit() else Category.objects.filter(slug=category).first()
        if selected_obj:
            category_ids = [selected_obj.pk] + list(selected_obj.children.values_list("pk", flat=True))
            books = books.filter(categories__id__in=category_ids)
    if publisher:
        books = books.filter(publisher_id=int(publisher)) if publisher.isdigit() else books.filter(publisher__slug=publisher)
    year = request.GET.get("year", "")
    decade = request.GET.get("decade", "")
    if year.isdigit() and 1200 <= int(year) <= 1405:
        books = books.filter(publication_year=int(year))
    elif decade.isdigit() and 1200 <= int(decade) <= 1400:
        books = books.filter(publication_year__gte=int(decade), publication_year__lte=int(decade) + 9)
    price_min = request.GET.get("min_price", "")
    price_max = request.GET.get("max_price", "")
    if price_min.isdigit() or price_max.isdigit() or request.GET.get("sort") in ("cheap", "expensive"):
        books = books.annotate(_current_price=Coalesce("sale_price", "price"))
    if price_min.isdigit(): books = books.filter(_current_price__gte=int(price_min))
    if price_max.isdigit(): books = books.filter(_current_price__lte=int(price_max))
    in_stock = request.GET.get("stock", "")
    if in_stock == "1": books = books.filter(stock__gt=0)
    if request.GET.get("discounted") == "1":
        books = books.filter(sale_price__isnull=False).exclude(sale_price=0)
    sort = request.GET.get("sort", "")
    if sort == "popular":
        books = books.annotate(sold_count=Sum("orderitem__quantity", filter=Q(orderitem__order__status__in=("paid", "preparing", "shipped", "delivered"))))
    elif sort == "rating":
        books = books.annotate(avg_rating=Avg("reviews__rating"))
    order_by = SORT_OPTIONS.get(sort, ("-created_at", "-pk"))
    books = books.order_by(*order_by)
    page_obj = Paginator(books.distinct(), 24).get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    years = Book.objects.filter(publication_year__gte=1200, publication_year__lte=1405).values_list("publication_year", flat=True).distinct().order_by("-publication_year")
    decades = sorted({(y // 10) * 10 for y in years}, reverse=True)
    root_categories = Category.objects.filter(parent__isnull=True)
    return render(request, "store/book_list.html", {"books": page_obj.object_list, "page_obj": page_obj, "query_string": query_params.urlencode(), "categories": root_categories, "publishers": Publisher.objects.all(), "years": years, "decades": decades, "query": query, "selected_category": category, "selected_category_obj": selected_obj, "selected_publisher": publisher, "selected_year": year, "selected_decade": decade, "selected_min_price": price_min, "selected_max_price": price_max, "in_stock": in_stock, "selected_sort": sort, "discounted": request.GET.get("discounted", "")})

def book_detail(request, slug):
    book = get_object_or_404(Book.objects.prefetch_related("categories", "reviews__user"), slug=slug)
    form = ReviewForm()
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.info(request, "برای ثبت دیدگاه ابتدا وارد شوید."); return redirect(f"/accounts/login/?next={book.get_absolute_url()}")
        form = ReviewForm(request.POST)
        if form.is_valid():
            Review.objects.update_or_create(book=book, user=request.user, defaults=form.cleaned_data)
            messages.success(request, "دیدگاه شما ثبت شد."); return redirect(book.get_absolute_url())
    related = Book.objects.filter(categories__in=book.categories.all(), stock__gt=0).exclude(pk=book.pk).distinct()[:4]
    if not related and book.publisher_id:
        related = Book.objects.filter(publisher=book.publisher, stock__gt=0).exclude(pk=book.pk)[:4]
    rating_avg = book.reviews.aggregate(v=Sum("rating"), n=Sum("rating", filter=Q(rating__gt=0)))
    rating_count = Review.objects.filter(book=book).count()
    rating_value = (rating_avg["v"] / rating_count) if rating_count and rating_avg["v"] else 0
    kebab_rate = StoreSetting.load().kebab_per_10000
    kebab_earn = book.current_price // 10000 * kebab_rate if kebab_rate else 0
    return render(request, "store/book_detail.html", {"book": book, "form": form, "related": related, "rating_avg": rating_value, "rating_floor": int(rating_value), "rating_count": rating_count, "kebab_earn": kebab_earn, "canonical_url": request.build_absolute_uri(book.get_absolute_url())})

def _cart_lines(request):
    cart = request.session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
        request.session["cart_notice"] = "سبد خرید نامعتبر بود و پاک شد."
    ids = [int(key) for key in cart if str(key).isdigit()]
    books = {book.pk: book for book in Book.objects.filter(pk__in=ids)}
    lines, total, clean_cart = [], 0, {}
    changed = False
    for key, amount in cart.items():
        if not str(key).isdigit() or int(key) not in books:
            changed = True
            continue
        book = books[int(key)]
        try:
            requested = int(amount)
        except (TypeError, ValueError):
            requested = 1
            changed = True
        if book.stock < 1:
            changed = True
            continue
        quantity = min(max(1, requested), book.stock)
        if str(quantity) != str(amount):
            changed = True
        clean_cart[str(book.pk)] = quantity
        line_total = quantity * book.current_price
        lines.append({"book": book, "quantity": quantity, "line_total": line_total})
        total += line_total
    if clean_cart != cart:
        changed = True
    request.session["cart"] = clean_cart
    if changed and "cart_notice" not in request.session:
        request.session["cart_notice"] = "تعداد سبد با موجودی فعلی هماهنگ شد؛ کتاب ناموجود از سبد کنار گذاشته شد."
    return lines, total

def cart_detail(request):
    lines, total = _cart_lines(request)
    notice = request.session.pop("cart_notice", None)
    if notice:
        messages.warning(request, notice)
    return render(request, "store/cart.html", {"lines": lines, "total": total})

@require_POST
def cart_add(request, book_id):
    book = get_object_or_404(Book, pk=book_id)
    cart = request.session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
    if book.stock < 1:
        messages.error(request, "این کتاب فعلاً موجود نیست.")
    else:
        try:
            requested = max(1, int(request.POST.get("quantity", 1)))
            existing = max(0, int(cart.get(str(book.pk), 0)))
        except (TypeError, ValueError):
            requested, existing = 1, 0
        cart[str(book.pk)] = min(existing + requested, book.stock)
        request.session["cart"] = cart
        messages.success(request, "کتاب به سبد خرید اضافه شد.")
    next_url = request.POST.get("next", "")
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("cart")

@require_POST
def cart_update(request, book_id):
    cart = request.session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
    book = get_object_or_404(Book, pk=book_id)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    if quantity < 1 or book.stock < 1:
        cart.pop(str(book_id), None)
        if book.stock < 1 and quantity > 0:
            messages.warning(request, "این کتاب ناموجود شده و از سبد خرید حذف شد.")
    else:
        cart[str(book_id)] = min(quantity, book.stock)
        if quantity > book.stock:
            messages.warning(request, f"تعداد «{book.title}» با موجودی فعلی به {book.stock} کاهش یافت.")
    request.session["cart"] = cart
    return redirect("cart")

@require_POST
def cart_remove(request, book_id):
    cart = request.session.get("cart", {})
    if isinstance(cart, dict):
        cart.pop(str(book_id), None)
    request.session["cart"] = cart
    return redirect("cart")

def checkout(request):
    lines, subtotal = _cart_lines(request)
    notice = request.session.pop("cart_notice", None)
    if notice:
        messages.warning(request, notice)
    if not lines:
        messages.info(request, "سبد خرید شما خالی است.")
        return redirect("book_list")
    store_settings = StoreSetting.load()
    initial = {
        "customer_name": request.user.get_full_name() if request.user.is_authenticated else "",
        "email": request.user.email if request.user.is_authenticated else "",
    }
    form = CheckoutForm(request.POST or None, initial=initial)
    extras_form = CheckoutExtrasForm(request.POST or None, initial={"use_wallet": request.user.is_authenticated})
    wallet = WalletAccount.objects.filter(user=request.user).first() if request.user.is_authenticated else None

    def render_checkout(discount=0):
        return render(request, "store/checkout.html", {
            "form": form, "extras_form": extras_form, "lines": lines, "subtotal": subtotal,
            "wallet_balance": wallet.balance if wallet else 0, "coupon_discount": discount,
        })

    if notice and request.method == "POST":
        form.add_error(None, "موجودی سبد به‌روز شد؛ لطفاً تعداد و مبلغ جدید را بررسی و دوباره ثبت سفارش را بزنید.")
        return render_checkout()
    if request.method == "POST" and form.is_valid() and extras_form.is_valid():
        discount = 0
        with transaction.atomic():
            cart = request.session.get("cart", {})
            cart_ids = [int(key) for key in cart if str(key).isdigit()]
            locked_books = {book.pk: book for book in Book.objects.select_for_update().filter(pk__in=cart_ids)}
            locked_lines, unavailable = [], []
            for key, raw_quantity in cart.items():
                if not str(key).isdigit() or int(key) not in locked_books:
                    unavailable.append("یکی از کتاب‌های سبد دیگر در فروشگاه موجود نیست.")
                    continue
                book = locked_books[int(key)]
                try:
                    quantity = int(raw_quantity)
                except (TypeError, ValueError):
                    quantity = 0
                if quantity < 1 or quantity > book.stock:
                    unavailable.append(f"موجودی «{book.title}» تغییر کرده است (موجودی فعلی: {book.stock}).")
                    continue
                locked_lines.append({"book": book, "quantity": quantity})
            if unavailable or not locked_lines:
                form.add_error(None, " ".join(unavailable) or "سبد خرید خالی است؛ لطفاً کتاب‌ها را دوباره انتخاب کنید.")
                return render_checkout()

            subtotal = sum(line["quantity"] * line["book"].current_price for line in locked_lines)
            coupon = None
            code = extras_form.cleaned_data["coupon_code"]
            if code:
                coupon = Coupon.objects.select_for_update().filter(code=code).first()
                now = timezone.now()
                coupon_error = None
                if not coupon or not coupon.active:
                    coupon_error = "این کد تخفیف معتبر یا فعال نیست."
                elif coupon.starts_at and now < coupon.starts_at:
                    coupon_error = "زمان استفاده از این کد تخفیف هنوز شروع نشده است."
                elif coupon.expires_at and now > coupon.expires_at:
                    coupon_error = "مهلت استفاده از این کد تخفیف تمام شده است."
                elif subtotal < coupon.minimum_order:
                    coupon_error = f"حداقل مبلغ کتاب‌ها برای این کد {coupon.minimum_order:,} تومان است."
                else:
                    redemptions = CouponRedemption.objects.filter(coupon=coupon, status__in=("reserved", "used"))
                    if coupon.usage_limit and redemptions.count() >= coupon.usage_limit:
                        coupon_error = "ظرفیت استفاده از این کد تخفیف تمام شده است."
                    else:
                        customer_uses = redemptions.filter(user=request.user).count() if request.user.is_authenticated else redemptions.filter(phone=form.cleaned_data["phone"]).count()
                        if customer_uses >= coupon.per_customer_limit:
                            coupon_error = "سقف استفادهٔ شما از این کد تخفیف تمام شده است."
                if coupon_error:
                    extras_form.add_error("coupon_code", coupon_error)
                    return render_checkout()
                if coupon.discount_type == "percent":
                    discount = subtotal * min(coupon.value, 100) // 100
                else:
                    discount = min(subtotal, coupon.value)
                if coupon.maximum_discount:
                    discount = min(discount, coupon.maximum_discount)

            order = form.save(commit=False)
            order.user = request.user if request.user.is_authenticated else None
            order.subtotal = subtotal
            order.coupon = coupon
            order.coupon_discount = discount
            order.tracking_code = secrets.token_hex(8).upper()
            rate = ShippingRate.objects.filter(code=order.shipping_method, active=True).first()
            if not rate:
                form.add_error("shipping_method", "هزینه این روش ارسال هنوز در سامانه تنظیم نشده است؛ لطفاً روش دیگری انتخاب کنید یا با پشتیبانی تماس بگیرید.")
                return render_checkout(discount)
            weight_grams = sum(line["book"].weight_grams * line["quantity"] for line in locked_lines)
            extra_kilos = max(0, (weight_grams - 1000 + 999) // 1000) if order.shipping_method in ("post_insured", "post_standard") else 0
            shipping_cost = rate.price + extra_kilos * rate.per_kg_cost
            discount_after = subtotal - discount
            if discount_after >= store_settings.free_shipping_threshold and store_settings.free_shipping_threshold > 0:
                shipping_cost = 0
                order.customer_note = (order.customer_note + "\n" if order.customer_note else "") + "ارسال رایگان (خرید بالای سقف تعیین‌شده)"
            order.shipping_cost = shipping_cost

            if request.user.is_authenticated and extras_form.cleaned_data["use_wallet"]:
                wallet = WalletAccount.objects.select_for_update().filter(user=request.user).first()
            wallet_available = wallet.balance if wallet else 0
            order.wallet_amount = min(wallet_available, max(0, order.total))
            order.status = "paid" if order.wallet_amount == order.total else "pending"
            order.save()
            for line in locked_lines:
                OrderItem.objects.create(order=order, book=line["book"], title_snapshot=line["book"].title, unit_price=line["book"].current_price, quantity=line["quantity"])
            if order.wallet_amount and wallet:
                wallet.balance -= order.wallet_amount
                wallet.save(update_fields=["balance", "updated_at"])
                WalletTransaction.objects.create(
                    user=request.user, order=order, kind="order_payment", direction="debit",
                    amount=order.wallet_amount, status="posted", note=f"پرداخت سفارش {order.tracking_code}",
                    processed_at=timezone.now(),
                )
            if coupon:
                CouponRedemption.objects.create(
                    coupon=coupon, order=order, user=order.user, phone=order.phone,
                    email=order.email, discount_amount=discount,
                    status="used" if order.status == "paid" else "reserved",
                )
            if order.status == "paid":
                award_kebab_for_order(order)
            # کسر موجودی رزروشدهٔ هر کتاب هنگام ثبت سفارش تا فروش بی‌از رخ ندهد
            for line in locked_lines:
                book = line["book"]
                book.stock = max(0, book.stock - line["quantity"])
            Book.objects.bulk_update([line["book"] for line in locked_lines], ["stock"], batch_size=100)

        request.session["cart"] = {}
        request.session["last_order_id"] = order.id
        if order.remaining_payment:
            messages.warning(request, "سفارش ثبت شد؛ ماندهٔ سفارش تا اتصال درگاه پرداخت در وضعیت در انتظار پرداخت می‌ماند.")
        else:
            messages.success(request, "سفارش با موجودی کیف پول و تخفیف ثبت و تسویه شد.")
        return redirect("order_confirmation")
    return render_checkout()

@login_required
def wallet_view(request):
    wallet, _ = WalletAccount.objects.get_or_create(user=request.user)
    form = WalletTopUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        amount = form.cleaned_data["amount"]
        WalletTransaction.objects.create(
            user=request.user, kind="topup", direction="credit", amount=amount,
            status="pending", note="درخواست شارژ؛ پس از اتصال درگاه یا تأیید واریز ثبت می‌شود.",
        )
        messages.info(request, "درخواست شارژ ثبت شد و پس از اتصال درگاه یا تأیید واریز توسط فروشگاه به موجودی اضافه می‌شود.")
        return redirect("wallet")
    transactions = WalletTransaction.objects.filter(user=request.user).select_related("order", "processed_by")[:30]
    return render(request, "store/wallet.html", {"wallet": wallet, "form": form, "transactions": transactions})

def order_confirmation(request):
    order_id=request.session.get("last_order_id")
    order=Order.objects.filter(pk=order_id).prefetch_related("items").first() if order_id else None
    return render(request,"store/order_confirmation.html",{"order":order})

def order_lookup(request):
    order=None; error=""
    code=request.GET.get("code","").strip().upper(); phone=normalize_phone(request.GET.get("phone", ""))
    if code and phone:
        order=Order.objects.filter(tracking_code=code,phone=phone).prefetch_related("items").first()
        if not order: error="سفارشی با این کد و شماره تماس پیدا نشد."
    return render(request,"store/order_lookup.html",{"order":order,"error":error})

def article_list(request):
    articles=Article.objects.filter(published=True).prefetch_related("topics")
    topic=request.GET.get("topic","")
    if topic.isdigit(): articles=articles.filter(topics__id=int(topic))
    from .models import SummaryTopic
    return render(request,"store/article_list.html",{"articles":articles.distinct(),"topics":SummaryTopic.objects.all(),"selected_topic":topic})
def _is_diamond(user): return user.is_authenticated and Membership.objects.filter(user=user,active=True,expires_at__gt=timezone.now()).exists()
def article_detail(request,slug):
    article=get_object_or_404(Article,slug=slug,published=True); locked=article.premium and not _is_diamond(request.user)
    return render(request,"store/article_detail.html",{"article":article,"locked":locked})

def diamond(request): return render(request,"store/diamond.html",{"plans":MembershipPlan.objects.filter(active=True)})

def faq(request):
    questions = [
        ("چطور بدون عضویت سفارش ثبت کنم؟", "کتاب‌ها را به سبد خرید اضافه کنید و در تسویه‌حساب، اطلاعات تماس و نشانی را وارد کنید؛ ساخت حساب کاربری الزامی نیست."),
        ("چه زمانی سفارش ارسال می‌شود؟", "آماده‌سازی معمولاً ۲ تا ۳ روز کاری زمان می‌برد. زمان نهایی ارسال به روش انتخابی و وضعیت موجودی بستگی دارد."),
        ("چطور موجودی کتاب را استعلام کنم؟", "برای استعلام موجودی و قیمت به‌روز از راه‌های تماس یا تیکت پشتیبانی استفاده کنید."),
        ("شرایط مرجوعی چیست؟", "برای مغایرت یا عیب فیزیکی کتاب، حداکثر تا ۱۰ روز پس از دریافت سفارش درخواست مرجوعی ثبت کنید."),
        ("عضویت الماسی چه دسترسی‌ای می‌دهد؟", "اشتراک فعال، دسترسی به خلاصه‌های ویژهٔ کتاب‌های غیرداستانی را فراهم می‌کند؛ خلاصه‌های رایگان نیز برای همه در دسترس‌اند."),
        ("پرداخت آنلاین فعال است؟", "ثبت سفارش در این نسخه فعال است؛ برای پرداخت آنلاین باید درگاه رسمی فروشگاه پیکربندی شود."),
    ]
    return render(request, "store/faq.html", {"questions": questions})

def about(request): return render(request, "store/about.html")
def terms(request): return render(request, "store/terms.html")
def privacy(request): return render(request, "store/privacy.html")
def podcast(request):
    from .models import PodcastEpisode, SummaryTopic
    return render(request, "store/podcast.html", {"topics": SummaryTopic.objects.all(), "episodes": PodcastEpisode.objects.filter(published=True).select_related("topic")})

def postal_tracking(request):
    order = None
    code = request.GET.get("code", "").strip()
    if code:
        order = Order.objects.filter(postal_tracking_code__iexact=code).first()
    return render(request, "store/postal_tracking.html", {"order": order, "code": code})

@login_required
def buy_membership(request,plan_id):
    if request.method!="POST": return redirect("diamond")
    plan=get_object_or_404(MembershipPlan,pk=plan_id,active=True)
    messages.info(request,f"پلن {plan.title} انتخاب شد. برای فعال‌سازی، درگاه پرداخت فروشگاه باید پیکربندی شود.")
    return redirect("diamond")

@login_required
def ticket_list(request):
    form=TicketForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        ticket=form.save(commit=False); ticket.user=request.user; ticket.save(); messages.success(request,"تیکت شما ثبت شد."); return redirect("tickets")
    return render(request,"store/tickets.html",{"tickets":SupportTicket.objects.filter(user=request.user),"form":form})

def return_policy(request): return render(request,"store/return_policy.html")
def return_request(request):
    form=ReturnRequestForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        order=Order.objects.filter(tracking_code=form.cleaned_data["tracking_code"].strip().upper(),phone=normalize_phone(form.cleaned_data["phone"])).first()
        if not order:
            form.add_error(None,"سفارشی با این کد و شماره موبایل پیدا نشد.")
        elif order.received_at and (timezone.now()-order.received_at).days>10:
            form.add_error(None,"مهلت ثبت درخواست مرجوعی (۱۰ روز پس از ثبت) گذشته است.")
        else:
            ReturnRequest.objects.create(order=order,reason=form.cleaned_data["reason"])
            messages.success(request,"درخواست مرجوعی ثبت شد تا پشتیبانی بررسی کند.")
            return redirect("return_request")
    return render(request,"store/return_request.html",{"form":form})

def shipping_info(request): return render(request,"store/shipping.html")
def contact(request): return render(request,"store/contact.html")
@login_required
def account(request):
    orders=Order.objects.filter(user=request.user).prefetch_related("items")
    memberships=Membership.objects.filter(user=request.user).select_related("plan").order_by("-expires_at")
    wallet, _ = WalletAccount.objects.get_or_create(user=request.user)
    return render(request,"store/account.html",{"orders":orders,"memberships":memberships,"wallet":wallet,"now":timezone.now()})
def register(request):
    form=RegisterForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        user=form.save(); login(request,user); messages.success(request,"حساب شما ساخته شد."); return redirect("home")
    return render(request,"registration/register.html",{"form":form})


def _kebab_context(request):
    settings_obj = StoreSetting.load()
    account = None
    if request.user.is_authenticated:
        account, _ = KebabAccount.objects.get_or_create(user=request.user)
    prizes = list(WheelPrize.objects.filter(active=True))
    cooldown_ok = True
    next_spin_at = None
    if account and account.last_spin_at and settings_obj.wheel_cooldown_days > 0:
        next_spin_at = account.last_spin_at + timedelta(days=settings_obj.wheel_cooldown_days)
        cooldown_ok = timezone.now() >= next_spin_at
    leaders = KebabAccount.objects.select_related("user").filter(total_earned__gt=0).order_by("-total_earned", "-points")[:20]
    ledger = KebabLedger.objects.filter(user=request.user).select_related("order")[:20] if request.user.is_authenticated else KebabLedger.objects.none()
    return {
        "kebab_account": account, "prizes": prizes, "cooldown_ok": cooldown_ok,
        "next_spin_at": next_spin_at, "kebab_settings": settings_obj,
        "leaders": leaders, "ledger": ledger,
    }


def kebab(request):
    """صفحهٔ «سیخ کباب‌های من»: امتیاز، گردونهٔ شانس و فعال‌ترین کاربران."""
    return render(request, "store/kebab.html", _kebab_context(request))


@login_required
@require_POST
def wheel_spin(request):
    """چرخش گردونهٔ شانس با کنترل فاصلهٔ زمانی و جایزهٔ وزنی."""
    context = _kebab_context(request)
    if not context["prizes"]:
        messages.info(request, "فعلاً جایزه‌ای برای گردونه تعریف نشده است؛ بعداً دوباره سر بزنید.")
        return redirect("kebab")
    if not context["cooldown_ok"]:
        messages.warning(request, "هنوز زمان چرخش بعدی شما نرسیده است؛ کمی صبر کنید.")
        return redirect("kebab")
    prizes = context["prizes"]
    total_weight = sum(prize.weight for prize in prizes) or 1
    ticket = random.randrange(1, total_weight + 1)
    chosen = None
    for prize in prizes:
        ticket -= prize.weight
        if ticket <= 0:
            chosen = prize
            break
    chosen = chosen or prizes[-1]
    account = KebabAccount.objects.select_for_update().filter(user=request.user).first()
    if account is None:
        account = KebabAccount(user=request.user)
        account.save()
    account.last_spin_at = timezone.now()
    result_text = ""
    if chosen.kind == "points" and chosen.amount > 0:
        account.points += chosen.amount
        account.total_earned += chosen.amount
        KebabLedger.objects.create(user=request.user, kind="wheel", points_change=chosen.amount, reason=f"جایزهٔ گردونهٔ شانس: {chosen.label}")
        result_text = f"تبریک! {chosen.amount:,} سیخ کباب بردید."
    elif chosen.kind == "wallet" and chosen.amount > 0:
        wallet, _ = WalletAccount.objects.get_or_create(user=request.user)
        wallet.balance += chosen.amount
        wallet.save(update_fields=["balance", "updated_at"])
        WalletTransaction.objects.create(
            user=request.user, kind="wheel_prize", direction="credit", amount=chosen.amount,
            status="posted", note=f"جایزهٔ گردونهٔ شانس: {chosen.label}", processed_at=timezone.now(),
        )
        result_text = f"تبریک! {chosen.amount:,} تومان اعتبار کیف پول بردید."
    else:
        result_text = "این بار جایزه‌ای نصیبتان نشد؛ دفعهٔ بعد شانس با شماست!"
    account.save()
    messages.success(request, result_text)
    return redirect("kebab")


def pledge(request):
    return render(request, "store/pledge.html")


def bank_accounts(request):
    accounts = [
        {"bank": "بانک ملت", "owner": "کتابفروشی کباب و کتاب", "number": "—", "sheba": "—"},
        {"bank": "بانک صادرات", "owner": "کتابفروشی کباب و کتاب", "number": "—", "sheba": "—"},
    ]
    return render(request, "store/bank_accounts.html", {"accounts": accounts})













@require_POST
@login_required
def mock_payment(request, tracking_code):
    """درگاه پرداخت آزمایشی (توسعه) — سفارش در انتظار پرداخت را تسویه می‌کند.

    فقط وقتی settings.MOCK_PAYMENTS فعال است کار می‌کند؛ در production غیرفعال شود.
    """
    if not getattr(settings, "MOCK_PAYMENTS", False):
        messages.error(request, "پرداخت آزمایشی در این محیط غیرفعال است.")
        return redirect("home")
    order = get_object_or_404(Order, tracking_code=tracking_code.strip().upper(), user=request.user)
    if order.status != "pending":
        messages.info(request, "این سفارش قابل پرداخت آزمایشی نیست.")
        return redirect("order_confirmation")
    with transaction.atomic():
        order.status = "paid"
        order.save(update_fields=["status"])
        settle_order_discounts(order, order.status)
    messages.success(request, f"پرداخت آزمایشی سفارش {order.tracking_code} انجام شد.")
    return redirect("order_confirmation")


def robots(request):
    return render(request, "store/robots.txt", content_type="text/plain; charset=utf-8")
