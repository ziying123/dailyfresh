# 使用celery
from django.conf import settings
from django.core.mail import send_mail
from django.template import loader
from celery import Celery


# 初始化django运行所依赖的环境
# 这几句代码需要在celery worker的一端加上
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DailyFresh.settings")
django.setup()


from goods.models import GoodsType, IndexGoodsBanner, IndexPromotionBanner, IndexTypeGoodsBanner


# 创建一个Celery类的对象
app = Celery('celery_tasks.tasks', broker='redis://127.0.0.1:6379/9')


# 定义任务函数
@app.task
def send_register_active_email(to_email, username, token):
    '''发送激活邮件'''

    subject = '天天生鲜欢迎信息'
    message = ''
    sender = settings.EMAIL_FROM
    receiver = [to_email]
    html_message = '<h1>%s, 欢迎您成为天天生鲜注册会员</h1>请点击以下链接激活您的账号<br/><a href="http://127.0.0.1:8000/user/active/%s">http://127.0.0.1:8000/user/active/%s</a>' % (
    username, token, token)

    # 发送邮件
    # send_mail 内部函数 只需要穿参数就可  但是需要在 settings 里面做配置
    send_mail(subject, message, sender, receiver, html_message=html_message)


@app.task
def generate_static_index_html():
    '''生成静态首页'''

    # 获取商品的分类信息
    types = GoodsType.objects.all()

    # 获取首页的轮播商品信息
    index_banner = IndexGoodsBanner.objects.all().order_by('index')

    # 获取首页促销活动信息
    promotion_banner = IndexPromotionBanner.objects.all().order_by('index')

    # 获取首页分类商品展示信息
    # type_banner = IndexTypeGoodsBanner.objects.all()
    for type in types:
        # 查询type类型首页展示的文字商品的信息
        title_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by('index')
        # 查询type类型首页展示的图片商品的信息
        image_banner = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by('index')
        # 动态给type对象增加两个属性:
        # title_banner(保存type类型首页展示的文字商品)
        # image_banner(保存type类型首页展示的图片商品)
        type.title_banner = title_banner
        type.image_banner = image_banner

    # 获取用户购物车中商品的数目
    cart_count = 0

    # 组织模板上下文
    context = {'types': types,
               'index_banner': index_banner,
               'promotion_banner': promotion_banner,
               'cart_count': cart_count}

    # 生成静态首页的内容
    # 1.加载模板文件
    temp = loader.get_template('static_index.html')

    # 2.模板渲染：产生标准的html页面内容
    static_html = temp.render(context)

    # 生成静态文件0
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(static_html)
