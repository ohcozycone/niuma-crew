"""Safe file references returned by upload and authorized listing."""

from pydantic import BaseModel


class FileRead(BaseModel):
    id: str
    name: str
    size: int
    media_type: str
    content_hash: str
    purpose: str
