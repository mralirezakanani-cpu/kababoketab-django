"""ربات به‌روزرسانی روزانهٔ قیمت و موجودی از هر سه تأمین‌کننده.

اجرا:
    python manage.py run_daily_sync
    python manage.py run_daily_sync --apply --import-new
    python manage.py run_daily_sync --source cheshmehdis
گزارش در logs/daily_sync.log نوشته می‌شود. برای زمان‌بندی روزانه در ویندوز:
    powershell -File scripts\register_daily_task.ps1
"""
import datetime
import sys
import traceback
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand

LOG_DIR = Path("logs")


class Command(BaseCommand):
    help = "همگام‌سازی زمان‌بندی‌شدهٔ قیمت و موجودی از ققنوس، پخش چشمه و کتاب گستر"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", default=True, help="اعمال قیمت مرجع روی فروشگاه (پیش‌فرض فعال)")
        parser.add_argument("--no-apply", dest="apply", action="store_false", help="فقط ثبت پیشنهادها، بدون اعمال")
        parser.add_argument("--import-new", action="store_true", help="کتاب‌های جدید چشمه هم وارد شود")
        parser.add_argument("--sources", default="qoqnoosp,cheshmehdis,gbook", help="ترتیب منبع‌ها با ویرگول")

    def handle(self, *args, **options):
        LOG_DIR.mkdir(exist_ok=True)
        log_path = LOG_DIR / "daily_sync.log"

        class Tee:
            def __init__(self, stream):
                self.stream = stream
                self.file = open(log_path, "a", encoding="utf-8")

            def write(self, text):
                self.stream.write(text)
                self.file.write(text)

            def flush(self):
                self.stream.flush()
                self.file.flush()

            def isatty(self):
                return False

        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = Tee(stdout)
        started = datetime.datetime.now()
        self.stdout.write(f"\n===== شروع همگام‌سازی روزانه {started:%Y-%m-%d %H:%M:%S} =====")
        failed = []
        try:
            for slug in [s.strip() for s in options["sources"].split(",") if s.strip()]:
                self.stdout.write(f"--- منبع: {slug} ---")
                try:
                    kwargs = {"source": slug, "apply": options["apply"]}
                    if slug == "cheshmehdis" and options["import_new"]:
                        kwargs["import_new"] = True
                    call_command("sync_supplier_catalogs", **kwargs)
                except Exception as exc:
                    failed.append(slug)
                    self.stdout.write(f"خطا در {slug}: {exc}")
                    traceback.print_exc()
            self.stdout.write(f"===== پایان {datetime.datetime.now():%Y-%m-%d %H:%M:%S} — ناموفق: {failed or 'هیچ'} =====")
        finally:
            sys.stdout, sys.stderr = stdout, stderr
        if failed:
            raise SystemExit(1)
