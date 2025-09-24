#!/bin/env python3
"""
Harbor API客户端模块

该模块提供了与Harbor容器镜像仓库进行交互的底层API客户端，
包括用户管理、项目管理、镜像仓库管理等核心功能。

主要功能：
1. 用户管理：创建、查询Harbor用户
2. 项目管理：创建、更新、删除项目，管理项目成员
3. 镜像仓库管理：查询、删除镜像仓库
4. 配额管理：查询和更新项目存储配额
5. 镜像标签管理：获取镜像的标签信息和大小

配置说明：
- 从配置中心获取Harbor连接信息
- 支持基本认证和机器人认证两种方式
- 自动处理SSL证书验证配置

使用示例：
    from dingo_command.common.harbor_client import HarborAPI

    # 使用默认配置创建客户端
    harbor_client = HarborAPI()

    # 使用自定义认证信息
    harbor_client = HarborAPI(
        username="admin",
        password="password",
        auth_type="basic"
    )

    # 创建用户
    result = harbor_client.create_user(
        username="dev001",
        email="dev@example.com",
        password="password123"
    )

依赖：
    - requests: HTTP请求库
    - urllib3: HTTP客户端库
    - dingo_command.common.CONF: 配置中心

作者: Dingo Aurora Team
版本: 1.0.0
"""

import requests
import urllib3
from typing import Dict, Any
from urllib.parse import quote
from dingo_command.common import CONF

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Harbor配置 - 从配置中心获取
# 该配置字典包含了连接Harbor服务所需的所有配置信息
HARBOR_CONFIG = {
    "base_url": CONF.harbor.base_url,  # Harbor服务的基础URL地址
    "robot_username": CONF.harbor.robot_username,  # 机器人用户名，用于API认证
    "robot_token": CONF.harbor.robot_token,  # 机器人访问令牌
    "verify_ssl": CONF.harbor.verify_ssl,  # 是否验证SSL证书
}


