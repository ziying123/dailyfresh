from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.conf import settings
from django.views.generic import View

from user.models import User, Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from celery_tasks.tasks import send_register_active_email
from utils.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
import re


# Create your views here.


# /user/register
class RegisterView(View):
    '''注册'''

    def get(self, request):
        '''显示'''

        return render(request, 'register.html')

    def post(self, request):
        '''注册信息提交'''

        # 接受参数
        username = request.POST['user_name']
        password = request.POST['pwd']
        email = request.POST['email']
        allow = request.POST['allow']

        # 校验参数
        # 检验参数完整性
        if not all([username, password, email, allow]):
            return render(request, 'register.html', {'errmsg': '参数不完整'})

        # 检验邮箱的正则
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱不合法'})

        # 是否同意协议
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})

        # 判断用户名是否重复
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            user = None

        if user:
            # 用户名已存在
            return render(request, 'register.html', {'errmsg': '用户名已存在'})

        # 业务处理
        user = User.objects.create_user(username,
                                        email,
                                        password)

        # django 的默认添加用户的激活状态为1
        user.is_active = 0
        user.save()

        # 加密用户的身份信息，生成激活token itsdangerous
        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        token = serializer.dumps(info)  # bytes
        token = token.decode()    # str类型

        # 发送激活邮件
        # 找其他人帮助我们发送邮件 celery:异步执行任务
        send_register_active_email.deley(email, username, token)

        # 返回视图
        return redirect(reverse('goods:index'))


# /user/active/加密信息token
class ActiveView(View):
    '''激活'''

    def get(self, request, token):
        '''激活'''

        serializer = Serializer(settings.SECRET_KEY, 3600)

        try:
            info = serializer.loads(token)

            # 获取用户的ID
            user_id = info['confirm']

            # 获取用户信息
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()

            # 跳转到登陆界面
            return redirect(reverse('user:login'))

        except SignatureExpired:
            return HttpResponse('激活链接已失效')


# /user/login
class LoginView(View):
    '''登陆'''

    def get(self, request):
        '''显示'''

        # 尝试从cookie中获取username
        if 'username' in request.COOKIES:
            # 记住了用户名

            username = request.COOKIES['username']
            checked = 'checked'

        else:
            # 没记住用户名

            username = ''
            checked = ''

        # 使用模板
        return render(request, 'login.html', {'username': username, 'checked': checked})

    def post(self, request):
        '''登录'''

        # 接受参数
        username = request.POST['username']
        password = request.POST['pwd']
        remember = request.POST['remember']   # on

        # 校验参数
        # 检验参数的完整性
        if not all([username, password]):
            return render(request, 'login.html', {'errmsg': '参数不完整'})

        # 业务处理
        user = authenticate(username=username, password=password)

        # 判断是否登录成功
        if user is not None:
            # 登录成功

            # 判断是否激活
            if user.is_active:
                # 用户已经激活哦

                # 记住用户的登录状态
                login(request, user)

                # 获取登录后跳转的的地址， 默认商品首页
                next_url = request.GET.get('next', 'goods:index')

                response = redirect(next_url)

                # 是否需要记住用户名
                if remember == "on":
                    # 记住用户名

                    # 设置cookie, 需要通过HttpReponse类的实例对象, set_cookie
                    # HttpResponseRedirect JsonResponse
                    response.set_cookie('username', username, max_age=7*3600)

                else:
                    # 不需要记住用户名
                    response.delete_cookie('username')

                # 跳转到首页
                return response

            else:
                # 用户未激活
                return render(request, 'login.html', {'errmsg': '账户未激活'})

        else:
            # 用户名或密码错误
            return render(request, 'login.html', {'errmsg': '用户名或密码错误'})


# /user/logout
class LogoutView(View):
    '''退出登录'''

    def get(self, request):
        # 清除用户的登录信息

        logout(request)

        # 跳转到首页
        return redirect(reverse('goods:index'))


# /user/
# class UserInfoView(View):
# class UserInfoView(LoginRequiredView):
class UserInfoView(View):
    '''用户中心-信息页面'''

    def get(self, request):
        '''显示'''

        # 获取登录的用户
        user = request.user

        # 获取用户的默认地址
        address = Address.objects.get_default_address(user)

        # 获取用户最近浏览记录
        conn = get_redis_connection('default')
        history_key = 'history_%d' % user.id

        # 获取最近5个商品记录
        sku_ids = conn.lrange(history_key, 0, 4)

        # 获取用户浏览的商品的信息
        skus_li = []
        skus = GoodsSKU.objects.filter(id__in=sku_ids)

        for sku_id in sku_ids:
            # 遍历商品的信息
            for sku in skus:
                if sku.id == int(sku_id):
                    skus_li.append(sku)

        # 组织模板上下文
        context = {'skus': skus, 'address': address, 'page': 'user'}

        # 使用模板
        return render(request, 'user_center_info.html', context)


