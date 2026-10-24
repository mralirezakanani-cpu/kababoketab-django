from django.contrib import admin
from django.urls import include, path
from store.admin import KababBookAdminSite

admin.site.__class__ = KababBookAdminSite
urlpatterns = [path("admin/", admin.site.urls), path("", include("store.urls"))]