class HarborAPI:
    """
    Harbor API客户端类

    该类提供了与Harbor容器镜像仓库进行交互的完整API接口，
    支持用户管理、项目管理、镜像仓库管理等所有核心功能。

    主要特性：
    1. 灵活的认证方式：支持基本认证和机器人认证
    2. 统一的响应格式：所有方法返回一致的响应结构
    3. 自动错误处理：内置异常捕获和错误响应生成
    4. 配置中心集成：自动从配置中心获取连接信息

    认证方式：
    - basic: 使用用户名和密码进行基本认证
    - robot: 使用机器人用户名和令牌进行认证

    配置优先级：
    1. 构造函数传入的config参数（最高优先级）
    2. 构造函数传入的username/password参数
    3. 配置中心中的默认配置（最低优先级）

    Attributes:
        config (Dict[str, Any]): Harbor配置信息
        base_url (str): Harbor服务的基础URL
        username (str): 认证用户名
        password (str): 认证密码
        _auth (tuple): 认证信息元组

    Example:
        # 使用默认配置
        harbor_client = HarborAPI()

        # 使用自定义配置
        custom_config = {
            "base_url": "https://harbor.example.com",
            "robot_username": "robot$myuser",
            "robot_token": "mytoken",
            "verify_ssl": False
        }
        harbor_client = HarborAPI(config=custom_config)

        # 使用基本认证
        harbor_client = HarborAPI(
            username="admin",
            password="password123",
            auth_type="basic"
        )

        # 使用机器人认证
        harbor_client = HarborAPI(auth_type="robot")

    Note:
        - 所有API调用都会自动处理认证信息
        - 响应格式统一，便于上层服务处理
        - 支持SSL证书验证配置
        - 内置重试和错误处理机制
    """

    def __init__(
        self,
        config: Dict[str, Any] = None,
        username: str = None,
        password: str = None,
        auth_type: str = "robot",
    ):
        """
        初始化Harbor API客户端

        根据传入的参数初始化客户端，支持多种配置方式和认证类型。
        配置优先级：config参数 > username/password参数 > 配置中心默认配置。

        Args:
            config (Dict[str, Any], optional): 自定义配置字典
                - base_url (str): Harbor服务地址
                - robot_username (str): 机器人用户名
                - robot_token (str): 机器人令牌
                - verify_ssl (bool): 是否验证SSL证书
                - 示例：{"base_url": "https://harbor.example.com"}

            username (str, optional): 基本认证用户名
                - 当auth_type为"basic"时使用
                - 如果未提供，将使用配置中心或config中的机器人认证
                - 示例：'admin', 'user001'

            password (str, optional): 基本认证密码
                - 当auth_type为"basic"时使用
                - 必须与username同时提供
                - 示例：'password123'

            auth_type (str): 认证类型
                - "basic": 基本认证，使用username和password
                - "robot": 机器人认证，使用配置中的机器人凭据
                - 默认值："basic"

        Raises:
            ValueError: 当认证类型不支持时抛出
            KeyError: 当配置信息不完整时抛出

        Example:
            # 使用默认配置和机器人认证
            client1 = HarborAPI()

            # 使用基本认证
            client2 = HarborAPI(
                username="admin",
                password="password123",
                auth_type="basic"
            )

            # 使用自定义配置
            custom_config = {
                "base_url": "https://harbor.example.com",
                "robot_username": "robot$myuser",
                "robot_token": "mytoken"
            }
            client3 = HarborAPI(config=custom_config)

        Note:
            - 如果同时提供config和username/password，config优先级更高
            - 机器人认证需要确保配置中心中有正确的凭据信息
            - base_url会自动去除末尾的斜杠字符
        """
        self.config = config or HARBOR_CONFIG
        self.base_url = self.config["base_url"].rstrip("/")
        self.username = username
        self.password = password

        if auth_type == "basic":
            self._auth = (self.username, self.password)
        elif auth_type == "robot":
            self._auth = (self.config["robot_username"], self.config["robot_token"])
        else:
            raise ValueError(f"不支持的认证方式: {auth_type}")
    # 请求
    def request(self, method, url, **kwargs):
        return requests.request(
            method,
            url,
            auth=self._auth,
            headers={"Content-Type": "application/json"},
            # verify=False,
            **kwargs,
        )

    def return_response(
        self, status: bool, code: int, message: str, data: Any = None
    ) -> Dict[str, Any]:
        """
        生成统一的API响应格式

        该方法用于生成所有Harbor API方法的统一响应格式，确保返回数据
        结构的一致性，便于上层服务处理响应结果。

        Args:
            status (bool): 操作是否成功
                - True: 操作成功
                - False: 操作失败

            code (int): HTTP状态码或自定义错误码
                - 200: 成功
                - 201: 创建成功
                - 400: 请求错误
                - 401: 认证失败
                - 404: 资源不存在
                - 409: 资源冲突
                - 500: 服务器内部错误

            message (str): 操作结果描述或错误信息
                - 成功时：描述操作结果
                - 失败时：说明错误原因

            data (Any, optional): 返回的数据内容
                - 成功时：包含请求的数据
                - 失败时：通常为None或错误详情
                - 默认为None

        Returns:
            Dict[str, Any]: 统一格式的响应字典
                - status (bool): 操作状态
                - code (int): 状态码
                - message (str): 消息描述
                - data (Any): 返回数据

        Example:
            # 成功响应
            success_response = self.return_response(
                status=True,
                code=200,
                message="用户创建成功",
                data={"user_id": 123, "username": "dev001"}
            )

            # 错误响应
            error_response = self.return_response(
                status=False,
                code=409,
                message="用户已存在"
            )

        Note:
            - 所有Harbor API方法都使用此方法生成响应
            - 响应格式与上层服务保持一致
            - 便于统一处理成功和失败情况
        """
        return {
            "status": status,
            "code": code,
            "message": message,
            "data": data,
        }

    # 创建用户
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        realname: str = "",
        comment: str = "",
        admin: bool = False,
    ) -> Dict[str, Any]:
        """
        在Harbor中创建新的用户账户

        该方法会在Harbor用户管理系统中创建一个新的用户账户，支持设置
        用户的基本信息、权限和备注等。新创建的用户默认具有普通用户权限。

        Args:
            username (str): 用户名
                - 长度限制：3-30个字符
                - 字符限制：只能包含字母、数字、连字符和下划线
                - 唯一性：用户名在系统中必须唯一
                - 示例：'developer001', 'test-user'

            email (str): 用户邮箱地址
                - 格式要求：必须是有效的邮箱格式
                - 用途：用于密码重置和通知
                - 唯一性：邮箱在系统中应该唯一
                - 示例：'user@example.com', 'dev@company.com'

            password (str): 用户密码
                - 长度要求：通常至少6个字符
                - 复杂度建议：包含大小写字母、数字和特殊字符
                - 安全建议：避免使用常见密码
                - 示例：'MySecurePass123!'

            realname (str, optional): 用户真实姓名
                - 默认值：空字符串
                - 用途：用于显示和识别用户
                - 示例：'张三', 'John Doe'

            comment (str, optional): 用户备注信息
                - 默认值：空字符串
                - 用途：记录用户相关信息，如部门、职位等
                - 示例：'开发部门', 'QA工程师'

            admin (bool, optional): 是否为管理员
                - 默认值：False（普通用户）
                - 用途：控制用户的系统权限
                - 示例：True 表示管理员用户

        Returns:
            Dict[str, Any]: 包含创建结果的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 创建普通用户
            result = harbor_client.create_user(
                username="dev001",
                email="dev001@company.com",
                password="DevPass123!",
                realname="张三",
                comment="开发部门"
            )

            # 创建管理员用户
            admin_result = harbor_client.create_user(
                username="admin001",
                email="admin@company.com",
                password="AdminPass456!",
                realname="管理员",
                admin=True
            )

            if result["status"]:
                print(f"用户创建成功: {result['message']}")
            else:
                print(f"用户创建失败: {result['message']}")

        Note:
            - 新创建的用户默认具有普通用户权限
            - 用户名和邮箱在系统中必须唯一
            - 建议在生产环境中使用强密码策略
            - 用户创建成功后需要手动分配项目权限
            - 管理员用户具有系统级权限，请谨慎创建
        """
        try:
            user_data = {
                "username": username,
                "email": email,
                "password": password,
                "realname": realname,
                "comment": comment,
                "admin": admin,
            }

            # 移除空值
            user_data = {k: v for k, v in user_data.items() if v}

            create_url = f"{self.base_url}/api/v2.0/users"

            response = self.request(
                "POST",
                create_url,
                json=user_data,
            )

            if response.status_code == 201:
                return self.return_response(
                    True, response.status_code, f"用户 {username} 创建成功"
                )
            elif response.status_code == 409:
                return self.return_response(
                    False, response.status_code, f"用户 {username} 已存在"
                )
            else:
                return self.return_response(
                    False, response.status_code, f"用户创建失败: {response.text}"
                )

        except Exception as e:
            return self.return_response(False, 500, f"创建用户异常: {str(e)}")

    # 获取所有用户
    def get_all_users(self) -> Dict[str, Any]:
        """
        获取Harbor中所有用户的信息

        该方法会查询Harbor系统中的所有用户账户，返回用户的详细信息。
        需要管理员权限才能执行此操作。

        Returns:
            Dict[str, Any]: 包含用户列表的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (list): 用户信息列表，每个用户包含：
                    - user_id (int): 用户ID
                    - username (str): 用户名
                    - email (str): 邮箱地址
                    - realname (str): 真实姓名
                    - comment (str): 备注信息
                    - admin (bool): 是否为管理员
                    - creation_time (str): 创建时间
                    - update_time (str): 更新时间

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取所有用户
            result = harbor_client.get_all_users()

            if result["status"]:
                users = result["data"]
                for user in users:
                    print(f"用户ID: {user['user_id']}")
                    print(f"用户名: {user['username']}")
                    print(f"邮箱: {user['email']}")
                    print(f"管理员: {user['admin']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 需要管理员权限才能执行
            - 返回的用户列表按用户ID排序
            - 如果用户数量很多，建议使用分页参数
            - 敏感信息（如密码）不会在响应中返回
        """
        try:
            url = f"{self.base_url}/api/v2.0/users"
            response = self.request("GET", url)
            return self.return_response(True, response.status_code, response.json())
        except Exception as e:
            return self.return_response(False, 500, f"获取所有用户异常: {str(e)}")

    def get_project_quotas(self, project_id: str) -> Dict[str, Any]:
        """
        获取指定项目的存储配额信息
        """
        try:
            url = f"{self.base_url}/api/v2.0/quotas?reference_id={project_id}"
            response = self.request("GET", url)
            return self.return_response(True, response.status_code, '获取指定项目配额成功', response.json())
        except Exception as e:
            return self.return_response(False, 500, f"获取指定项目配额异常: {str(e)}")

    def get_all_quotas(self) -> Dict[str, Any]:
        """
        获取Harbor中所有项目的存储配额信息

        该方法会查询系统中所有项目的存储配额配置，包括存储限制和已使用情况。
        返回的配额信息按项目ID排序，支持分页查询。

        Returns:
            Dict[str, Any]: 包含配额信息的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (list): 配额信息列表，每个配额包含：
                    - id (int): 配额ID
                    - ref (dict): 引用信息
                        - name (str): 项目名称
                        - owner_name (str): 所有者名称
                    - hard (dict): 硬限制
                        - storage (int): 存储限制（字节）
                    - used (dict): 已使用量
                        - storage (int): 已使用存储（字节）
                    - creation_time (str): 创建时间
                    - update_time (str): 更新时间

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取所有项目配额
            result = harbor_client.get_all_quotas()

            if result["status"]:
                quotas = result["data"]
                for quota in quotas:
                    project_name = quota['ref']['name']
                    hard_gb = quota['hard']['storage'] / (1024**3) if quota['hard']['storage'] else 0
                    used_gb = quota['used']['storage'] / (1024**3) if quota['used']['storage'] else 0
                    print(f"项目: {project_name}")
                    print(f"存储限制: {hard_gb:.2f} GB")
                    print(f"已使用: {used_gb:.2f} GB")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 默认返回前100个配额信息（page_size=100）
            - 存储大小以字节为单位，需要自行转换为GB
            - 只有设置了存储限制的项目才会出现在结果中
            - 建议定期调用此方法监控存储使用情况
        """
        try:
            page = 1
            page_size = 100
            all_quotas = []
            while True:
                url = f"{self.base_url}/api/v2.0/quotas?page={page}&page_size={page_size}&reference=project"
                response = self.request("GET", url)
                response.raise_for_status()
                data = response.json()
                if not data:
                    break
                all_quotas.extend(data)
                page+=1
            return self.return_response(
                    True, 200, "获取项目配额成功", all_quotas
                )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目配额异常异常: {str(e)}")

    def get_project_repositories(
        self, project_name: str, page: int = 1, page_size: int = 100, get_all: bool = False
    ) -> Dict[str, Any]:
        """
        获取指定项目下的所有镜像仓库信息

        该方法会查询指定项目中的所有镜像仓库，返回仓库的基本信息、
        标签数量、创建时间等详细信息。该方法会自动遍历所有页面，
        获取项目下的全部仓库数据，忽略传入的page和page_size参数。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 示例：'k8s', 'my-project'
            page (int): 起始页码（此参数被忽略，始终从第1页开始）
            page_size (int): 每页大小（此参数被忽略，内部固定为100）

        Returns:
            Dict[str, Any]: 包含仓库信息的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (list): 仓库信息列表，每个仓库包含：
                    - id (int): 仓库ID
                    - name (str): 完整仓库名称（包含项目前缀）
                    - project_id (int): 项目ID
                    - description (str): 仓库描述
                    - artifact_count (int): 镜像数量
                    - pull_count (int): 拉取次数
                    - creation_time (str): 创建时间
                    - update_time (str): 更新时间

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取项目下的所有仓库
            result = harbor_client.get_project_repositories("k8s")

            if result["status"]:
                repositories = result["data"]
                for repo in repositories:
                    print(f"仓库ID: {repo['id']}")
                    print(f"仓库名称: {repo['name']}")
                    print(f"镜像数量: {repo['artifact_count']}")
                    print(f"拉取次数: {repo['pull_count']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 该方法会自动获取项目下的所有仓库，不受page和page_size参数影响
            - 内部使用分页机制（每页100条）循环获取所有数据
            - 仓库名称包含项目前缀，如'k8s/nginx'
            - 如果项目不存在或没有仓库，返回空列表
            - 建议结合get_repository_artifacts获取详细标签信息
        """
        try:
            if get_all:
                all_repositories = []
                while True:
                    url = f"{self.base_url}/api/v2.0/projects/{project_name}/repositories?page={page}&page_size={page_size}"
                    response = self.request("GET", url)
                    if response.status_code == 200:
                        all_repositories.extend(response.json())
                        page += 1
                        if len(response.json()) < page_size:
                            break
                    else:
                        return self.return_response(
                            False, response.status_code, "获取项目下所有镜像失败", response.json()
                        )
                return self.return_response(
                    True, 200, "获取项目下所有镜像成功", all_repositories
                )
            else:
                url = f"{self.base_url}/api/v2.0/projects/{project_name}/repositories?page={page}&page_size={page_size}"
                response = self.request("GET", url)
                return self.return_response(
                    True, 200, "获取项目下所有镜像成功", response.json()
                )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目下所有镜像异常: {str(e)}")

    def get_project_repository(
        self,
        project_name: str,
        repository_name: str,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        获取指定项目下的指定镜像仓库信息

        该方法会查询指定项目中的指定镜像仓库，返回仓库的基本信息、
        标签数量、创建时间等详细信息。支持分页查询。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 示例：'k8s', 'my-project'
            repository_name (str): 镜像仓库名称
                - 必须是已存在的镜像仓库名称
                - 镜像仓库名称区分大小写
                - 示例：'nginx', 'core/kube-calico-controllers'

        Returns:
            Dict[str, Any]: 包含仓库信息的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (list): 仓库信息列表，每个仓库包含：
                    - id (int): 仓库ID
                    - name (str): 完整仓库名称（包含项目前缀）
                    - project_id (int): 项目ID
                    - description (str): 仓库描述
                    - artifact_count (int): 镜像数量
                    - pull_count (int): 拉取次数
                    - creation_time (str): 创建时间
                    - update_time (str): 更新时间

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取项目下的所有仓库
            result = harbor_client.get_project_repository("k8s", "nginx")

            if result["status"]:
                repositories = result["data"]
                for repo in repositories:
                    print(f"仓库ID: {repo['id']}")
                    print(f"仓库名称: {repo['name']}")
                    print(f"镜像数量: {repo['artifact_count']}")
                    print(f"拉取次数: {repo['pull_count']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 默认返回前100个仓库（page_size=100）
            - 仓库名称包含项目前缀，如'k8s/nginx'
            - 如果项目不存在或没有仓库，返回空列表
            - 建议结合get_repository_artifacts获取详细标签信息
        """
        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}/repositories/{repository_name}?page={page}&page_size={page_size}"
            response = self.request("GET", url)
            if response.status_code == 200:
                return self.return_response(
                    True,
                    response.status_code,
                    "获取项目下指定镜像仓库成功",
                    [response.json()],
                )
            else:
                return self.return_response(
                    False,
                    response.status_code,
                    "获取项目下指定镜像仓库失败",
                    [response.json()],
                )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目下指定镜像仓库异常: {str(e)}")

    def delete_project_repository(
        self, project_name: str, repository_name: str
    ) -> Dict[str, Any]:
        """
        删除指定项目下的镜像仓库

        该方法会删除指定项目中的特定镜像仓库，包括该仓库下的所有镜像、
        标签和配置信息。删除操作不可逆，请谨慎使用。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 示例：'my-project', 'k8s'

            repository_name (str): 要删除的镜像仓库名称
                - 可以是简单名称或包含路径的名称
                - 如果包含路径分隔符'/'，系统会自动进行URL编码
                - 示例：'nginx', 'core/kube-calico-controllers'

        Returns:
            Dict[str, Any]: 包含删除结果的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 删除简单名称的镜像仓库
            result = harbor_client.delete_project_repository(
                project_name="my-project",
                repository_name="nginx"
            )

            # 删除包含路径的镜像仓库
            result = harbor_client.delete_project_repository(
                project_name="k8s",
                repository_name="core/kube-calico-controllers"
            )

            if result["status"]:
                print(f"仓库删除成功: {result['message']}")
            else:
                print(f"仓库删除失败: {result['message']}")

        Note:
            - 删除操作不可逆，请谨慎使用
            - 删除前请确保仓库中没有重要的镜像数据
            - 建议在删除前备份重要的镜像数据
            - 包含路径的仓库名称会自动进行URL编码处理
            - 删除后该仓库下的所有镜像和标签都将丢失
        """
        try:
            if "/" in repository_name:
                encoded_repo = quote(quote(repository_name, safe=""), safe="")
            else:
                encoded_repo = repository_name
            url = f"{self.base_url}/api/v2.0/projects/{project_name}/repositories/{encoded_repo}"
            response = self.request("DELETE", url)
            if response.status_code == 200:
                return self.return_response(
                    True, response.status_code, "仓库镜像删除成功", response.text
                )
            else:
                return self.return_response(
                    False, response.status_code, "仓库镜像删除失败", response.text
                )
        except Exception as e:
            return self.return_response(False, 500, f"仓库镜像删除异常: {str(e)}")

    def search(self,q: str) -> Dict[str, Any]:
        """
        搜索Harbor中的项目和仓库
        """
        try:
            url = f"{self.base_url}/api/v2.0/search?q={q}"
            response = self.request("GET", url)
            return self.return_response(
                True, response.status_code, "搜索项目和仓库成功", response.json()
            )
        except Exception as e:
            return self.return_response(False, 500, f"搜索项目和仓库异常: {str(e)}")

    def get_projects(self) -> Dict[str, Any]:
        """
        获取Harbor中所有项目的基本信息

        该方法会查询系统中所有项目的列表，返回项目的基本信息包括
        项目名称、ID、公开性、创建时间等。自动分页获取所有数据。

        Returns:
            Dict[str, Any]: 包含项目列表的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (list): 项目信息列表，每个项目包含：
                    - project_id (int): 项目ID
                    - name (str): 项目名称
                    - owner_id (int): 所有者ID
                    - owner_name (str): 所有者名称
                    - public (bool): 是否公开
                    - repo_count (int): 仓库数量
                    - creation_time (str): 创建时间
                    - update_time (str): 更新时间
                    - metadata (dict): 项目元数据

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取所有项目
            result = harbor_client.get_projects()

            if result["status"]:
                projects = result["data"]
                for project in projects:
                    print(f"项目ID: {project['project_id']}")
                    print(f"项目名称: {project['name']}")
                    print(f"是否公开: {project['public']}")
                    print(f"仓库数量: {project['repo_count']}")
                    print(f"创建时间: {project['creation_time']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 返回所有用户有权限访问的项目
            - 项目按创建时间倒序排列
            - 自动分页获取所有数据，无需手动分页
            - 公开项目所有用户都可以访问
            - 私有项目只有成员可以访问
        """
        try:
            all_projects = []
            page = 1
            page_size = 100  # 每页获取100条数据，减少请求次数
            
            while True:
                url = f"{self.base_url}/api/v2.0/projects?page={page}&page_size={page_size}"
                response = self.request("GET", url)
                if response.status_code != 200:
                    return self.return_response(
                        False, response.status_code, f"获取仓库第{page}页失败", response.text
                    )
                
                data = response.json()
                
                if not data:  # 如果没有更多数据，退出循环
                    break
                    
                all_projects.extend(data)
                
                # 如果返回的数据少于page_size，说明已经是最后一页
                if len(data) < page_size:
                    break
                    
                page += 1
            
            return self.return_response(
                True, 200, f"获取所有项目成功，共{len(all_projects)}个项目", all_projects
            )
        except Exception as e:
            return self.return_response(False, 500, f"获取所有项目异常: {str(e)}")

    def get_project_info(self, project_name: str) -> Dict[str, Any]:
        """
        获取指定项目的详细信息

        该方法会查询指定项目的完整信息，包括项目配置、元数据、
        统计信息等详细信息。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 用户必须对该项目有访问权限
                - 示例：'k8s', 'my-project'

        Returns:
            Dict[str, Any]: 包含项目详细信息的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (dict): 项目详细信息，包含：
                    - project_id (int): 项目ID
                    - name (str): 项目名称
                    - owner_id (int): 所有者ID
                    - owner_name (str): 所有者名称
                    - public (bool): 是否公开
                    - repo_count (int): 仓库数量
                    - creation_time (str): 创建时间
                    - update_time (str): 更新时间
                    - metadata (dict): 项目元数据
                    - cve_allowlist (dict): CVE白名单配置
                    - storage_limit (int): 存储限制（字节）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取项目详细信息
            result = harbor_client.get_project_info("k8s")

            if result["status"]:
                project = result["data"]
                print(f"项目ID: {project['project_id']}")
                print(f"项目名称: {project['name']}")
                print(f"是否公开: {project['public']}")
                print(f"仓库数量: {project['repo_count']}")
                print(f"创建时间: {project['creation_time']}")

                # 获取存储限制
                if project.get('storage_limit'):
                    storage_gb = project['storage_limit'] / (1024**3)
                    print(f"存储限制: {storage_gb:.2f} GB")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 需要项目访问权限才能获取信息
            - 存储限制以字节为单位，需要自行转换为GB
            - 如果项目不存在，会返回404错误
            - 元数据字段可能为空，需要检查后再使用
        """
        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}"
            response = self.request("GET", url)
            return self.return_response(
                True, response.status_code, "获取项目信息成功", response.json()
            )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目信息异常: {str(e)}")

    def get_project_summary(self, project_name: str) -> Dict[str, Any]:
        """
        获取指定项目的概览信息
        """
        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}/summary"
            response = self.request("GET", url)
            return self.return_response(
                True, response.status_code, "获取项目概览信息成功", response.json()
            )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目概览信息异常: {str(e)}")

    # 获取项目成员
    def get_project_members(self, project_name: str) -> Dict[str, Any]:
        """
        获取指定项目的所有成员信息

        该方法会查询指定项目中的所有成员，包括成员的用户名、角色、
        添加时间等详细信息。只有项目成员或管理员可以查看。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 用户必须对该项目有访问权限
                - 示例：'k8s', 'my-project'

        Returns:
            Dict[str, Any]: 包含成员信息的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (list): 成员信息列表，每个成员包含：
                    - id (int): 成员ID
                    - entity_id (int): 实体ID
                    - entity_name (str): 用户名
                    - entity_type (str): 实体类型（通常为'u'表示用户）
                    - role_id (int): 角色ID
                    - role_name (str): 角色名称
                    - creation_time (str): 添加时间
                    - update_time (str): 更新时间

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取项目成员
            result = harbor_client.get_project_members("k8s")

            if result["status"]:
                members = result["data"]
                for member in members:
                    print(f"用户名: {member['entity_name']}")
                    print(f"角色: {member['role_name']}")
                    print(f"添加时间: {member['creation_time']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 需要项目访问权限才能查看成员
            - 角色ID对应不同的权限级别
            - 如果项目没有成员，返回空列表
            - 建议结合add_project_member管理项目成员
        """
        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}/members?page=1&page_size=10"
            response = self.request("GET", url)
            if response.status_code == 200:
                return self.return_response(
                    True, response.status_code, "获取项目成员成功", response.json()
                )
            else:
                return self.return_response(
                    False, response.status_code, "获取项目成员失败", response.json()
                )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目成员异常: {str(e)}")

    def add_project_member(
        self, project_name: str, username: str, role: str = 1
    ) -> Dict[str, Any]:
        """
        向指定项目添加新成员

        该方法会将指定的用户添加到项目中，并分配相应的角色权限。
        用户添加成功后，将具有访问项目资源的权限。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 当前用户必须具有项目管理权限
                - 示例：'k8s', 'my-project'

            username (str): 要添加的用户名
                - 必须是Harbor中已存在的用户名
                - 用户名区分大小写
                - 用户不能已经是项目成员
                - 示例：'developer001', 'test-user'

            role (str, optional): 用户角色ID
                - 默认值：1（项目开发者）
                - 可选值：
                    - 1: 项目开发者（Project Developer）
                    - 2: 项目维护者（Project Maintainer）
                    - 3: 项目管理员（Project Admin）
                - 示例：1, 2, 3

        Returns:
            Dict[str, Any]: 包含添加结果的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 添加用户为项目开发者
            result = harbor_client.add_project_member(
                project_name="k8s",
                username="developer001",
                role=1
            )

            # 添加用户为项目管理员
            admin_result = harbor_client.add_project_member(
                project_name="k8s",
                username="admin001",
                role=3
            )

            if result["status"]:
                print(f"成员添加成功: {result['message']}")
            else:
                print(f"成员添加失败: {result['message']}")

        Note:
            - 需要项目管理权限才能添加成员
            - 用户不能重复添加到同一项目
            - 角色权限从低到高：开发者 < 维护者 < 管理员
            - 建议根据用户职责分配适当的角色
            - 添加后用户立即具有相应权限
        """
        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}/members"
            response = self.request(
                "POST",
                url,
                json={
                    "member_user": {"username": username},
                    "role_id": role,
                },
            )
            if response.status_code == 201:
                return self.return_response(
                    True, response.status_code, "添加项目成员成功", response.text
                )
            else:
                return self.return_response(
                    False, response.status_code, "添加项目成员失败", response.text
                )
        except Exception as e:
            return self.return_response(False, 500, f"添加项目成员异常: {str(e)}")

    def get_repository_artifacts(
        self, project_name: str, repository_name: str
    ) -> Dict[str, Any]:
        """
        获取指定仓库中所有镜像的标签和详细信息

        该方法会查询指定仓库中的所有镜像，包括标签、大小、推送时间、
        扫描概览等详细信息。支持嵌套目录仓库名的双重URL编码。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 示例：'k8s', 'my-project'

            repository_name (str): 仓库名称
                - 可以是简单名称或包含路径的名称
                - 如果包含路径分隔符'/'，系统会自动进行双重URL编码
                - 示例：'nginx', 'core/kube-calico-controllers'

        Returns:
            Dict[str, Any]: 包含镜像信息的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data (list): 镜像信息列表，每个镜像包含：
                    - id (int): 镜像ID
                    - type (str): 镜像类型
                    - media_type (str): 媒体类型
                    - manifest_media_type (str): 清单媒体类型
                    - size (int): 镜像大小（字节）
                    - tags (list): 标签列表
                        - name (str): 标签名称
                        - push_time (str): 推送时间
                    - scan_overview (dict): 安全扫描概览
                    - sbom_overview (dict): SBOM概览
                    - labels (list): 标签列表

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 获取简单名称仓库的镜像
            result = harbor_client.get_repository_artifacts(
                project_name="k8s",
                repository_name="nginx"
            )

            # 获取嵌套目录仓库的镜像
            result = harbor_client.get_repository_artifacts(
                project_name="k8s",
                repository_name="core/kube-calico-controllers"
            )

            if result["status"]:
                artifacts = result["data"]
                for artifact in artifacts:
                    print(f"镜像ID: {artifact['id']}")
                    print(f"大小: {artifact['size']} 字节")
                    for tag in artifact.get('tags', []):
                        print(f"  标签: {tag['name']}")
                        print(f"  推送时间: {tag['push_time']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 支持嵌套目录仓库名的双重URL编码
            - 默认返回前15个镜像（page_size=15）
            - 镜像大小以字节为单位，需要自行转换为GB
            - 包含安全扫描和SBOM信息（如果启用）
            - 建议结合get_project_repositories获取仓库列表
        """
        # 双重编码
        # Harbor 的 OpenAPI 文档 中虽然要求路径参数 / 编成 %2F，但在实际部署中（特别是带有反向代理或路径正则校验的配置），有时必须双重编码 %252F 才能识别嵌套目录仓库名。
        if "/" in repository_name:
            encoded_repo = quote(quote(repository_name, safe=""), safe="")
        else:
            encoded_repo = repository_name
        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}/repositories/{encoded_repo}/artifacts"
            params = {
                "with_tag": "true",
                "with_scan_overview": "false",
                "with_sbom_overview": "false",
                "with_label": "true",
                "with_immutable_status": "false",
                "with_accessory": "false",
                "page_size": 100,
                "page": 1,
            }
            response = self.request("GET", url, params=params)
            if response.status_code == 200:
                return self.return_response(
                    True, response.status_code, "获取项目仓库标签成功", response.json()
                )
            else:
                return self.return_response(
                    False, response.status_code, "获取项目仓库标签失败", response.json()
                )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目仓库标签异常: {str(e)}")

    def update_project_quotas(
        self, quota_id: int, storage_limit: int
    ) -> Dict[str, Any]:
        """
        更新指定项目的存储配额限制

        该方法会更新指定配额ID对应的项目存储限制，支持动态调整
        项目的存储配额。存储限制以GB为单位，系统会自动转换为字节。

        Args:
            quota_id (int): 配额ID
                - 必须是有效的配额ID
                - 可以通过get_all_quotas方法获取
                - 示例：123, 456

            storage_limit (int): 新的存储限制，单位为GB
                - 范围：通常为1-1000 GB
                - 必须大于当前已使用的存储空间
                - 系统会自动转换为字节单位
                - 示例：50 表示50GB存储限制

        Returns:
            Dict[str, Any]: 包含更新结果的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 更新项目存储限制为50GB
            result = harbor_client.update_project_quotas(123, 50)

            if result["status"]:
                print(f"配额更新成功: {result['message']}")
            else:
                print(f"配额更新失败: {result['message']}")

        Note:
            - 配额ID必须通过get_all_quotas方法获取
            - 存储限制以GB为单位，系统自动转换为字节
            - 新的限制必须大于已使用的存储空间
            - 建议在更新前检查当前使用情况
        """
        try:
            url = f"{self.base_url}/api/v2.0/quotas/{quota_id}"
            response = self.request(
                "PUT",
                url,
                json={"hard": {"storage": storage_limit * 1024 * 1024 * 1024}},
            )
            if response.status_code == 200:
                return self.return_response(
                    True,
                    response.status_code,
                    "更新项目配额成功",
                )
            else:
                return self.return_response(
                    False, response.status_code, "更新项目配额失败", response.json()
                )
        except Exception as e:
            return self.return_response(False, 500, f"更新项目配额异常: {str(e)}")

    # 自定义镜像仓库添加接口
    def add_custom_projects(
        self, project_name: str, public: str, storage_limit: int
    ) -> Dict[str, Any]:
        """
        在Harbor中创建新的自定义镜像仓库项目

        该方法会创建一个新的项目，支持设置项目的公开性和存储限制。
        项目创建成功后，可以用于存储和管理Docker镜像。

        Args:
            project_name (str): 项目名称
                - 长度限制：1-63个字符
                - 字符限制：只能包含小写字母、数字、连字符和下划线
                - 唯一性：项目名称在系统中必须唯一
                - 示例：'my-project', 'test-repo-123'

            public (str): 项目是否公开
                - 可选值：'true' 或 'false'
                - 'true': 所有用户都可以拉取镜像（无需认证）
                - 'false': 只有项目成员可以拉取镜像
                - 示例：'false' 表示私有项目

            storage_limit (int): 项目存储限制，单位为GB
                - 范围：通常为1-1000 GB
                - 建议：根据实际需求设置，避免资源浪费
                - 系统会自动转换为字节单位
                - 示例：20 表示20GB存储限制

        Returns:
            Dict[str, Any]: 包含创建结果的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 创建一个私有的20GB存储限制项目
            result = harbor_client.add_custom_projects(
                project_name="my-private-repo",
                public="false",
                storage_limit=20
            )

            if result["status"]:
                print(f"项目创建成功: {result['message']}")
            else:
                print(f"项目创建失败: {result['message']}")
                if result.get("data"):
                    print(f"错误详情: {result['data']}")

        Note:
            - 项目名称在系统中必须唯一
            - 存储限制以GB为单位，系统自动转换为字节
            - 公开性设置会立即生效
            - 项目创建后需要手动添加成员
            - 建议在生产环境中使用有意义的项目名称
        """
        try:
            url = f"{self.base_url}/api/v2.0/projects"
            response = self.request(
                "POST",
                url,
                json={
                    "project_name": f"{project_name}",
                    "public": bool(public),
                    "metadata": {
                        "public": f"{public}",
                    },
                    "storage_limit": storage_limit,
                },
            )
            if response.status_code == 201:
                return self.return_response(
                    True,
                    response.status_code,
                    f"自定义镜像仓库添加成功: {project_name}",
                )
            else:
                if response.json().get("errors"):
                    return self.return_response(
                        False,
                        response.status_code,
                        f"自定义镜像仓库添加失败: {project_name}",
                        response.json().get("errors")[0].get("message"),
                    )
                else:
                    return self.return_response(
                        False,
                        response.status_code,
                        f"自定义镜像仓库添加失败: {project_name}",
                        response.json(),
                    )
        except Exception as e:
            return self.return_response(False, 500, f"添加自定义镜像仓库异常: {str(e)}")

    # 自定义镜像仓库修改接口
    # 仓库大小无法使用该接口更改，通过单独调用update_project_quotas接口更改
    def update_custom_projects(self, project_name: str, public: str) -> Dict[str, Any]:
        """
        更新自定义镜像仓库项目的配置信息

        该方法会更新指定项目的公开性设置。注意：存储限制的更新
        需要通过单独的配额管理接口来实现。

        Args:
            project_name (str): 要更新的项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 示例：'my-project', 'test-repo'

            public (str): 项目是否公开
                - 可选值：'true' 或 'false'
                - 'true': 所有用户都可以拉取镜像（无需认证）
                - 'false': 只有项目成员可以拉取镜像
                - 示例：'false' 表示私有项目

        Returns:
            Dict[str, Any]: 包含更新结果的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 更新项目为私有
            result = harbor_client.update_custom_projects(
                project_name="my-project",
                public="false"
            )

            # 更新项目为公开
            result = harbor_client.update_custom_projects(
                project_name="my-project",
                public="true"
            )

            if result["status"]:
                print(f"项目更新成功: {result['message']}")
            else:
                print(f"项目更新失败: {result['message']}")
                if result.get("data"):
                    print(f"错误详情: {result['data']}")

        Note:
            - 只能更新项目的公开性设置
            - 存储限制需要通过update_project_quotas接口更新
            - 公开性设置会立即生效
            - 建议在更新前检查当前项目状态
        """

        try:
            # 更新是否公开
            url = f"{self.base_url}/api/v2.0/projects/{project_name}"
            payload = {
                "project_name": f"{project_name}",
                "public": True if public == 'true' else False,
                "metadata": {
                    "public": 'true' if public == 'true' else 'false',
                },
            }
            response = self.request("PUT", url, json=payload)
            if response.status_code == 200:
                return self.return_response(
                    True,
                    response.status_code,
                    f"自定义镜像仓库更新成功: {project_name}",
                )
            else:
                if response.json().get("errors"):
                    return self.return_response(
                        False,
                        response.status_code,
                        f"自定义镜像仓库更新失败: {project_name}",
                        response.json().get("errors")[0].get("message"),
                    )
                else:
                    return self.return_response(
                        False,
                        response.status_code,
                        f"自定义镜像仓库更新失败: {project_name}",
                        response.json(),
                    )
        except Exception as e:
            return self.return_response(False, 500, f"修改自定义镜像仓库异常: {str(e)}")

    # 自定义镜像仓库删除接口
    def delete_custom_projects(self, project_name: str) -> Dict[str, Any]:
        """
        删除指定的自定义镜像仓库项目

        该方法会永久删除指定的项目及其所有相关的镜像仓库、标签、
        配置信息和成员关系。删除操作不可逆，请谨慎使用。

        Args:
            project_name (str): 要删除的项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 删除前请确认项目名称正确
                - 示例：'test-project', 'old-repo'

        Returns:
            Dict[str, Any]: 包含删除结果的响应字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当API调用失败时抛出异常

        Example:
            # 删除指定的项目
            result = harbor_client.delete_custom_projects("test-project")

            if result["status"]:
                print(f"项目删除成功: {result['message']}")
            else:
                print(f"项目删除失败: {result['message']}")
                if result.get("data"):
                    print(f"错误详情: {result['data']}")

        Note:
            - 删除操作不可逆，请谨慎使用
            - 删除前请确保项目中没有重要的镜像数据
            - 建议在删除前备份重要的镜像数据
            - 删除后项目下的所有仓库和镜像都将丢失
            - 项目成员关系也会被删除
        """
        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}"
            response = self.request("DELETE", url)
            if response.status_code == 200:
                return self.return_response(
                    True,
                    response.status_code,
                    f"自定义镜像仓库删除成功: {project_name}",
                )
            else:
                return self.return_response(
                    False,
                    response.status_code,
                    f"自定义镜像仓库删除失败: {project_name}",
                    response.json().get("errors", "未知错误"),
                )
        except Exception as e:
            return self.return_response(False, 500, f"删除自定义镜像仓库异常: {str(e)}")

    # 删除自定义仓库镜像TAG
    def delete_custom_projects_images_tag(self, project_name: str, repository_name: str,digest: str) -> Dict[str, Any]:
        if "/" in repository_name:
            encoded_repo = quote(quote(repository_name, safe=""), safe="")
        else:
            encoded_repo = repository_name

        try:
            url = f"{self.base_url}/api/v2.0/projects/{project_name}/repositories/{encoded_repo}/artifacts/{digest}"
            response = self.request("DELETE", url)
            if response.status_code == 200:
                return self.return_response(
                    True,
                    response.status_code,
                    f"自定义镜像仓库Tag删除成功: {repository_name}",
                )
            else:
                return self.return_response(
                    False,
                    response.status_code,
                    f"自定义镜像仓库Tag删除失败: {repository_name}",
                    response.json().get("errors", "未知错误"),
                )
        except Exception as e:
            return self.return_response(False, 500, f"删除自定义镜像仓库异常: {str(e)}")

    # 获取项目标签
    def get_public_projects_labels(self, project_id: int, page: int = 1, page_size: int = 100, get_all: bool = False) -> Dict[str, Any]:
        try:
            if get_all:
                all_labels = []
                while True:
                    url = f"{self.base_url}/api/v2.0/labels"
                    response = self.request("GET", url, params={"page": page, "page_size": page_size, "project_id": project_id,"scope":"p"})
                    if response.status_code == 200:
                        all_labels.extend(response.json())
                        if len(response.json()) < page_size:
                            break
                        page += 1
                return self.return_response(
                    True,
                    response.status_code,
                    "获取项目标签成功",
                    all_labels,
                )
            else:   
                url = f"{self.base_url}/api/v2.0/labels"
                response = self.request("GET", url, params={"page": page, "page_size": page_size, "project_id": project_id,"scope":"p"})
                if response.status_code == 200:
                    return self.return_response(
                        True,
                        response.status_code,
                        "获取项目标签成功",
                        response.json(),
                    )
                else:
                    return self.return_response(
                        False,
                        response.status_code,
                        "获取项目标签失败",
                        response.json(),
                    )
        except Exception as e:
            return self.return_response(False, 500, f"获取项目标签异常: {str(e)}")