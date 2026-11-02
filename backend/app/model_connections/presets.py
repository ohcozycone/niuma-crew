"""Curated endpoint metadata, never credentials or client-controlled URLs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ModelPreset(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    provider: str
    protocol: str
    base_url: str
    default_model_id: str
    description: str
    capability: Literal["chat", "embedding"] = "chat"


KIMI_CODE = ModelPreset(
    id="kimi-code",
    name="Kimi Code",
    provider="kimi-code",
    protocol="openai-chat-completions",
    base_url="https://api.kimi.com/coding/v1",
    default_model_id="kimi-for-coding",
    description="使用 Kimi Code 订阅 Key；与开放平台 Key 不通用。",
)

SILICONFLOW_EMBEDDING = ModelPreset(
    id="siliconflow-embedding",
    name="硅基流动 · BGE-M3",
    provider="siliconflow",
    protocol="openai-embeddings",
    capability="embedding",
    base_url="https://api.siliconflow.cn/v1",
    default_model_id="BAAI/bge-m3",
    description="用于知识库向量检索。使用硅基流动 Key，账号需具备该模型访问权限。",
)

PRESETS = {preset.id: preset for preset in (KIMI_CODE, SILICONFLOW_EMBEDDING)}
