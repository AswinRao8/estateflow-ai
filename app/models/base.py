from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard envelope for all successful API responses."""
    success: bool = True
    data: T | None = None
    message: str = "OK"


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    """Standard envelope for all error responses."""
    success: bool = False
    error: ErrorDetail

    @classmethod
    def of(cls, code: str, message: str, field: str | None = None) -> "ErrorResponse":
        return cls(error=ErrorDetail(code=code, message=message, field=field))
