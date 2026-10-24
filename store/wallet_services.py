from django.db import transaction
from django.utils import timezone

from .models import CouponRedemption, KebabAccount, KebabLedger, Order, StoreSetting, WalletAccount, WalletTransaction


@transaction.atomic
def process_wallet_transaction(transaction_id, actor, approve=True):
    entry = WalletTransaction.objects.select_for_update().select_related("user").get(pk=transaction_id)
    if entry.status != "pending" or entry.kind not in {"topup", "adjustment"}:
        return False
    wallet, _ = WalletAccount.objects.select_for_update().get_or_create(user=entry.user)
    if approve:
        if entry.direction == "debit" and wallet.balance < entry.amount:
            return False
        wallet.balance += entry.amount if entry.direction == "credit" else -entry.amount
        wallet.save(update_fields=["balance", "updated_at"])
        entry.status = "posted"
    else:
        entry.status = "rejected"
    entry.processed_at = timezone.now()
    entry.processed_by = actor
    entry.save(update_fields=["status", "processed_at", "processed_by"])
    return True


@transaction.atomic
def refund_order_wallet(order, actor=None):
    locked_order = Order.objects.select_for_update().select_related("user").get(pk=order.pk)
    if not locked_order.user_id or not locked_order.wallet_amount:
        return False
    if WalletTransaction.objects.filter(order=locked_order, kind="refund").exists():
        return False
    payment = WalletTransaction.objects.filter(order=locked_order, kind="order_payment", status="posted").first()
    if not payment:
        return False
    wallet, _ = WalletAccount.objects.select_for_update().get_or_create(user=locked_order.user)
    wallet.balance += payment.amount
    wallet.save(update_fields=["balance", "updated_at"])
    WalletTransaction.objects.create(
        user=locked_order.user,
        order=locked_order,
        kind="refund",
        direction="credit",
        amount=payment.amount,
        status="posted",
        note="بازگشت خودکار سهم پرداخت‌شده از کیف پول",
        processed_at=timezone.now(),
        processed_by=actor,
    )
    return True


def kebab_points_for_order(order):
    """سیخ کباب قابل کسب برای این سفارش بر اساس مبلغ کتاب‌ها (بدون ارسال)."""
    if not order.user_id:
        return 0
    rate = StoreSetting.load().kebab_per_10000
    if rate <= 0:
        return 0
    return max(0, (order.subtotal - order.coupon_discount) // 10000 * rate)


@transaction.atomic
def award_kebab_for_order(order, actor=None):
    """اعطای سیخ کباب سفارش پرداخت‌شده (فقط یک بار برای هر سفارش)."""
    if not order.user_id or order.status not in {"paid", "preparing", "shipped", "delivered"}:
        return False
    locked = Order.objects.select_for_update().get(pk=order.pk)
    points = kebab_points_for_order(locked)
    if points <= 0 or KebabLedger.objects.filter(order=locked, kind="purchase").exists():
        return False
    account = KebabAccount.objects.select_for_update().filter(user_id=locked.user_id).first()
    if account is None:
        account = KebabAccount(user_id=locked.user_id)
        account.save()
    account.points += points
    account.total_earned += points
    account.save(update_fields=["points", "total_earned"])
    KebabLedger.objects.create(
        user_id=locked.user_id, order=locked, kind="purchase", points_change=points,
        reason=f"خرید سفارش {locked.tracking_code}",
    )
    return True


@transaction.atomic
def revoke_kebab_for_order(order, actor=None):
    """بازگشت سیخ کباب سفارش در لغو/استرداد (فقط یک بار)."""
    if not order.user_id:
        return False
    locked = Order.objects.select_for_update().get(pk=order.pk)
    entry = KebabLedger.objects.filter(order=locked, kind="purchase").first()
    if not entry:
        return False
    account = KebabAccount.objects.select_for_update().filter(user_id=locked.user_id).first()
    if account:
        account.points = max(0, account.points - entry.points_change)
        account.save(update_fields=["points"])
    KebabLedger.objects.create(
        user_id=locked.user_id, order=locked, kind="adjustment", points_change=-entry.points_change,
        reason=f"لغو/استرداد سفارش {locked.tracking_code}",
    )
    return True


@transaction.atomic
def settle_order_discounts(order, status, actor=None):
    if status in {"cancelled", "refunded"}:
        refund_order_wallet(order, actor)
        revoke_kebab_for_order(order, actor)
        CouponRedemption.objects.filter(order=order, status__in=("reserved", "used")).update(status="released")
    elif status == "paid":
        CouponRedemption.objects.filter(order=order, status="reserved").update(status="used")
        award_kebab_for_order(order, actor)
