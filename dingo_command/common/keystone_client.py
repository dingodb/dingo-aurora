from keystoneauth1 import loading, session
from keystoneclient.v3 import client as keystone_client
from dingo_command.common import CONF

class KeystoneClient:
    def __init__(self, conf=CONF):
        # 从conf中加载keystone认证信息
        loader = loading.get_plugin_loader('password')
        auth = loader.load_from_options(
            auth_url=conf.keystone.auth_url,
            username=conf.keystone.user_name,
            password=conf.keystone.password,
            project_name=conf.keystone.project_name,
            user_domain_name=getattr(conf.keystone, 'user_domain_name', 'Default'),
            project_domain_name=getattr(conf.keystone, 'project_domain_name', 'Default')
        )
        sess = session.Session(auth=auth)
        self.client = keystone_client.Client(session=sess)

    def get_project_by_name(self, name):
        """
        根据项目名称查询项目
        """
        projects = self.client.projects.list(name=name)
        return projects[0] if projects else None

    def create_project(self, name, domain=None, description=None):
        """
        创建新项目
        """
        domain = domain or self.client.session.get_project_domain_id()
        return self.client.projects.create(
            name=name,
            domain=domain,
            description=description
        )