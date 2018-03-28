from haystack import indexes
from goods.models import GoodsSKU

#  指定对于某个类的某些数据建立索引


class GoodsSKUIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)

    # 索引字段: use_template=True说明会在一个文件中指定根据表的哪些字段内容建立索引

    def get_model(self):
        return GoodsSKU

    # 搜索引擎会对这个方法返回的数据建立索引
    def index_queryset(self, using=None):
        return self.get_model().objects.all()
