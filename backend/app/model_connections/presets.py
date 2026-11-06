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

ZHIPU = ModelPreset(
    id="zhipu",
    name="智谱 GLM",
    provider="zhipu",
    protocol="openai-chat-completions",
    base_url="https://open.bigmodel.cn/api/paas/v4",
    default_model_id="glm-5.3",
    description="使用智谱开放平台标准 API Key，按 API 账户计费；与 GLM Coding Plan Key 不通用。",
)

DEEPSEEK = ModelPreset(
    id="deepseek",
    name="DeepSeek",
    provider="deepseek",
    protocol="openai-chat-completions",
    base_url="https://api.deepseek.com",
    default_model_id="deepseek-flash",
    description="使用 DeepSeek 开放平台 API Key，账号需有可用余额及模型访问权限。",
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

PRESETS = {preset.id: preset for preset in (KIMI_CODE, ZHIPU, DEEPSEEK, SILICONFLOW_EMBEDDING)}
