from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LLMConfig(BaseModel):
    """由调用方传入的模型连接，不读取部署环境。"""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    api_key: SecretStr = Field(min_length=1)
    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    provider: str = ""  # 未指定预设时使用标准 OpenAI 兼容客户端。
    timeout: float = Field(default=60, gt=0)  # 超时单位为秒；传入 HTTP 客户端时由其覆盖。
    max_retries: int = Field(default=0, ge=0)  # 默认关闭自动重试，避免重复计费。
