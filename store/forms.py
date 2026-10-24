from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Order, ReturnRequest, Review, SupportTicket, ShippingRate
from .utils import normalize_phone

class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="ایمیل", required=False)
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")
        labels = {"username": "نام کاربری"}

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "body")
        labels = {"rating": "امتیاز شما", "body": "دیدگاه"}
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}

class CheckoutForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rates = {rate.code: rate for rate in ShippingRate.objects.filter(active=True)}
        choices = []
        for code, label in Order.SHIPPING:
            rate = rates.get(code)
            if not rate:
                continue
            fee = f"{rate.price:,} تومان"
            if rate.per_kg_cost:
                fee += f" + {rate.per_kg_cost:,} تومان برای هر کیلوگرم اضافه"
            elif code in ("post_insured", "post_standard"):
                fee += " + هزینهٔ وزن (تعرفه در پنل تنظیم می‌شود)"
            choices.append((code, f"{label} — {fee}"))
        self.fields["shipping_method"].choices = choices

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("shipping_method")
        if method and method != "pickup" and not cleaned.get("address"):
            self.add_error("address", "برای ارسال، نشانی کامل لازم است.")
        if method in ("post_insured", "post_standard") and not cleaned.get("postal_code"):
            self.add_error("postal_code", "برای ارسال پستی کد پستی لازم است.")
        return cleaned
    class Meta:
        model = Order
        fields = ("customer_name", "phone", "email", "address", "postal_code", "customer_note", "shipping_method")
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "customer_note": forms.Textarea(attrs={"rows": 2, "placeholder": "مثلاً زمان مناسب تحویل یا توضیح برای سفارش"})}
        labels = {"customer_name":"نام و نام خانوادگی", "phone":"شماره موبایل", "email":"ایمیل (اختیاری)", "address":"نشانی کامل", "postal_code":"کد پستی", "customer_note":"یادداشت مشتری (اختیاری)", "shipping_method":"روش دریافت"}

class CheckoutExtrasForm(forms.Form):
    coupon_code = forms.CharField(label="کد تخفیف", max_length=40, required=False, widget=forms.TextInput(attrs={"placeholder": "کد تخفیف را وارد کنید", "autocomplete": "off"}))
    use_wallet = forms.BooleanField(label="استفاده از موجودی کیف پول", required=False)
    def clean_coupon_code(self):
        return self.cleaned_data["coupon_code"].strip().upper()

class WalletTopUpForm(forms.Form):
    amount = forms.IntegerField(label="مبلغ شارژ (تومان)", min_value=10000, max_value=50000000, widget=forms.NumberInput(attrs={"step": "10000", "placeholder": "مثلاً ۳۰۰۰۰۰"}))

class TicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ("subject", "message")
        labels = {"subject":"موضوع", "message":"متن پیام"}

class ReturnRequestForm(forms.ModelForm):
    tracking_code = forms.CharField(label="کد سفارش", max_length=24)
    phone = forms.CharField(label="شماره موبایل سفارش")
    class Meta:
        model = ReturnRequest
        fields = ("reason",)
        labels = {"reason":"شرح مغایرت یا ایراد"}
        widgets = {"reason": forms.Textarea(attrs={"rows": 4})}
