from pydantic import BaseModel, Field

class DingoopsObject(BaseModel):
    id: str = Field(None, description="对象的id")
    name: str = Field(None, description="对象的名称")
    description: str = Field(None, description="对象的描述信息")
    extra: dict = Field(None, description="对象的扩展信息")
    created_at: str = Field(None, description="对象的创建时间")
    updated_at: str = Field(None, description="对象的更新时间")