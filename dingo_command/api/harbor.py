from fastapi import APIRouter, HTTPException
from fastapi import Query, Body, Header, Depends
from dingo_command.services.harbor import HarborService
from datetime import datetime

router = APIRouter()
harbor_service = HarborService()


# 获取公共仓库镜像
@router.get(
    "/harbor/public/project/images/list",
    summary="获取公共仓库镜像",
    description="获取公共仓库镜像",
)
async def get_public_base_image(
    project_name: str = Query("alayanew-public", description="项目名称"),
    public_image_name: str = Query("", description="镜像名称"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(10, description="页数量大小"),
):
    try:
        result = harbor_service.get_public_base_image(
            project_name=project_name,
            public_image_name=public_image_name,
            page=page,
            page_size=page_size,
        )
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400, detail=f"get public base image error: {str(e)}"
        )


# 添加harbor用户
@router.post("/harbor/user/add", summary="添加harbor用户", description="添加harbor用户")
async def add_harbor_user(
    username: str = Body(..., description="用户名"),
    password: str = Body(..., description="密码"),
    email: str = Body("", description="邮箱"),
    realname: str = Body("", description="真实姓名"),
    comment: str = Body("", description="备注"),
):
    try:
        if not email:
            email = f"{username}@zetyun01.com"
        if not realname:
            realname = username
        if not comment:
            comment = "接口添加"
        result = harbor_service.add_harbor_user(
            username=username,
            password=password,
            email=email,
            realname=realname,
            comment=comment,
        )
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"add harbor user error: {str(e)}")


# 添加自定义镜像仓库
@router.post(
    "/harbor/custom/project/add",
    summary="添加自定义镜像仓库",
    description="添加自定义镜像仓库",
)
async def add_custom_projects(
    project_name: str = Body(..., description="项目名称"),
    public: str = Body(..., description="是否公开"),
    storage_limit: int = Body(..., description="存储限制"),
    user_name: str = Body(..., description="用户名"),
):
    try:
        result = harbor_service.add_custom_projects(
            project_name=project_name,
            public=public,
            storage_limit=storage_limit,
            user_name=user_name,
        )
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400, detail=f"add custom projects error: {str(e)}"
        )


# 更新自定义镜像仓库
@router.post(
    "/harbor/custom/project/update",
    summary="更新自定义镜像仓库",
    description="更新自定义镜像仓库",
)
async def update_custom_projects(
    project_name: str = Body(..., description="项目名称"),
    public: str = Body(..., description="是否公开"),
    storage_limit: int = Body(..., description="存储限制"),
    user_name: str = Body(..., description="用户名"),
):
    try:
        result = harbor_service.update_custom_projects(
            project_name=project_name, public=public, storage_limit=storage_limit, user_name=user_name
        )
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400, detail=f"update custom projects error: {str(e)}"
        )


# 获取自定义镜像仓库
@router.get(
    "/harbor/custom/project/list",
    summary="获取自定义镜像仓库",
    description="获取自定义镜像仓库",
)
async def get_custom_projects(
    user_name: str = Query(..., description="用户名"),
):
    try:
        result = harbor_service.get_custom_projects(user_name=user_name)
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400, detail=f"get custom projects error: {str(e)}"
        )


# 删除自定义镜像仓库
@router.post(
    "/harbor/custom/project/delete",
    summary="删除自定义镜像仓库",
    description="删除自定义镜像仓库",
)
async def delete_custom_projects(
    project_name: str = Body(..., embed=True, description="项目名称"),
):
    try:
        result = harbor_service.delete_custom_projects(project_name=project_name)
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400, detail=f"delete custom projects error: {str(e)}"
        )


# 获取自定义镜像仓库镜像
@router.get(
    "/harbor/custom/project/images/list",
    summary="获取自定义镜像仓库镜像",
    description="获取自定义镜像仓库镜像",
)
async def get_custom_projects_images(
    project_name: str = Query(..., embed=True, description="项目名称"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(10, description="页数量大小"),
):
    try:
        result = harbor_service.get_custom_projects_images(project_name=project_name, page=page, page_size=page_size)
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400, detail=f"get custom projects images error: {str(e)}"
        )


# 删除自定义镜像仓库镜像
@router.post(
    "/harbor/custom/project/images/delete",
    summary="删除自定义镜像仓库镜像",
    description="删除自定义镜像仓库镜像",
)
async def delete_custom_projects_images(
    project_name: str = Body(..., description="项目名称"),
    repository_name: str = Body(..., description="镜像仓库名称"),
):
    try:
        result = harbor_service.delete_custom_projects_images(
            project_name=project_name, repository_name=repository_name
        )
        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=400, detail=f"delete custom projects images error: {str(e)}"
        )

# 删除自定义镜像仓库镜像TAG
@router.post(
    "/harbor/custom/project/images/tag/delete",
    summary="删除自定义镜像仓库镜像TAG",
    description="删除自定义镜像仓库镜像TAG",
)
async def delete_custom_projects_images_tag(
    project_name: str = Body(..., description="项目名称"),
    repository_name: str = Body(..., description="镜像仓库名称"),
    digest: str = Body(..., description="镜像TAG"),
):  
    try:
        result = harbor_service.delete_custom_projects_images_tag(
            project_name=project_name, repository_name=repository_name, digest=digest
        )
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"delete custom projects images tag error: {str(e)}")