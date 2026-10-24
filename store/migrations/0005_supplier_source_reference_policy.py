from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0004_supplier_sources")]

    operations = [
        migrations.AlterField(model_name="suppliersource", name="update_store_prices", field=models.BooleanField(default=False, verbose_name="اجازهٔ اعمال قیمت و موجودی روی فروشگاه")),
        migrations.AddField(model_name="suppliersource", name="use_for_price", field=models.BooleanField(default=True, verbose_name="مرجع انتخاب قیمت")),
        migrations.AddField(model_name="suppliersource", name="use_for_stock", field=models.BooleanField(default=True, verbose_name="مرجع انتخاب موجودی")),
        migrations.AddField(model_name="suppliersource", name="priority", field=models.PositiveSmallIntegerField(default=100, verbose_name="اولویت در قیمت‌های برابر")),
        migrations.AddField(model_name="suppliersource", name="offer_ttl_hours", field=models.PositiveSmallIntegerField(default=24, verbose_name="اعتبار داده (ساعت)")),
    ]
