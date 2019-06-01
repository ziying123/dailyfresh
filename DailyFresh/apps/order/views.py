from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from django.db import transaction
from django.conf import settings
from django.http import JsonResponse

from user.models import Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods

from utils.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
from alipay import AliPay
from datetime import datetime
import os


# Create your views here.
a = 123

# /order/place
class OrderPlaceView(LoginRequiredMixin, View):
    '''提交订单页面显示'''

    def post(self, request):
        '''显示'''
        # 获取参数
        sku_ids = request.POST.getlist('sku_ids')  # [2,5] # 2,5

        # 参数校验
        if not all(sku_ids):
            # 参数不完整，跳转到购物车页面
            return redirect(reverse('cart:show'))

        # 业务处理
        # 获取用户的收货地址信息
        user = request.user
        addrs = Address.objects.filter(user=user)

        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        skus = []
        total_count = 0
        total_price = 0
        # 遍历获取用户要购买的商品的信息
        for sku_id in sku_ids:
            # 根据sku_id获取商品信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取用户所要购买的商品的数量
            count = conn.hget(cart_key, sku_id)
            # 计算商品的小计
            amount = sku.price * int(count)
            # 动态给sku对象增加属性amount和count, 分别保存商品的小计和商品的数量
            sku.amount = amount
            sku.count = count
            # 添加sku
            skus.append(sku)
            # 累加计算所要购买商品的总件数和总金额
            total_count += int(count)
            total_price += amount

        # 运费：运费的子系统
        transit_price = 10

        # 实付款
        total_pay = total_price + transit_price

        # 组织上下文
        sku_ids = ','.join(sku_ids)
        context = {'addrs': addrs,
                   'skus': skus,
                   'total_count': total_count,
                   'total_price': total_price,
                   'transit_price': transit_price,
                   'total_pay': total_pay,
                   'sku_ids': sku_ids}

        # 使用模板
        return render(request, 'place_order.html', context)


# /order/commit
# 采用ajax post请求
# 前端传递的参数：收货地址id（addr_id)  支付方式(pay_method) 用户要购买的商品的id(sku_ids)
class OrderCommitView1(View):
    '''订单创建'''

    @transaction.atomic
    def post(self, request):
        '''订单创建'''
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 参数校验
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验地址信息
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 2, 'errmsg': '地址信息错误'})

        # 校验支付的方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            # 支付方式非法
            return JsonResponse({'res': 3, 'errmsg': '非法的支付方式'})

        # 业务处理:订单创建
        # 组织参数
        # 订单id(order_id): 20171211182130+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 订单中商品的总数目和总价格
        total_count = 0
        total_price = 0

        # 设置保存点
        sid = transaction.savepoint()

        try:
            # todo: 需要向df_order_info添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)

            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            # todo: 用户的订单中包含几个商品，应该向df_order_goods中添加几条记录
            sku_ids = sku_ids.split(',')  # [2,5]
            for sku_id in sku_ids:
                # 根据sku_id获取商品的信息
                try:
                    # select * from df_goods_sku where id=sku_id;
                    # sku = GoodsSKU.objects.get(id=sku_id)
                    # select * from df_goods_sku where id=sku_id for update;
                    print('user:%d try get lock' % user.id)
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                    print('user:%d get lock' % user.id)
                except GoodsSKU.DoesNotExist:
                    transaction.savepoint_rollback(sid)
                    return JsonResponse({'res': 4, 'errmsg': '商品信息错误'})

                # 获取用户要购买的商品的数目
                count = conn.hget(cart_key, sku_id)

                # 判断商品的库存
                if int(count) > sku.stock:
                    transaction.savepoint_rollback(sid)
                    return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                import time
                time.sleep(10)
                # todo: 向df_order_goods中添加1条记录
                OrderGoods.objects.create(order=order,
                                          sku=sku,
                                          count=count,
                                          price=sku.price)

                # todo: 减少商品的库存，增加销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                # todo: 累加计算商品的总件数和总价格
                total_count += int(count)
                total_price += sku.price * int(count)

            # todo: 更新order中订单商品的总件数和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(sid)
            return JsonResponse({'res': 7, 'errmsg': '下单失败'})

        # 释放保存点
        transaction.savepoint_commit(sid)

        # todo: 删除购物车中的对应记录
        conn.hdel(cart_key, *sku_ids)  # hdel(cart_key, 2, 5)

        # 返回应答
        return JsonResponse({'res': 5, 'message': '订单创建成功'})


