import json

import httpx

from app.llm.config import LLMConfig


def probe_chat(config: LLMConfig) -> dict:
    failure = "服务未返回可识别的模型目录，暂时无法验证；这不代表 Key 一定无效。"
    try:
        with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                "GET",
                config.base_url + "/models",
                headers={
                    "Authorization": "Bearer " + config.api_key.get_secret_value(),
                    "User-Agent": "AgentPlatform/0.1",
                    "Accept": "application/json",
                },
            ) as response:
                if response.status_code in (401, 403):
                    return dict(
                        ok=False,
                        message="服务拒绝访问，请检查所选预设的 API Key、账户状态及模型访问权限。",
                    )
                if response.status_code == 429:
                    return dict(ok=False, message="服务限流，请稍后重试。")
                if response.status_code != 200:
                    return dict(
                        ok=False,
                        message=f"服务返回 HTTP {response.status_code}，未完成连接检查。",
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 1048576:
                        return dict(ok=False, message=failure)
        payload = json.loads(body)
        models = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return dict(ok=False, message=failure)
        found = any(isinstance(item, dict) and item.get("id") == config.model_id for item in models)
        return dict(
            ok=found,
            message=(
                "凭证与模型目录检查通过；尚未验证内容生成或 Agent 任务。"
                if found
                else "已连接，但当前 Model ID 不在可见模型目录中，请核对模型或订阅权限。"
            ),
        )
    except httpx.TimeoutException:
        return dict(ok=False, message="连接检查超时，请稍后重试。")
    except httpx.HTTPError:
        return dict(ok=False, message="无法连接模型服务，请检查服务状态和后端网络。")
    except (ValueError, UnicodeError):
        return dict(ok=False, message=failure)