# /user/order/页码
# class UserOrderView(LoginRequiredMixin, View):
#     '''用户中心-订单页'''
#
#     def get(self. request):
#         '''显示'''
#
# class UserOrderView(LoginRequiredMixin, View):
#     '''用户中心-订单页'''
#
#     def get(self, request, page):
#         '''显示'''
#
#         # 获取登录用户
#         user = request.user
#
#         # 获取用户的订单信息
#         orders = OrderInfo.objects.filter(user=user).order_by('-create_time')
#
#         # 遍历orders，获取每个订单的订单商品的信息
#         for order in orders:
#
#             # 查询和order相关的订单商品的信息
#             order_skus = OrderGoods.objects.filter(order=order)
#
#             # 遍历order_skus, 计算订单中每个商品的小计
#             for order_sku in order_skus:
#
#                 # 计算小计
#                 amount = order_sku.count * order_sku.price
#
#                 # 给order_sku增加属性amount,保存订单商品的小计
#                 order_sku.amount = amount
#
#             # 计算订单的实付款
#             total_amount = order.total_price + order.transit_price
#
#             # 获取订单状态的名称
#             status_name = OrderInfo.ORDER_STATUS[order.order_status]
#
#             # 给order增加属性, 保存订单商品的信息
#             order.order_skus = order_skus
#             order.total_amount = total_amount
#             order.status_name = status_name
#
#         # 分页
#         paginator = Paginator(orders, 1)
#
#         # 处理页码
#         page = int(page)
#
#         if page <= 0 or page > paginator.num_pages:
#             # 默认获取第1页的内容
#             page = 1
#
#         # 获取第page页的Page对象
#         order_page = paginator.page(page)
#
#         # 处理页码列表
#         # 1.总页数<5, 显示所有页码
#         # 2.当前页是前3页，显示1-5页
#         # 3.当前页是后3页，显示后5页
#         # 4.其他情况，显示当前页的前2页，当前页，当前页的后2页
#         num_pages = paginator.num_pages
#         if num_pages < 5:
#             pages = range(1, num_pages + 1)
#         elif page <= 3:
#             pages = range(1, 6)
#         elif num_pages - page <= 2:
#             pages = range(num_pages - 4, num_pages + 1)
#         else:
#             pages = range(page - 2, page + 3)
#
#         # 组织上下文数据
#         context = {'order_page': order_page,
#                    'pages': pages,
#                    'page': 'order'}
#
#         # 使用模板
#         return render(request, 'user_center_order.html', context)


# 模型管理器类
# /user/address


# /user/order
class UserOrderView(LoginRequiredMixin,View):
    """用户订单"""

    def get(self,request,page):
        """用户订单页面显示"""

        # 获取登陆的用户
        user = request.user
        # 获取用户的订单信息
        orders = OrderInfo.objects.filter(user=user).order_by("-create_time")
        # 遍历orders 获取每个订单的订单商品信息
        for order in orders:
            # 查询和order相关的订单商品的信息
            order_skus = OrderGoods.objects.filter(order=order)
            # 遍历order_skus,计算订单中每个商品的小计
            for order_sku in order_skus:
                # 计算小计
                amount = order_sku.count * order_sku.price
                # orser_sku增加属性,保存订单商品的小计
                order_sku.amount = amount
            # 计算订单的实付款
            total_amount = order.total_price + order.transit_price

            # 获取订单状态的名称
            status_name = OrderInfo.ORDER_STATUS[order.order_status]
            # 给order动态增加属性order_skus，保存订单商品的属性
            order.order_skus = order_skus
            order.total_amount = total_amount
            order.status_name = status_name

        # 分页
        paginator = Paginator(orders,1)

        # 处理页码，
        page = int(page)

        # 获取page页的Page对象
        order_page = paginator.page(page)

        # 处理页码
        # 总页数小于5时，显示总页数
        # 当前页是前3页时，显示前5页
        # 当前页时后3页时，显示后5页
        # 当前页的前两页，当前页，当前页的后两页
        num_pages = paginator.num_pages
        if num_pages <= 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        # 组织模板上下文
        content = {'order_page':order_page,
                   'pages':pages,
                   'page': 'order'}

        return render(request,"user_center_order.html",content)


class AddressView(View):
    '''用户中心-订单页'''

    def get(self, request):
        '''显示'''

        # 获取登录的user对象
        user = request.user
        # 如果用户存在默认地址，新添加的地址不作为默认地址，否则作为默认地址
        address = Address.objects.get_default_address(user)

        # 使用模板
        return render(request, 'user_center_site.html', {'address': address, 'page': 'address'})

    def post(self, request):
        '''添加地址'''

        # 接收参数
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 参数校验
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg': '参数不完整'})

        # 业务处理: 添加收货地址
        # 获取登录的user对象
        user = request.user

        # 如果用户存在默认地址，新添加的地址不作为默认地址，否则作为默认地址
        address = Address.objects.get_default_address(user)

        if address:
            # 存在默认地址
            is_default = False

        else:
            # 不存在默认地址
            is_default = True

        # 添加地址
        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回应答：刷新地址页面
        return redirect(reverse('user:address'))
