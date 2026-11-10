from app.infrastructure.settings import positive_values
from app.runtime.contracts.agent import AgentConfig as AgentConfig


def load_agent_config(values: dict[str, str | None]) -> AgentConfig:
    return AgentConfig(**positive_values(AgentConfig, values))
