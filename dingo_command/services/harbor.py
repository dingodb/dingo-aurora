from re import S
from dingo_command.common.harbor_client import HarborAPI
from typing import Any

from dingo_command.common import CONF

base_url = CONF.harbor.base_url
clean_url = base_url.split("://", 1)[-1]
private_project_storage_limit = CONF.harbor.storage_limit

# 获取公共基础镜像
class HarborService:
    """
    Harbor服务管理类

    该类提供了与Harbor容器镜像仓库交互的高级接口，包括：
    - 用户管理：创建Harbor用户账户
    - 项目管理：创建、更新、删除自定义镜像仓库项目
    - 镜像查询：获取公共基础镜像和自定义项目镜像信息
    - 镜像管理：删除指定的镜像仓库

    主要功能：
    1. 用户管理：支持创建新用户，设置用户信息和权限
    2. 项目管理：支持创建、更新、删除私有/公有项目，设置存储限制
    3. 镜像查询：支持查询公共基础镜像和自定义项目的详细信息
    4. 镜像管理：支持删除指定的镜像仓库

    Attributes:
        harbor (HarborAPI): Harbor API客户端实例，用于与Harbor服务通信

    Example:
        # 创建Harbor服务实例
        harbor_service = HarborService()

        # 创建新用户
        user_result = harbor_service.add_harbor_user(
            username="dev001",
            password="SecurePass123!",
            email="dev@example.com"
        )

        # 创建自定义项目
        project_result = harbor_service.add_custom_projects(
            project_name="my-project",
            public="false",
            storage_limit=50,
            user_name="dev001"
        )

        # 更新项目配置
        update_result = harbor_service.update_custom_projects(
            project_name="my-project",
            public="true",
            storage_limit=100
        )

        # 获取用户参与的项目
        projects_result = harbor_service.get_custom_projects("dev001")

        # 获取项目镜像
        images_result = harbor_service.get_custom_projects_images("my-project")

        # 删除镜像仓库
        delete_result = harbor_service.delete_custom_projects_images(
            project_name="my-project",
            repository_name="nginx"
        )

        # 删除项目
        delete_project_result = harbor_service.delete_custom_projects("my-project")

    Note:
        - 所有方法都返回统一的响应格式
        - 需要确保Harbor服务可访问且配置正确
        - 建议在生产环境中使用HTTPS连接
        - 删除操作不可逆，请谨慎使用
    """

    def __init__(self):
        """
        初始化Harbor服务

        创建HarborAPI客户端实例，用于与Harbor服务进行通信。
        客户端将使用配置中心中的Harbor配置信息。
        """
        self.harbor = HarborAPI()

    def return_response(
        self, status: bool, code: int, message: str, data: Any = None
    ) -> dict:
        """
        生成统一的响应格式

        该方法用于生成所有Harbor服务方法的统一响应格式，
        确保返回数据结构的一致性。

        Args:
            status (bool): 操作是否成功
            code (int): HTTP状态码或自定义错误码
            message (str): 操作结果描述或错误信息
            data (Any, optional): 返回的数据，默认为None

        Returns:
            dict: 统一格式的响应字典
                - status (bool): 操作状态
                - code (int): 状态码
                - message (str): 消息描述
                - data (Any): 返回数据

        Example:
            # 成功响应
            success_response = self.return_response(
                status=True,
                code=200,
                message="操作成功",
                data={"id": 123, "name": "test"}
            )

            # 错误响应
            error_response = self.return_response(
                status=False,
                code=404,
                message="资源不存在"
            )
        """
        return {
            "status": status,
            "code": code,
            "message": message,
            "data": data,
        }

    # 获取公共基础镜像
    def get_public_base_image(
        self,
        project_name: str = "anc-public",
        public_image_name="",
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """
        获取公共基础镜像仓库信息

        该方法会从Harbor的'k8s'项目中获取所有公共基础镜像的信息，
        包括仓库名称、标签、大小和推送时间等详细信息。

        Returns:
            dict: 包含公共基础镜像信息的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码，成功时为200
                - message (str): 操作结果描述
                - data (list): 镜像仓库列表，每个元素包含：
                    - name (str): 完整仓库名称
                    - repository_name (str): 去除项目前缀的仓库名称
                    - project_name (str): 项目名称（固定为'k8s'）
                    - tags_list (list): 标签信息列表，每个标签包含：
                        - tag_name (str): 标签名称
                        - tag_push_time (str): 推送时间
                        - size (str): 格式化后的镜像大小（GB或MB）

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 获取所有公共基础镜像
            result = harbor_service.get_public_base_image()

            if result["status"]:
                images = result["data"]
                for image in images:
                    print(f"仓库: {image['repository_name']}")
                    print(f"项目: {image['project_name']}")
                    for tag in image['tags_list']:
                        print(f"  标签: {tag['tag_name']}")
                        print(f"  大小: {tag['size']}")
                        print(f"  推送时间: {tag['tag_push_time']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 该方法专门用于获取'k8s'项目中的公共基础镜像
            - 镜像大小会自动格式化为GB或MB单位
            - 如果镜像没有标签，tag_name和tag_push_time将显示为'none'
            - 返回的数据结构经过优化，便于前端展示和处理
        """

        # 搜索项目
        repo_count = 0
        search_response = self.harbor.search(project_name)
        if search_response["status"]:
            projects = search_response["data"]["project"]
            if len(projects) > 0:
                for project in projects:
                    if project["name"] == project_name:
                        repo_count = project["repo_count"]
            else:
                return self.return_response(False, 400, "项目不存在")
        else:
            return self.return_response(False, 400, "搜索项目失败")
        
        if public_image_name:
            # project_repositories = self.harbor.get_project_repository(
            #     project_name, public_image_name, page=page, page_size=page_size
            # )
            project_repositories = self.harbor.get_project_repositories(
                project_name, page=page, page_size=page_size, get_all=True
            )
            if not project_repositories["status"]:
                return project_repositories

            project_repositories_list = []

            # 处理每个镜像仓库
            for repository in project_repositories["data"]:
                # 提取仓库名称（去除项目前缀）
                repository_name = repository["name"].replace(
                    f"{project_name}/", "", 1
                )  # 只替换第一个

                if public_image_name in repository_name:
                    # 更新仓库信息
                    repository.update(dict(repository_name=repository_name))
                    repository.update(dict(project_name=project_name))
                    repository.update(
                        dict(
                            pull_command=f"docker pull {clean_url}/{project_name}/{repository_name}"
                        )
                    )
                    repository.update(dict(image_url=clean_url))

                    # 获取镜像仓库的标签和详细信息
                    public_project_artifacts = self.harbor.get_repository_artifacts(
                        project_name, repository_name
                    )

                    tags_list = []
                    # 处理每个镜像标签
                    for artifact in public_project_artifacts["data"]:
                        tags = artifact.get("tags", [])
                        tags_dic = {}

                        if tags:
                            # 获取标签信息
                            tag_name = tags[0]["name"]
                            tag_push_time = tags[0]["push_time"]
                            tags_dic = dict(
                                tag_name=tag_name, tag_push_time=tag_push_time
                            )
                        else:
                            # 没有标签的情况
                            tags_dic = dict(tag_name="none", tag_push_time="none")

                        # 获取并格式化镜像大小
                        size_bytes = artifact.get("size", 0)
                        # 根据大小动态选择单位
                        if size_bytes >= 1024 * 1024 * 1024:  # 大于等于1GB
                            size_formatted = (
                                f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
                            )
                        else:  # 小于1GB，使用MB
                            size_formatted = f"{size_bytes / (1024 * 1024):.2f} MB"

                        tags_dic.update(dict(size=size_formatted))
                        tags_list.append(tags_dic)

                    # 更新仓库的标签信息
                    repository.update(dict(tags_list=tags_list))
                    project_repositories_list.append(repository)

            return self.return_response(
                True, 200, "获取镜像成功", project_repositories_list
            )

        else:
            project_repositories = self.harbor.get_project_repositories(
                project_name, page=page, page_size=page_size, get_all=False
            )

            if not project_repositories["status"]:
                return project_repositories

            project_repositories_list = []

            # 处理每个镜像仓库
            for repository in project_repositories["data"]:
                # 提取仓库名称（去除项目前缀）
                repository_name = repository["name"].replace(
                    f"{project_name}/", "", 1
                )  # 只替换第一个

                # 更新仓库信息
                repository.update(dict(repository_name=repository_name))
                repository.update(dict(project_name=project_name))
                repository.update(
                    dict(
                        pull_command=f"docker pull {clean_url}/{project_name}/{repository_name}"
                    )
                )
                repository.update(dict(image_url=clean_url))

                # 获取镜像仓库的标签和详细信息
                public_project_artifacts = self.harbor.get_repository_artifacts(
                    project_name, repository_name
                )

                tags_list = []
                # 处理每个镜像标签
                for artifact in public_project_artifacts["data"]:
                    tags = artifact.get("tags", [])
                    tags_dic = {}

                    if tags:
                        # 获取标签信息
                        tag_name = tags[0]["name"]
                        tag_push_time = tags[0]["push_time"]
                        tags_dic = dict(tag_name=tag_name, tag_push_time=tag_push_time)
                    else:
                        # 没有标签的情况
                        tags_dic = dict(tag_name="none", tag_push_time="none")

                    # 获取并格式化镜像大小
                    size_bytes = artifact.get("size", 0)
                    # 根据大小动态选择单位
                    if size_bytes >= 1024 * 1024 * 1024:  # 大于等于1GB
                        size_formatted = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
                    else:  # 小于1GB，使用MB
                        size_formatted = f"{size_bytes / (1024 * 1024):.2f} MB"

                    tags_dic.update(dict(size=size_formatted))
                    tags_list.append(tags_dic)

                # 更新仓库的标签信息
                repository.update(dict(tags_list=tags_list))
                project_repositories_list.append(repository)

            # return self.return_response(
            #     True, 200, "获取镜像成功", project_repositories_list
            # )
            return {
                "status": True,
                "code": 200,
                "message": "获取公共仓库镜像成功",
                "page_size": repo_count,
                "data": project_repositories_list,
            }

    # 添加harbor用户
    def add_harbor_user(
        self,
        username: str,
        password: str,
        email: str,
        realname: str = "",
        comment: str = "",
    ) -> dict:
        """
        在Harbor中创建新用户

        该方法会在Harbor用户管理系统中创建一个新的用户账户，
        新用户默认具有普通用户权限（非管理员）。

        Args:
            username (str): 用户名，用于登录Harbor
                - 长度限制：通常为3-30个字符
                - 字符限制：只能包含字母、数字、连字符和下划线
                - 唯一性：用户名在系统中必须唯一
                - 示例：'developer001', 'test-user'

            password (str): 用户密码
                - 长度要求：通常至少6个字符
                - 复杂度建议：包含大小写字母、数字和特殊字符
                - 安全建议：避免使用常见密码
                - 示例：'MySecurePass123!'

            email (str): 用户邮箱地址
                - 格式要求：必须是有效的邮箱格式
                - 用途：用于密码重置和通知
                - 唯一性：邮箱在系统中应该唯一
                - 示例：'user@example.com'

            realname (str, optional): 用户真实姓名
                - 默认值：空字符串
                - 用途：用于显示和识别用户
                - 示例：'张三', 'John Doe'

            comment (str, optional): 用户备注信息
                - 默认值：空字符串
                - 用途：记录用户相关信息，如部门、职位等
                - 示例：'开发部门', 'QA工程师'

        Returns:
            dict: 包含用户创建结果的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 创建一个新的开发用户
            result = harbor_service.add_harbor_user(
                username="dev001",
                password="DevPass123!",
                email="dev001@company.com",
                realname="张三",
                comment="开发部门"
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
        """
        result = self.harbor.create_user(
            username=username,
            email=email,
            password=password,
            realname=realname,
            comment=comment,
            admin=False,
        )
        return result

    # 添加自定义镜像仓库
    def add_custom_projects(
        self, project_name: str, public: str, storage_limit: int, user_name: str
    ) -> dict:
        """
        添加自定义镜像仓库项目并分配用户权限

        该方法会执行以下操作：
        1. 在Harbor中创建一个新的镜像仓库项目
        2. 设置项目的公开性和存储限制
        3. 将指定用户添加为项目成员

        Args:
            project_name (str): 项目名称，用于标识镜像仓库项目
                - 长度限制：通常为1-63个字符
                - 字符限制：只能包含小写字母、数字、连字符和下划线
                - 示例：'my-project', 'test-repo-123'

            public (str): 项目是否公开
                - 可选值：'true' 或 'false'
                - 'true': 所有用户都可以拉取镜像
                - 'false': 只有项目成员可以拉取镜像
                - 示例：'false' 表示私有项目

            storage_limit (int): 项目存储限制，单位为GB
                - 范围：通常为1-1000 GB
                - 建议：根据实际需求设置，避免资源浪费
                - 示例：20 表示20GB存储限制

            user_name (str): 要添加到项目的用户名
                - 必须是Harbor中已存在的用户
                - 用户将被分配默认的项目成员权限
                - 示例：'user_rkvu5rmv', 'developer001'

        Returns:
            dict: 包含操作结果的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 创建一个私有的20GB存储限制的镜像仓库项目
            result = harbor_service.add_custom_projects(
                project_name="my-private-repo",
                public="false",
                storage_limit=20,
                user_name="developer001"
            )

            if result["status"]:
                print(f"项目创建成功: {result['message']}")
            else:
                print(f"项目创建失败: {result['message']}")

        Note:
            - 项目创建成功后，用户将自动成为项目成员
            - 存储限制以GB为单位，系统会自动转换为字节
            - 如果项目名称已存在，操作将失败
            - 建议在生产环境中使用有意义的项目名称
        """
        # 检查仓库配额限制，是否超出限制100GB
        all_quota = private_project_storage_limit * 1024 * 1024 * 1024
        storage_limit = storage_limit * 1024 * 1024 * 1024
        get_custom_projects_response = self.get_custom_projects(user_name)
        total_hard = sum(project['quota_info']['hard'] for project in get_custom_projects_response["data"])
        if total_hard + storage_limit > all_quota:
            return self.return_response(False, 400, "仓库配额超出限制100GB")
        
        # 创建自定义镜像仓库项目
        add_custom_projects_response = self.harbor.add_custom_projects(
            project_name, public, storage_limit
        )

        # 检查项目创建是否成功
        if add_custom_projects_response["status"]:
            # 项目创建成功，添加用户为项目成员
            add_project_member_response = self.harbor.add_project_member(
                project_name, user_name
            )

            # 更新成功消息，包含项目名称信息
            add_project_member_response["message"] = (
                f"自定义镜像仓库添加成功: {project_name}"
            )

            return add_project_member_response
        else:
            # 项目创建失败，返回错误信息
            return add_custom_projects_response

    # 更新自定义镜像仓库
    def update_custom_projects(
        self, project_name: str, public: str, storage_limit: int, user_name: str
    ) -> dict:
        """
        更新自定义镜像仓库项目的配置信息

        该方法会更新指定项目的公开性和存储限制。注意：存储限制的更新
        需要通过单独的配额管理接口来实现。

        Args:
            project_name (str): 要更新的项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 示例：'my-project', 'test-repo'

            public (str): 项目是否公开
                - 可选值：'true' 或 'false'
                - 'true': 所有用户都可以拉取镜像
                - 'false': 只有项目成员可以拉取镜像
                - 示例：'false' 表示私有项目

            storage_limit (int): 项目存储限制，单位为GB
                - 范围：通常为1-1000 GB
                - 必须大于当前已使用的存储空间
                - 示例：50 表示50GB存储限制
            
            user_name (str): 要更新项目的用户名
                - 必须是Harbor中已存在的用户名
                - 用户名区分大小写
                - 示例：'developer001', 'user_rkvu5rmv'

        Returns:
            dict: 包含更新结果的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 更新项目为私有并设置50GB存储限制
            result = harbor_service.update_custom_projects(
                project_name="my-project",
                public="false",
                storage_limit=50,
                user_name="developer001"
            )

            if result["status"]:
                print(f"项目更新成功: {result['message']}")
            else:
                print(f"项目更新失败: {result['message']}")

        Note:
            - 存储限制的更新通过配额管理接口实现
            - 公开性设置会立即生效
            - 建议在更新前检查当前存储使用情况
            - 存储限制不能小于已使用的存储空间
        """
        # 检查仓库配额限制，是否超出限制100GB
        all_quota = private_project_storage_limit * 1024 * 1024 * 1024
        get_custom_projects_response = self.get_custom_projects(user_name)
        total_hard = 0
        project_name_list = []
        for i in get_custom_projects_response["data"]:
            if i['name'] == project_name:
                total_hard += storage_limit * 1024 * 1024 * 1024
            else:
                total_hard += i['quota_info']['hard']
            project_name_list.append(i['name'])
        if project_name not in project_name_list:
            return self.return_response(False, 400, f"仓库不存在: {project_name}")
        if total_hard > all_quota:
            return self.return_response(False, 400, f"仓库配额超出限制100GB: {project_name}")

        # 更新项目公开性设置
        update_custom_projects_response = self.harbor.update_custom_projects(
            project_name, public
        )

        if update_custom_projects_response["status"]:
            # 仓库大小无法使用该接口更改，通过单独调用update_project_quotas接口更改
            quotas = self.harbor.get_all_quotas()
            for quota in quotas["data"]:
                if quota["ref"].get("name") == project_name:
                    quota_id = quota["id"]
                    update_project_quotas_response = self.harbor.update_project_quotas(
                        quota_id, storage_limit
                    )
                    if update_project_quotas_response["status"]:
                        update_custom_projects_response["message"] = (
                            f"仓库 {project_name} 更新成功"
                        )
                        return update_custom_projects_response
                    else:
                        update_custom_projects_response["message"] = (
                            f"仓库 {project_name} 更新失败"
                        )
                        return update_custom_projects_response
        else:
            return update_custom_projects_response

    # 获取自定义镜像仓库
    # Harbor 的 GET /projects?owner=username 参数并不是用来查询"某个用户参与的项目"，而是用来查询"某个用户创建的项目"。
    # 但是在实际使用中，大多数用户不是用 UI 创建项目，而是管理员创建后把用户加入为成员。此时，用户不是项目 owner，只是成员，所以这个 API 返回为空
    def get_custom_projects(self, user_name: str) -> dict:
        """
        获取指定用户参与的所有自定义镜像仓库项目信息

        该方法会查询指定用户作为成员参与的所有项目，包括项目基本信息、
        存储配额使用情况和仓库数量等详细信息。

        注意：Harbor的GET /projects?owner=username接口只能查询用户创建的项目，
        无法查询用户作为成员参与的项目，因此需要通过遍历所有项目来查找。

        Args:
            user_name (str): 要查询的用户名
                - 必须是Harbor中已存在的用户名
                - 用户名区分大小写
                - 示例：'developer001', 'user_rkvu5rmv'

        Returns:
            dict: 包含用户参与项目信息的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码，成功时为200
                - message (str): 操作结果描述
                - data (list): 项目信息列表，每个项目包含：
                    - creation_time (str): 项目创建时间
                    - name (str): 项目名称
                    - quota_info (dict): 存储配额信息
                        - hard (int): 存储限制（字节）
                        - used (int): 已使用存储（字节）
                    - repo_count (int): 仓库数量
                    - project_id (int): 项目ID

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 获取用户参与的所有项目
            result = harbor_service.get_custom_projects("developer001")

            if result["status"]:
                projects = result["data"]
                for project in projects:
                    print(f"项目名称: {project['name']}")
                    print(f"创建时间: {project['creation_time']}")
                    print(f"仓库数量: {project['repo_count']}")

                    quota = project['quota_info']
                    hard_gb = quota['hard'] / (1024**3) if quota['hard'] else 0
                    used_gb = quota['used'] / (1024**3) if quota['used'] else 0
                    print(f"存储限制: {hard_gb:.2f} GB")
                    print(f"已使用: {used_gb:.2f} GB")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 该方法通过遍历所有项目来查找用户参与的项目
            - 性能取决于项目总数，建议在项目数量较多时进行分页处理
            - 返回的存储大小以字节为单位，需要自行转换为GB
            - 如果用户没有参与任何项目，返回空列表
        """
        custom_prjects_response = self.return_response(
            True, 200, "获取自定义镜像仓库成功", ""
        )
        custom_projects_list = []

        # 获取自定义仓库配额信息
        get_all_quotas_response = self.harbor.get_all_quotas()

        # 获取所有项目，判断用户是否为项目成员
        get_projects_response = self.harbor.get_projects()
        if get_projects_response["status"]:
            for project in get_projects_response["data"]:
                project_name = project["name"]
                # 获取项目成员
                project_members_response = self.harbor.get_project_members(project_name)
                if project_members_response["status"]:
                    for member in project_members_response["data"]:
                        if member["entity_name"] == user_name:
                            # 获取自定义镜像仓库
                            get_project_info_response = self.harbor.get_project_info(
                                project_name
                            )

                            # 获取仓库配额信息
                            for quota in get_all_quotas_response["data"]:
                                if quota["ref"].get("name") == project_name:
                                    quota_id = quota["id"]
                                    get_project_quotas_response = (
                                        self.harbor.get_project_quotas(quota_id)
                                    )
                                    if get_project_quotas_response["status"]:
                                        quota_info = get_project_quotas_response["data"]
                                        hard = quota_info["hard"].get("storage")
                                        used = quota_info["used"].get("storage")
                                        temp_dict = {
                                            "creation_time": get_project_info_response[
                                                "data"
                                            ]["creation_time"],
                                            "name": get_project_info_response["data"][
                                                "name"
                                            ],
                                            "quota_info": (
                                                dict(
                                                    hard=hard,
                                                    used=used,
                                                )
                                            ),
                                            "repo_count": get_project_info_response[
                                                "data"
                                            ]["repo_count"],
                                            "project_id": get_project_info_response[
                                                "data"
                                            ]["project_id"],
                                        }
                                        custom_projects_list.append(temp_dict)
                else:
                    return project_members_response
        else:
            return get_projects_response

        custom_prjects_response["data"] = custom_projects_list
        return custom_prjects_response

    # 删除自定义镜像仓库
    def delete_custom_projects(self, project_name: str) -> dict:
        """
        删除指定的自定义镜像仓库项目

        该方法会永久删除指定的项目及其所有相关的镜像仓库、标签和配置信息。
        删除操作不可逆，请谨慎使用。

        Args:
            project_name (str): 要删除的项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 删除前请确认项目名称正确
                - 示例：'test-project', 'old-repo'

        Returns:
            dict: 包含删除结果的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 删除指定的项目
            result = harbor_service.delete_custom_projects("test-project")

            if result["status"]:
                print(f"项目删除成功: {result['message']}")
            else:
                print(f"项目删除失败: {result['message']}")

        Note:
            - 删除操作不可逆，请谨慎使用
            - 删除前请确保项目中没有重要的镜像数据
            - 建议在删除前备份重要的镜像数据
            - 删除后项目下的所有仓库和镜像都将丢失
        """
        delete_custom_projects_response = self.harbor.delete_custom_projects(
            project_name
        )
        return delete_custom_projects_response

    # 获取指定自定义仓库镜像
    def get_custom_projects_images(self, project_name: str) -> dict:
        """
        获取指定自定义仓库项目中的所有镜像信息

        该方法会获取指定项目下的所有镜像仓库信息，包括仓库名称、标签、
        大小和推送时间等详细信息。实际上是调用了get_public_base_image方法。

        Args:
            project_name (str): 要查询的项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 用户必须对该项目有访问权限
                - 示例：'my-project', 'test-repo'

        Returns:
            dict: 包含项目镜像信息的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码，成功时为200
                - message (str): 操作结果描述
                - data (list): 镜像仓库列表，每个元素包含：
                    - name (str): 完整仓库名称
                    - repository_name (str): 去除项目前缀的仓库名称
                    - project_name (str): 项目名称
                    - tags_list (list): 标签信息列表，每个标签包含：
                        - tag_name (str): 标签名称
                        - tag_push_time (str): 推送时间
                        - size (str): 格式化后的镜像大小（GB或MB）

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 获取指定项目的所有镜像
            result = harbor_service.get_custom_projects_images("my-project")

            if result["status"]:
                images = result["data"]
                for image in images:
                    print(f"仓库: {image['repository_name']}")
                    print(f"项目: {image['project_name']}")
                    for tag in image['tags_list']:
                        print(f"  标签: {tag['tag_name']}")
                        print(f"  大小: {tag['size']}")
                        print(f"  推送时间: {tag['tag_push_time']}")
            else:
                print(f"获取失败: {result['message']}")

        Note:
            - 该方法复用了get_public_base_image的逻辑
            - 返回的数据结构与get_public_base_image一致
            - 镜像大小会自动格式化为GB或MB单位
            - 如果镜像没有标签，tag_name和tag_push_time将显示为'none'
        """
        get_custom_projects_images_response = self.get_public_base_image(project_name)
        return get_custom_projects_images_response

    # 删除指定自定义仓库镜像
    def delete_custom_projects_images(
        self, project_name: str, repository_name: str
    ) -> dict:
        """
        删除指定自定义仓库项目中的特定镜像仓库

        该方法会删除指定项目下的特定镜像仓库，包括该仓库下的所有镜像和标签。
        删除操作不可逆，请谨慎使用。

        Args:
            project_name (str): 项目名称
                - 必须是已存在的项目名称
                - 项目名称区分大小写
                - 示例：'test11', 'my-project'

            repository_name (str): 要删除的镜像仓库名称
                - 可以是简单名称或包含路径的名称
                - 如果包含路径分隔符'/'，系统会自动进行URL编码
                - 示例：'nginx', 'core/kube-calico-controllers'

        Returns:
            dict: 包含删除结果的字典
                - status (bool): 操作是否成功
                - code (int): HTTP状态码
                - message (str): 操作结果描述
                - data: 返回的数据（如果有）

        Raises:
            Exception: 当Harbor API调用失败时抛出异常

        Example:
            # 删除简单名称的镜像仓库
            result = harbor_service.delete_custom_projects_images(
                project_name="test11",
                repository_name="nginx"
            )

            # 删除包含路径的镜像仓库
            result = harbor_service.delete_custom_projects_images(
                project_name="test11",
                repository_name="core/kube-calico-controllers"
            )

            if result["status"]:
                print(f"镜像仓库删除成功: {result['message']}")
            else:
                print(f"镜像仓库删除失败: {result['message']}")

        Note:
            - 删除操作不可逆，请谨慎使用
            - 删除前请确保仓库中没有重要的镜像数据
            - 建议在删除前备份重要的镜像数据
            - 包含路径的仓库名称会自动进行URL编码处理
            - 删除后该仓库下的所有镜像和标签都将丢失
        """
        delete_project_repository_response = self.harbor.delete_project_repository(
            project_name, repository_name
        )
        return delete_project_repository_response
