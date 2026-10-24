@echo off
rem ربات روزانهٔ به‌روزرسانی قیمت و موجودی کباب و کتاب
cd /d "%~dp0.."
".venv\Scripts\python.exe" manage.py run_daily_sync --apply >> logs\scheduler.log 2>&1
