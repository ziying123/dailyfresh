from django.core.files.storage import Storage
from django.conf import settings
from fdfs_client.client import Fdfs_client


class FDFSStorage(Storage):
    '''fast dfs文件存储类'''

    def __init__(self, client_conf=None, nginx_url=None):
        if client_conf is None:
            client_conf = settings.FDFS_CLIENT_CONF
        self.client_conf = client_conf

        if nginx_url is None:
            nginx_url = settings.FDFS_NGINX_URL
        self.nginx_url = nginx_url

    # def open(self, name, mode='rb'):
    def _open(self, name, mode='rb'):
        '''打开文件时使用'''
        pass

    # Django中的Storage.save方法调用
    # save方法的返回值最终会保存在表的image字段中
    # def save(self, name, content, max_length=None):
    def _save(self, name, content):
        '''保存文件时调用'''
        # name: 所要保存的文件的名称
        # content: 包含上传文件内容的File类的实例对象

        # 上传文件内容到fast dfs文件系统中
        client = Fdfs_client(self.client_conf)

        # 获取上传文件的内容
        content = content.read()

        # 文件上传
        res = client.upload_by_buffer(content)

        # {
        #     'Group name': group_name,
        #     'Remote file_id': remote_file_id,
        #     'Status': 'Upload successed.',
        #     'Local file name': '',
        #     'Uploaded size': upload_size,
        #     'Storage IP': storage_ip
        # }

        # 判断文件上传是否成功
        if res['Status'] != 'Upload successed.':
            raise Exception('上传文件到Fdfs失败')

        # 获取文件id
        file_id = res['Remote file_id']
        return file_id

    def exists(self, name):
        '''判断文件在存储系统中是否存在'''
        return False

    def url(self, name):
        '''返回可访问到文件url地址'''
        # name:文件id
        return self.nginx_url + name
