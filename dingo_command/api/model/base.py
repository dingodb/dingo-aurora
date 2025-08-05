from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field

T = TypeVar("T")

class DingoopsObject(BaseModel):
    id: str = Field(None, description="对象的id")
    name: str = Field(None, description="对象的名称")
    description: str = Field(None, description="对象的描述信息")
    extra: dict = Field(None, description="对象的扩展信息")
    created_at: int = Field(None, description="对象的创建时间")
    updated_at: int = Field(None, description="对象的更新时间")


# 基础响应模型
class BaseResponse(BaseModel, Generic[T]):
    code: int = 200
    status: str = "success"
    data: Optional[T] = None
    message: Optional[str] = None


class ErrorDetail(BaseModel):
    type: Optional[str] = None
    details: Optional[str] = None


class ErrorResponse(BaseResponse):
    error: Optional[ErrorDetail] = None


# chart基础响应模型
class BaseChartResponse(BaseModel, Generic[T]):
    success: bool = Field(default=True, description="请求是否成功")
    data: Optional[List[T]] = Field(default=None, description="成功时的业务数据")
    message: Optional[str] = Field(default=None, description="错误信息或成功提示")


class ErrorChartResponse(BaseModel, Generic[T]):
    success: bool = Field(default=False, description="请求失败")
    message: str = Field(..., description="详细错误信息")


class ErrorChartDetail(BaseModel):
    type: Optional[str] = None
    details: Optional[str] = None


# # 成功响应（带数据）
# success_response = BaseResponse(
#     data={"items": [1, 2, 3]},
#     message="查询成功"
# )
#
# # 输出：{"success": true, "data": {"items": [1,2,3]}, "message": "查询成功"}
#
# # 错误响应（无数据）
# error_response = ErrorResponse(
#     message="用户ID不存在"
# )
#
# # 输出：{"success": false, "message": "用户ID不存在"}