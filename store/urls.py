from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
urlpatterns = [
 path("",views.home,name="home"), path("books/",views.book_list,name="book_list"), path("shop/",views.book_list,name="shop"), path("product/<str:slug>/",views.book_detail,name="book_detail"),
 path("cart/",views.cart_detail,name="cart"), path("cart/add/<int:book_id>/",views.cart_add,name="cart_add"), path("cart/update/<int:book_id>/",views.cart_update,name="cart_update"), path("cart/remove/<int:book_id>/",views.cart_remove,name="cart_remove"), path("checkout/",views.checkout,name="checkout"),
 path("orders/track/",views.order_lookup,name="order_lookup"), path("orders/confirmation/",views.order_confirmation,name="order_confirmation"), path("blog/",views.article_list,name="article_list"), path("blog/<str:slug>/",views.article_detail,name="article_detail"),
 path("faq/",views.faq,name="faq"), path("about-us/",views.about,name="about"), path("contactus/",views.contact,name="contactus"), path("terms-and-conditions/",views.terms,name="terms"), path("privacy-policy/",views.privacy,name="privacy"), path("podcast/",views.podcast,name="podcast"), path("tracking/",views.postal_tracking,name="postal_tracking"),
 path("diamond/",views.diamond,name="diamond"), path("diamond-membership/",views.diamond,name="diamond_membership"), path("diamond/buy/<int:plan_id>/",views.buy_membership,name="buy_membership"), path("support/tickets/",views.ticket_list,name="tickets"),
 path("kebab/",views.kebab,name="kebab"), path("kebab/wheel/",views.wheel_spin,name="wheel_spin"),
 path("pledge/",views.pledge,name="pledge"), path("bank-accounts/",views.bank_accounts,name="bank_accounts"),
 path("shipping/",views.shipping_info,name="shipping_info"), path("returns/",views.return_policy,name="return_policy"), path("returns/request/",views.return_request,name="return_request"), path("contact/",views.contact,name="contact"),
 path("wallet/",views.wallet_view,name="wallet"), path("accounts/me/",views.account,name="account"), path("my-account/",views.account,name="my_account"), path("my-account/orders/",views.account,name="my_orders"), path("my-account/tickets/",views.ticket_list,name="my_tickets"), path("my-account/diamond/",views.account,name="my_diamond"), path("accounts/register/",views.register,name="register"), path("accounts/login/",auth_views.LoginView.as_view(template_name="registration/login.html"),name="login"), path("accounts/logout/",auth_views.LogoutView.as_view(),name="logout"),
]




