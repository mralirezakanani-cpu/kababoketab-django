from django.contrib.sitemaps import Sitemap

from .models import Article, Book, Category


class BookSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Book.objects.all()

    def lastmod(self, obj):
        return obj.created_at

    def location(self, obj):
        return obj.get_absolute_url()


class ArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Article.objects.filter(published=True)

    def lastmod(self, obj):
        return obj.created_at


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return Category.objects.all()

    def location(self, obj):
        return f"/books/?category={obj.slug}"


sitemaps = {"books": BookSitemap, "articles": ArticleSitemap, "categories": CategorySitemap}