# /order/commit
# 前端传递的参数用户收货地址，支付方式，用户购买的商品id
class OrderCommitView(View):
    '''订单创建'''

    @transaction.atomic
    def post(self, request):
        '''订单创建'''
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 参数校验
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验地址信息
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res': 2, 'errmsg': '地址信息错误'})

        # 校验支付的方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            # 支付方式非法
            return JsonResponse({'res': 3, 'errmsg': '非法的支付方式'})

        # 业务处理:订单创建
        # 组织参数
        # 订单id(order_id): 20171211182130+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 订单中商品的总数目和总价格
        total_count = 0
        total_price = 0

        # 设置保存点
        sid = transaction.savepoint()

        try:
            # todo: 需要向df_order_info添加一条记录
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)

            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            # todo: 用户的订单中包含几个商品，应该向df_order_goods中添加几条记录
            sku_ids = sku_ids.split(',')  # [2,5]
            for sku_id in sku_ids:
                for i in range(3):
                    # 根据sku_id获取商品的信息
                    try:
                        # select * from df_goods_sku where id=sku_id;
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist:
                        transaction.savepoint_rollback(sid)
                        return JsonResponse({'res': 4, 'errmsg': '商品信息错误'})

                    # 获取用户要购买的商品的数目
                    count = conn.hget(cart_key, sku_id)

                    # 判断商品的库存
                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(sid)
                        return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                    # todo: 减少商品的库存，增加销量
                    origin_stock = sku.stock
                    new_stock = origin_stock - int(count)
                    new_sales = sku.sales + int(count)
                    # print('user:%d times:%d stock:%d'%(user.id, i, origin_stock))
                    # import time
                    # time.sleep(10)
                    # update df_goods_sku set stock = new_stock, sales = new_sales
                    # where id = sku_id and stock = origin_stock
                    # 返回更新的行数
                    res = GoodsSKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock,
                                                                                        sales=new_sales)
                    if res == 0:
                        # 更新失败
                        if i == 2:
                            # 尝试了3次，更新仍然失败
                            transaction.savepoint_rollback(sid)
                            return JsonResponse({'res': 7, 'errmsg': '订单错误2'})
                        continue

                    # todo: 向df_order_goods中添加1条记录
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)

                    # todo: 累加计算商品的总件数和总价格
                    total_count += int(count)
                    total_price += sku.price * int(count)

                    # 更新成功之后跳转循环
                    break

            # todo: 更新order中订单商品的总件数和总价格
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(sid)
            return JsonResponse({'res': 7, 'errmsg': '下单失败'})

        # 释放保存点
        transaction.savepoint_commit(sid)

        # todo: 删除购物车中的对应记录
        conn.hdel(cart_key, *sku_ids)  # hdel(cart_key, 2, 5)

        # 返回应答
        return JsonResponse({'res': 5, 'message': '订单创建成功'})


# /order/pay
# 采用ajax post请求
# 前端传递的参数：订单id（order_id)
class OrderPayView(View):
    '''订单支付'''

    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '订单id不完整'})

        # 获取订单信息
        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)

        except OrderInfo.DoesNotExist:
            # 订单信息错误
            return JsonResponse({'res': 2, 'errmsg': '订单信息错误'})

        # 业务处理：调用支付宝的支付接口
        # 初始化
        alipay = AliPay(
            appid="2016090800464004",  # 应用APPID
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),  # 私钥文件的路径
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False,代表真实环境
        )

        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        total_amount = order.total_price + order.transit_price  # Decimal
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 订单id
            total_amount=str(total_amount),  # 订单总金额
            subject='天天生鲜%s' % order_id,  # 订单标题
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 支付页面地址
        pay_url = "https://openapi.alipaydev.com/gateway.do?" + order_string

        # 返回应答
        return JsonResponse({'res': 3, 'pay_url': pay_url})


