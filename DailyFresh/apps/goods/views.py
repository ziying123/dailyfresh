from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.core.paginator import Paginator
from django.views.generic import View
from django.core.cache import cache

from goods.models import GoodsSKU, GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner
from order.models import OrderGoods

from django_redis import get_redis_connection


# Create your views here.

# /index


class IndexView(View):
    '''首页'''

    def get(self, request):
        '''显示'''

        # 尝试获取缓存
        context = cache.get('index_page_data')

        if context is None:
            # 缓存不存在

            # 获取的分类信息
            types = GoodsType.objects.all()

            # 获取首页的轮播信息
            index_banner = IndexGoodsBanner.objects.all().order_by('index')

            # 获取首页的促销信息
            promotion_banner = IndexPromotionBanner.objects.all().order_by('index')

            # 获取首页分类商品展示信息
            for type in types:

                # 查询type类首页展示的文字信息
                title_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')

                # 查询type类首页分类展示的图片信息
                image_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')

                # 动态的给type对象增加两个属性
                type.title_banner = title_banner
                type.image_banner = image_banner

            # 组织模板信息
            context = {'types': types,
                       'index_banner': index_banner,
                       'promotion_banner': promotion_banner}

            # 设置缓存
            # 缓存名称 缓存数据  缓存过期时间 pickle
            cache.set('index_page_data', context, 3600)

        # 设置购物车的数量
        cart_count = 0

        # 获取user
        user = request.user

        # 判断是否登陆
        if user.is_authenticated():
            # 用户已经登陆， 获取购物车的条目数量

            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

        # 组织魔板上下文
        context.update(cart_count=cart_count)

        # 使用模板
        # HttpResponse类的实例对象
        return render(request, 'index.html', context)


# 商品id
# /goods/商品id
# /goods/100
# /goods/1
class DetailView(View):
    '''详情页面'''

    def get(self, request, sku_id):
        '''显示'''

        # 获取商品的信息
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 该商品不存在
            return redirect(reverse('goods:index'))

        # 获取商品的分类信息
        types = GoodsType.objects.all()

        # 获取商品的评论信息
        order_skus = OrderGoods.objects.filter(sku=sku).exclude(comment='').order_by('-update_time')

        # 获取和该商品同类型的另外两个商品
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[:2]

        # 获取和商品同一个spu其他规格的商品信息
        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=sku_id)

        # 设置购物车的数量为0
        cart_count = 0

        # 获取user
        user = request.user

        # 判读用户是否登陆
        if user.is_authenticated():

            # 获取购物车的数量
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

            # 添加到浏览记录
            history_key = 'history_%d' % user.id

            # 先尝试从redis列表中移除元素sku_id
            conn.lrem(history_key, 0, sku_id)

            # 把元素sku_id添加到redis列表的左侧
            conn.lpush(history_key, sku_id)

            # 只保留用户最新浏览的5个商品的id
            conn.ltrim(history_key, 0, 4)

        # 组织模板上下文
        context = {'sku': sku,
                   'types': types,
                   'order_skus': order_skus,
                   'new_skus': new_skus,
                   'same_spu_skus': same_spu_skus,
                   'cart_count': cart_count}

        # 使用模板
        return render(request, 'detail.html', context)


# 前端给后端传递参数方式:
# url传参数（捕获参数)
# get传参数
# post传参数

# 种类id 页码 排序方式
# /list/种类id/页码/排序方式
# /list?type_id=种类id&page=页码&sort=排序方式
# /list/种类id/页码?sort=排序方式
# restful api
# /list/7/
class ListView(View):
    '''列表页'''

    def get(self, request, type_id, page):
        '''显示'''

        try:
            type = GoodsType.objects.get(id=type_id)

        except GoodsType.DoesNotExist:

            # 没有分类信息，跳转到首页
            return redirect(reverse('goods:index'))

        # 获取分类信息
        types = GoodsType.objects.all()

        # 获取排序的方式 获取分类商品的信息
        sort = request.GET.get('sort', 'default')
        # sort=default 按照默认方式(id)进行排序
        # sort=price 按照商品价格(price)进行排序
        # sort=hot 按照商品销量(sales)进行排序

        if sort == 'price':
            skus = GoodsSKU.objects.filter(type=type).order_by('price')

        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')

        else:
            sort = 'default'
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        # 分页
        paginator = Paginator(skus, 1)

        # 处理页码
        page = int(page)

        if page <= 0 or page > paginator.num_pages:
            # 默认获取第1页的内容
            page = 1

        # 获取第page页的Page对象
        skus_page = paginator.page(page)

        # 处理页码列表
        # 1.总页数<5, 显示所有页码
        # 2.当前页是前3页，显示1-5页
        # 3.当前页是后3页，显示后5页
        # 4.其他情况，显示当前页的前2页，当前页，当前页的后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        # 获取分类的2个新品信息
        new_skus = GoodsSKU.objects.filter(type=type).order_by('-create_time')[:2]

        # 获取用户购物车中商品的数目
        cart_count = 0

        # 获取user
        user = request.user
        if user.is_authenticated():
            # 用户已登录，获取购物车商品的条目数
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

        # 组织模板上下文
        context = {'type': type,
                   'types': types,
                   'skus_page': skus_page,
                   'pages': pages,
                   'new_skus': new_skus,
                   'cart_count': cart_count,
                   'sort': sort}

        # 使用模板
        return render(request, 'list.html', context)
