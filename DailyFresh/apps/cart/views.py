from django.shortcuts import render
from django.views.generic import View
from django.http import JsonResponse

from goods.models import GoodsSKU

from django_redis import get_redis_connection
from utils.mixin import LoginRequiredMixin


# Create your views here.
# get: 只涉及到获取数据
# post: 涉及数据的修改(新增，更新，删除)

# 采用ajax 请求
# 使用post 方式
# 前端需要传递的参数:商品id(sku_id) 商品数量(count)
# /cart/add


class CartAddView(View):
    '''购物车记录添加'''

    def post(self, request):
        '''添加记录'''
        # 获取user
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 接收参数
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 参数校验
        if not all([sku_id, count]):
            # 数据不完整
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验商品id
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 校验商品数量
        try:
            count = int(count)
        except Exception as e:
            # 商品数据不合法
            return JsonResponse({'res': 3, 'errmsg': '商品数目不合法'})

        if count <= 0:
            # 商品数据不合法
            return JsonResponse({'res': 3, 'errmsg': '商品数目不合法'})

        # 业务处理: 添加购物车记录
        # 先去redis中获取属性sku_id的值，如果有则商品的数目做累加，如果没有添加新属性
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        cart_count = conn.hget(cart_key, sku_id)

        if cart_count:
            # 商品数目累加
            count += int(cart_count)

        # 判断商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        # 设置购物车中sku_id对应的值
        conn.hset(cart_key, sku_id, count)

        # 获取用户购物车中商品的条目数
        cart_count = conn.hlen(cart_key)

        # 返回应答
        return JsonResponse({'res': 5, 'cart_count': cart_count, 'message': '添加成功'})


# /cart/
class CartInfoView(LoginRequiredMixin, View):
    '''购物车页面'''

    def get(self, request):
        '''显示'''
        # 获取user
        user = request.user

        # 获取redis中对应用户的购物车记录 cart_用户id: {'sku_id':商品数目}
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        cart_dict = conn.hgetall(cart_key)  # {'sku_id':商品数量}

        skus = []
        total_count = 0
        total_price = 0
        # 获取购物车中商品id对应的商品信息
        for sku_id, count in cart_dict.items():
            # 根据sku_id获取商品的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算商品的小计
            amount = sku.price * int(count)
            # 动态给sku对象增加属性amount和count, 分别保存商品的小计和购物车中商品的数量
            sku.amount = amount
            sku.count = count
            # 添加sku
            skus.append(sku)
            # 累加计算商品的总件数和总价格
            total_count += int(count)
            total_price += amount

        # 组织模板上下文
        context = {'total_count': total_count,
                   'total_price': total_price,
                   'skus': skus}

        # 使用模板
        return render(request, 'cart.html', context)


# /cart/update
# 采用ajax post请求
# 前端需要传递的参数:商品id(sku_id) 商品数量(count)
class CartUpdateView(View):
    '''购物车记录更新'''

    def post(self, request):
        '''更新'''
        # 获取user
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 接收参数
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 参数校验
        if not all([sku_id, count]):
            # 数据不完整
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验商品id
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 校验商品数量
        try:
            count = int(count)
        except Exception as e:
            # 商品数据不合法
            return JsonResponse({'res': 3, 'errmsg': '商品数目不合法'})

        if count <= 0:
            # 商品数据不合法
            return JsonResponse({'res': 3, 'errmsg': '商品数目不合法'})

        # 业务处理：购物车记录更新
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 判断商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        # 更新
        conn.hset(cart_key, sku_id, count)

        # 获取更新之后购物车商品的总件数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 5, 'total_count': total_count, 'message': '更新成功'})


# /cart/delete
# 采用ajax post请求
# 前端需要传递的参数:商品id(sku_id)
class CartDeleteView(View):
    '''购物车记录删除'''

    def post(self, request):
        '''记录删除'''
        # 获取user
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 接收参数
        sku_id = request.POST.get('sku_id')

        # 参数校验
        if not sku_id:
            # 数据不完整
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验商品id
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 业务处理: 删除购物车记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 删除redis中的记录
        conn.hdel(cart_key, sku_id)

        # 获取更新时候购物车商品的总件数
        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 3, 'total_count': total_count, 'message': '删除成功'})
