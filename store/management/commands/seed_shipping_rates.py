from django.core.management.base import BaseCommand
from store.models import ShippingRate

RATES = {
    "tehran_express": (450000, 0),
    "tehran_courier": (160000, 0),
    "post_insured": (191000, 0),
    "post_standard": (141000, 0),
    "freight": (300000, 0),
    "pickup": (40000, 0),
}

class Command(BaseCommand):
    help = "Set the published base shipping prices; configure per-kg fees in admin."

    def handle(self, *args, **options):
        for old, new in (("tehran_insured", "tehran_express"), ("alopeyk", "tehran_courier")):
            legacy = ShippingRate.objects.filter(code=old).first()
            if legacy:
                ShippingRate.objects.filter(code=new).delete()
                ShippingRate.objects.filter(pk=legacy.pk).update(code=new)
        for code, (price, per_kg) in RATES.items():
            ShippingRate.objects.update_or_create(code=code, defaults={"price": price, "active": True})
        self.stdout.write(self.style.SUCCESS("Six shipping methods and published base fees are ready."))
