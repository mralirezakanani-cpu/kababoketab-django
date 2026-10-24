from .models import Book, Category, StoreSetting, SummaryTopic


def cart_summary(request):
    cart=request.session.get("cart",{}); ids=[int(k) for k in cart if str(k).isdigit()]
    books={b.id:b for b in Book.objects.filter(id__in=ids)} if ids else {}; count=total=0
    for key,amount in cart.items():
        book=books.get(int(key)) if str(key).isdigit() else None
        if book:
            quantity=max(1,min(int(amount),book.stock or 1)); count+=quantity; total+=quantity*book.current_price
    return {"cart_count":count,"cart_total":total}


def site_context(request):
    """داده‌های مشترک هدر/فوتر و تنظیمات فروشگاه."""
    settings_obj = StoreSetting.load()
    return {
        "footer_categories": Category.objects.filter(parent__isnull=True).order_by("name")[:8],
        "footer_topics": SummaryTopic.objects.all()[:8],
        "store_settings": settings_obj,
    }
