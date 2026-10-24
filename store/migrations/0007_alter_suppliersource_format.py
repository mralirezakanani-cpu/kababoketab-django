from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("store", "0006_order_customer_note")]

    operations = [
        migrations.AlterField(
            model_name="suppliersource",
            name="format",
            field=models.CharField(
                choices=[("json", "JSON"), ("csv", "CSV"), ("qoqnoosp_xlsx", "فایل رسمی محصولات ققنوس (ZIP/XLSX)")],
                default="json",
                max_length=16,
                verbose_name="قالب فید",
            ),
        ),
    ]
