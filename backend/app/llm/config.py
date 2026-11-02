"""模型工厂接收的单个连接配置，由已授权的模型连接解析得到。"""

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LLMConfig(BaseModel):
    """每次执行显式传入的模型连接，不从部署环境读取模型或 API Key。"""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    api_key: SecretStr = Field(min_length=1)  # SecretStr 隐藏 repr 中的密钥。
    model_id: str = Field(min_length=1)  # 上游模型标识。
    base_url: str = Field(min_length=1)  # 上游 API 基础地址。
    timeout: float = Field(default=60, gt=0)  # SDK 请求超时，秒；传入 HTTP 客户端时由其覆盖。
    max_retries: int = Field(default=0, ge=0)  # SDK 自动重试次数；默认关闭，避免重复计费。
