"""Server-only credentials and bounded policy for built-in public web access."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WebConfig:
    bocha_api_key: str | None = field(default=None, repr=False)
    jina_api_key: str | None = field(default=None, repr=False)
    bocha_endpoint: str = "https://api.bocha.cn/v1/web-search"
    timeout_seconds: float = 20
    max_response_bytes: int = 1048576
    max_content_chars: int = 24000

    def __post_init__(self) -> None:
        # Credentials must never be forwarded to arbitrary configurable destinations.
        if self.bocha_endpoint not in {
            "https://api.bocha.cn/v1/web-search",
            "https://api.bochaai.com/v1/web-search",
        }:
            raise ValueError("WEB_BOCHA_ENDPOINT must be an official Bocha endpoint")
        if not 1 <= self.timeout_seconds <= 60:
            raise ValueError("WEB_TIMEOUT_SECONDS must be between 1 and 60")
        if not 4096 <= self.max_response_bytes <= 4194304:
            raise ValueError("WEB_MAX_RESPONSE_BYTES must be between 4096 and 4194304")
        if not 1000 <= self.max_content_chars <= 100000:
            raise ValueError("WEB_MAX_CONTENT_CHARS must be between 1000 and 100000")

    @property
    def ready(self) -> bool:
        # The employee's permission enables both capabilities as one bundle.
        return bool(self.bocha_api_key and self.bocha_api_key.strip())


def load_web_config(values: dict[str, str | None]) -> WebConfig:
    return WebConfig(
        bocha_api_key=values.get("WEB_BOCHA_API_KEY") or None,
        jina_api_key=values.get("WEB_JINA_API_KEY") or None,
        bocha_endpoint=values.get("WEB_BOCHA_ENDPOINT") or "https://api.bocha.cn/v1/web-search",
        timeout_seconds=float(values.get("WEB_TIMEOUT_SECONDS") or "20"),
        max_response_bytes=int(values.get("WEB_MAX_RESPONSE_BYTES") or "1048576"),
        max_content_chars=int(values.get("WEB_MAX_CONTENT_CHARS") or "24000"),
    )
