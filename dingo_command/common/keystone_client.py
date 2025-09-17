from keystoneauth1 import loading, session
from keystoneclient.v3 import client as keystone_client
from dingo_command.common import CONF

class KeystoneClient:
    def __init__(self, token, project_id=None):
        # 使用 keystoneauth1 session 初始化 keystoneclient
        loader = loading.get_plugin_loader('token')
        auth_kwargs = {
            'token': token,
            'auth_url': CONF.nova.auth_url
        }
        
        # 添加项目信息以获取完整的服务目录
        if project_id:
            auth_kwargs['project_id'] = project_id
        auth = loader.load_from_options(**auth_kwargs)
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
    
    def create_app_credential(self, user_id, name, roles=None):
        """
        创建应用凭证 (AppCredential)
        
        Args:
            user_id: 用户 ID
            name: 应用凭证名称
            roles: 角色列表，格式为 [{"name": "role_name"}]
            blob: 必需的凭证内容（通常为 JSON 字符串）
        
        Returns:
            创建的 AppCredential 对象
        """
        return self.client.application_credentials.create(
            user=user_id,
            name=name,
            roles=roles or []
        )
    def get_app_credential(self, user_id, name):
        """
        根据用户 ID 和应用凭证名称查询应用凭证
        """
        app_credentials = self.client.application_credentials.list(user=user_id, name=name)
        return app_credentials[0] if app_credentials else None