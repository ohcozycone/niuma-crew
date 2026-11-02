"""Bounded OpenAI-compatible embedding calls with a fixed provider configuration."""

import math
from collections.abc import Callable

import httpx
from langchain_openai import OpenAIEmbeddings
from openai import APIError
from pydantic import BaseModel, ConfigDict, SecretStr

from app.errors import InvalidInputError, RateLimitError, ServiceUnavailableError

BATCH_SIZE = 8
VECTOR_DIMENSIONS = 1024


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    connection_id: str
    config_revision: int
    credential_revision: int
    model_id: str
    base_url: str
    api_key: SecretStr


def normalized_vector(values: object) -> list[float]:
    """Reject malformed/zero vectors and store unit vectors for cosine scoring."""
    if not isinstance(values, list) or len(values) != VECTOR_DIMENSIONS:
        raise ValueError("invalid embedding dimensions")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("invalid embedding values")
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("invalid embedding norm")
    return [float(value / norm) for value in values]


def embed_texts(
    config: EmbeddingConfig,
    texts: list[str],
    guard: Callable[[], None] = lambda: None,
) -> list[list[float]]:
    """Send raw, short text; provider token IDs are never approximated with tiktoken."""
    if any(not text.strip() or len(text.encode("utf-8")) > 8192 for text in texts):
        raise InvalidInputError(
            "embedding_text_too_long", "向量输入为空或超过 8192 字节，请缩短文本后重试。"
        )
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as transport:
            model = OpenAIEmbeddings(
                model=config.model_id,
                base_url=config.base_url,
                api_key=config.api_key,
                check_embedding_ctx_length=False,
                model_kwargs={"encoding_format": "float"},
                chunk_size=BATCH_SIZE,
                max_retries=0,
                http_client=transport,
            )
            for start in range(0, len(texts), BATCH_SIZE):
                guard()
                batch = texts[start : start + BATCH_SIZE]
                result = model.embed_documents(batch)
                if len(result) != len(batch):
                    raise ValueError("invalid embedding count")
                vectors.extend(normalized_vector(vector) for vector in result)
                guard()
        return vectors
    except APIError as error:
        status = getattr(error, "status_code", None)
        if status == 429:
            raise RateLimitError(
                "embedding_rate_limited", "硅基流动请求限流，请稍后重试。", retry_after=30
            ) from None
        message = (
            "硅基流动拒绝访问，请检查 Key、实名认证及模型访问权限。"
            if status in (401, 403)
            else "向量服务暂时不可用，请检查服务状态并稍后重试。"
        )
        raise ServiceUnavailableError("embedding_unavailable", message) from None
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
        raise ServiceUnavailableError(
            "embedding_response_invalid", "向量服务未返回有效结果，请稍后重试或检查连接。"
        ) from None
