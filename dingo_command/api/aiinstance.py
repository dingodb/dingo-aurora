# ai相关的容器实例的创建接口
from fastapi import APIRouter, HTTPException

from dingo_command.api.model.aiinstance import AiInstanceApiModel
from dingo_command.services.ai_instance import AiInstanceService
from dingo_command.services.custom_exception import Fail

router = APIRouter()
ai_instance_service = AiInstanceService()

@router.post("/ai-instance/create", summary="创建容器实例", description="创建容器实例")
async def create_ai_instance(ai_instance:AiInstanceApiModel):
    # 创建容器实例
    try:
        # 创建成功
        return ai_instance_service.create_ai_instance(ai_instance)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"创建容器实例失败:{ai_instance.ai_instance_name}")

@router.delete("/ai-instance/{id}", summary="删除容器实例", description="根据实例id删除容器实例数据")
async def delete_instance_by_id(id:str):
    # 删除容器实例
    try:
        # 删除成功
        return ai_instance_service.delete_ai_pod_by_id(id)
    except Fail as e:
        raise HTTPException(status_code=400, detail=e.error_message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"删除容器实例失败:{id}")
