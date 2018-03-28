from django.contrib import admin
from django.core.cache import cache
from goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner, GoodsSKU, GoodsImage, Goods
# Register your models here.


class BaseAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        '''数据更新或者新增时调用'''
        # 调用父类的方法，实现更新或新增操作
        super().save_model(request, obj, form, change)

        # 附加操作: 发出任务，重新生成静态首页
        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()

        # 附加操作: 更新缓存
        cache.delete('index_page_data')

    def delete_model(self, request, obj):
        '''数据删除时调用'''
        # 调用父类的方法，实现数据的删除操作
        super().delete_model(request, obj)

        # 附加操作: 发出任务，重新生成静态首页
        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()

        # 附加操作: 更新缓存
        cache.delete('index_page_data')


class GoodsTypeAdmin(BaseAdmin):
    pass


class IndexGoodsBannerAdmin(BaseAdmin):
    pass


class IndexPormotionBannerAdmin(BaseAdmin):
    pass


class GoodsSKUAdmin(BaseAdmin):

    pass


class GoodsAdmin(BaseAdmin):
    pass


class GoodsImageAdmin(BaseAdmin):
    pass


class IndexTypeGoodsBannerAdmin(BaseAdmin):
    pass


admin.site.register(GoodsType, GoodsTypeAdmin)
admin.site.register(GoodsSKU, GoodsSKUAdmin)
admin.site.register(Goods, GoodsAdmin)
admin.site.register(GoodsImage, GoodsImageAdmin)
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdmin)
admin.site.register(IndexPromotionBanner, IndexPormotionBannerAdmin)
admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBannerAdmin)

