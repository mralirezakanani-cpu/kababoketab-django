from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0005_supplier_source_reference_policy")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer_note",
            field=models.TextField(blank=True, verbose_name="یادداشت مشتری"),
        ),
    ]
