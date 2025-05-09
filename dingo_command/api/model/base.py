from pydantic import BaseModel, Field
from typing import Optional, Generic, TypeVar

T = TypeVar("T")

class DingoopsObject(BaseModel):
    id: str = Field(None, description="对象的id")
    name: str = Field(None, description="对象的名称")
    description: str = Field(None, description="对象的描述信息")
    extra: dict = Field(None, description="对象的扩展信息")
    created_at: str = Field(None, description="对象的创建时间")
    updated_at: str = Field(None, description="对象的更新时间")


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