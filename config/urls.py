from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from store.admin import KababBookAdminSite
from store.sitemaps import sitemaps

admin.site.__class__ = KababBookAdminSite
urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="django.contrib.sitemaps.views.sitemap"),
    path("", include("store.urls")),
]
