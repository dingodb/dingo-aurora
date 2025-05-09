# 统一返回格式对象

from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

# 定义泛型类型
T = TypeVar("T")

class ResponseModel(BaseModel, Generic[T]):
    errorCode: str = ''
    errorMessage: str = ''
    flag: bool = True
    resData: Optional[T] = None


def success_response(data=None):
    return ResponseModel(flag=True, resData=data)

def error_response(errorCode, errorMessage):
    return ResponseModel(flag= False, errorCode=errorCode, errorMessage=errorMessage)