# /order/check
# 采用ajax post请求
# 前端传递的参数：订单id（order_id)
class OrderCheckView(View):
    '''查询支付结果'''

    def post(self, request):
        '''查询支付结果'''

        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收参数
        order_id = request.POST.get('order_id')

        # 校验参数
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '订单id不完整'})

        # 获取订单信息
        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            # 订单信息错误
            return JsonResponse({'res': 2, 'errmsg': '订单信息错误'})

        # 业务处理：调用支付宝的支付接口 sdk
        # 初始化
        alipay = AliPay(
            appid="2016090800464004",  # 应用APPID
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),  # 私钥文件的路径
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False,代表真实环境
        )

        # 调用支付宝交易查询接口
        # {
        #      "trade_no": "2017032121001004070200176844", # 支付宝交易号
        #      "code": "10000", # 网关返回码
        #      "invoice_amount": "20.00",
        #      "open_id": "20880072506750308812798160715407",
        #      "fund_bill_list": [
        #          {
        #              "amount": "20.00",
        #              "fund_channel": "ALIPAYACCOUNT"
        #          }
        #      ],
        #      "buyer_logon_id": "csq***@sandbox.com",
        #      "send_pay_date": "2017-03-21 13:29:17",
        #      "receipt_amount": "20.00",
        #      "out_trade_no": "out_trade_no15",
        #      "buyer_pay_amount": "20.00",
        #      "buyer_user_id": "2088102169481075",
        #      "msg": "Success",
        #      "point_amount": "0.00",
        #      "trade_status": "TRADE_SUCCESS", # 支付交易状态
        #      "total_amount": "20.00"
        #  }

        while True:
            response = alipay.api_alipay_trade_query(out_trade_no=order_id)
            code = response.get('code')
            print('code:%s' % code)

            if code == '10000' and response.get('trade_status') == 'TRADE_SUCCESS':
                # 用户支付成功
                # 获取支付宝交易号
                trade_no = response.get('trade_no')
                # 更新订单支付状态，设置支付宝交易号
                order.order_status = 4  # 待评价
                order.trade_no = trade_no
                order.save()
                # 返回应答
                return JsonResponse({'res': 4, 'message': '支付成功'})
            elif code == '40004' or (code == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY'):
                # 等待买家付款
                # 支付订单还未创建，一会就可能成功
                import time
                time.sleep(5)
                continue
            else:
                # 支付错误
                return JsonResponse({'res': 3, 'errmsg': '支付失败'})


# /order/comment/订单id
class CommentView(LoginRequiredMixin, View):
    """订单评论"""

    def get(self, request, order_id):
        """提供评论页面"""

        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order', kwargs={'page': 1}))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order", kwargs={'page': 1}))

        # 根据订单的状态获取订单的状态标题
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 获取订单商品信息
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            amount = order_sku.count * order_sku.price
            # 动态给order_sku增加属性amount,保存商品小计
            order_sku.amount = amount
        # 动态给order增加属性order_skus, 保存订单商品信息
        order.order_skus = order_skus

        # 使用模板
        return render(request, "order_comment.html", {"order": order})

    def post(self, request, order_id):
        """处理评论内容"""

        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order', kwargs={'page': 1}))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order", kwargs={'page': 1}))

        # 获取评论条数
        total_count = request.POST.get("total_count")
        total_count = int(total_count)

        # 循环获取订单中商品的评论内容
        for i in range(1, total_count + 1):  # [1, total_count]
            # 获取评论的商品的id
            sku_id = request.POST.get("sku_%d" % i)  # sku_1 sku_2
            # 获取评论的商品的内容
            content = request.POST.get('content_%d' % i, '')  # content_1 content_2 content_3
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            order_goods.comment = content
            order_goods.save()

        order.order_status = 5  # 已完成
        order.save()

        return redirect(reverse("user:order", kwargs={"page": 1}))
