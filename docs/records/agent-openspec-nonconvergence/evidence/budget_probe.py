"""Offline runtime probe; all model responses are scripted, no provider requests."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from runtime_helpers import MemoryControl
from test_capability_runtime import ScriptedModel, response

from app.agent_runtime.checkpoints import CheckpointStore
from app.agent_runtime.contracts import AgentRequest, RuntimeFailure
from app.agent_runtime.langchain import execute_agent
from app.llm.config import LLMConfig


async def probe(model_limit):
    skill = {
        "skill_id": "offline-probe",
        "name": "离线样本",
        "description": "用于工具预算探针",
        "instructions": "这是静态工具结果。",
        "parameters": {},
        "skill_revision": 1,
        "assignment_revision": 1,
        "instructions_hash": "offline",
    }
    snapshot = {
        "schema_version": 2,
        "skills": [skill],
        "selected_skill_ids": [],
        "tools": [],
        "system_prompt": "完成离线任务。",
        "max_model_calls": model_limit,
        "max_skill_reads": 16,
        "max_tool_calls": 32,
        "max_output_tokens": 4096,
        "max_output_bytes": 131072,
        "max_reasoning_bytes": 32768,
        "context_bytes": 131072,
        "recursion_limit": 128,
    }
    model = ScriptedModel(
        responses=[
            response(
                "",
                [
                    {
                        "name": "read_file",
                        "id": f"read-{i}",
                        "args": {"file_path": "/skills/s-offline-probe/SKILL.md"},
                    }
                ],
            )
            for i in range(8)
        ]
        + [response("已经有足够信息，第九轮可直接交付。")]
    )
    control = MemoryControl()
    request = AgentRequest(
        run_id=str(uuid4()),
        snapshot=snapshot,
        messages=[{"id": str(uuid4()), "role": "user", "content": "完成离线任务"}],
        config=LLMConfig(
            api_key="offline-placeholder",
            model_id="offline-scripted",
            base_url="http://invalid.local",
        ),
    )
    with tempfile.TemporaryDirectory(prefix="niuma-budget-probe-") as directory:
        with patch("app.llm.factory.create_chat_model", return_value=model):
            try:
                output = await execute_agent(
                    request,
                    control,
                    checkpoints=CheckpointStore(str(Path(directory) / "runtime.sqlite")),
                )
                outcome = {"status": "succeeded", "text": output.text}
            except RuntimeFailure as error:
                outcome = {
                    "status": "failed",
                    "code": error.code,
                    "partial_text": error.partial_text,
                }
    outcome.update(
        model_limit=model_limit,
        scripted_model_invocations=len(model.prompts),
        durable_model_starts=control.model_calls,
        tool_actions=sum(a["kind"] == "tool_call" for a in control.actions.values()),
        final_answer_in_script_was_consumed=model._index == 9,
    )
    return outcome


async def main():
    print(json.dumps([await probe(8), await probe(9)], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
