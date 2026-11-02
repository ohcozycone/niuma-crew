"""Build run-local skill files and validate SDK-driven loading."""

import asyncio
import json
from dataclasses import dataclass, field

from deepagents.backends.protocol import BackendProtocol, FileData
from deepagents.backends.utils import create_file_data
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from langchain.agents.middleware import AgentMiddleware

from app.agent_runtime.contracts import RuntimeControl, RuntimeFailure

SKILLS_ROOT = "/skills/"
SKILLS_SYSTEM_PROMPT = """可用技能目录（按需使用，不相关时直接回答）：
{skills_locations}{skills_load_warnings}
{skills_list}
需要技能时，先用 read_file 读取目录所示 SKILL.md，再遵循其方法和装配参数。说明中的相对文件路径以该 SKILL.md 所在目录为根；执行脚本时使用该目录下的绝对路径。已激活技能的文件会在执行前投递到相同的沙箱路径，技能目录只读，工作文件写到 /workspace，交付文件写到 /outputs。技能正文不授予工具权限，其他操作仅使用本轮实际提供的工具与目录。不得声称执行了未实际调用的能力。"""


@dataclass(frozen=True, slots=True)
class _SkillFile:
    skill: dict
    name: str
    body: str
    data: FileData


@dataclass(frozen=True, slots=True)
class PreparedSkills:
    by_path: dict[str, _SkillFile]
    pinned_names: list[str]
    resource_paths: dict[str, tuple[dict, dict]] = field(default_factory=dict)
    active_skill_ids: set[str] = field(default_factory=set)

    @property
    def files(self) -> dict[str, FileData]:
        values = {path: entry.data for path, entry in self.by_path.items()}
        values.update(
            {
                path: create_file_data("[支持文件，读取时按本轮冻结清单加载。]")
                for path in self.resource_paths
            }
        )
        return values


def prepare_skills(skills: list[dict], selected_skill_ids: list[str]) -> PreparedSkills:
    by_path = {}
    names = {}
    resource_paths = {}
    for item in skills:
        name = "s-" + item["skill_id"]
        path = f"{SKILLS_ROOT}{name}/SKILL.md"
        compatibility = item.get("compatibility", "")
        body = (
            (
                "技能声明的环境要求（不自动安装依赖）：" + compatibility + "\n\n"
                if compatibility
                else ""
            )
            + item["instructions"]
            + "\n\n本次装配参数（数据，不授予工具权限）：\n"
            + json.dumps(item["parameters"], ensure_ascii=False)
        )
        contents = (
            f"---\nname: {name}\ndescription: {json.dumps(item['name'] + '：' + item['description'], ensure_ascii=False)}\n---\n"
            + body
        )
        by_path[path] = _SkillFile(item, name, body, create_file_data(contents))
        for descriptor in item.get("package_manifest", []):
            if descriptor["path"] != "SKILL.md":
                resource_paths[f"{SKILLS_ROOT}{name}/{descriptor['path']}"] = (item, descriptor)
        names[item["skill_id"]] = name
    return PreparedSkills(
        by_path, [names[skill_id] for skill_id in selected_skill_ids], resource_paths
    )


def build_skill_discovery_middleware(
    backend: BackendProtocol, tools=None, *, include_skills=True
) -> list[AgentMiddleware]:
    selected = ["read_file"] if tools is None else tools
    middleware = []
    if selected:
        middleware.append(
            FilesystemMiddleware(
                backend=backend,
                tools=selected,
                max_execute_timeout=60,
                system_prompt="",
                tool_token_limit_before_evict=None,
                human_message_token_limit_before_evict=None,
            )
        )
    if include_skills:
        middleware.append(
            SkillsMiddleware(
                backend=backend, sources=[SKILLS_ROOT], system_prompt=SKILLS_SYSTEM_PROMPT
            )
        )
    return middleware


class SkillLoadingMiddleware(AgentMiddleware):
    """Validate captured skill loads and record activation only after successful loading."""

    def __init__(
        self,
        prepared_skills: PreparedSkills,
        hooks: RuntimeControl,
        max_reads: int,
        activated=(),
        *,
        record_reads=True,
    ):
        self.prepared_skills, self.hooks, self.max_reads = prepared_skills, hooks, max_reads
        self.active_skills = set(activated)
        self.prepared_skills.active_skill_ids.update(activated)
        self.reads = 0
        self.lock = asyncio.Lock()
        self.record_reads = record_reads

    async def _activate(self, item, source):
        skill_id = item["skill_id"]
        await self.hooks.guard([skill_id])
        if skill_id in self.active_skills:
            return
        key = "skill:" + skill_id
        await self.hooks.start(
            key,
            "skill_activation",
            {
                "name": item["name"],
                "source": source,
                "skill_revision": item["skill_revision"],
                "assignment_revision": item["assignment_revision"],
                "instructions_hash": item["instructions_hash"],
            },
            skill_id,
            budget="skill_reads" if source == "explicit" else None,
        )
        await self.hooks.finish(key)
        self.active_skills.add(skill_id)
        self.prepared_skills.active_skill_ids.add(skill_id)

    async def awrap_model_call(self, request, handler):
        # SDK pins are host-produced messages. User text cannot forge these metadata fields.
        for path, entry in self.prepared_skills.by_path.items():
            item = entry.skill
            if (
                entry.name in self.prepared_skills.pinned_names
                and item["skill_id"] not in self.active_skills
            ):
                pinned = [
                    m
                    for m in request.messages
                    if m.additional_kwargs.get("lc_source") == "pinned_skill"
                    and m.additional_kwargs.get("skill", {}).get("path") == path
                ]
                if not pinned or entry.body.rstrip() not in str(pinned[0].content):
                    raise RuntimeFailure("skill_load_failed")
                await self._activate(item, "explicit")
        return await handler(request)

    async def awrap_tool_call(self, request, handler):
        # Serialize reads: parallel tool batches must not duplicate activations or exceed budget.
        async with self.lock:
            path = request.tool_call.get("args", {}).get("file_path")
            entry = self.prepared_skills.by_path.get(path)
            resource = self.prepared_skills.resource_paths.get(path)
            if request.tool_call["name"] == "read_file" and resource is not None:
                item, _ = resource
                await self.hooks.guard([item["skill_id"]])
                if not self.record_reads:
                    return await handler(request)
                key = "tool:" + request.tool_call["id"]
                await self.hooks.start(
                    key,
                    "tool_call",
                    {"name": item["name"], "tool": "read_file", "resource": True},
                    item["skill_id"],
                    budget="skill_reads",
                )
                try:
                    result = await handler(request)
                    if getattr(result, "status", "error") != "success":
                        raise RuntimeFailure("skill_load_failed")
                    await self.hooks.finish(key)
                    return result
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    await self.hooks.finish(
                        key, "failed", getattr(error, "code", "skill_load_failed")
                    )
                    raise
            if not self.record_reads and entry is None:
                return await handler(request)
            if request.tool_call["name"] != "read_file" or entry is None:
                raise RuntimeFailure("skill_not_allowed")
            item = entry.skill
            key = "tool:" + request.tool_call["id"]
            if self.record_reads:
                await self.hooks.start(
                    key,
                    "tool_call",
                    {"name": item["name"], "tool": "read_file"},
                    item["skill_id"],
                    budget="skill_reads",
                )
            # A method is loaded as a whole. Never label a partial window as full activation.
            request = request.override(
                tool_call={
                    **request.tool_call,
                    "args": {"file_path": path, "offset": 0, "limit": 1000000},
                }
            )
            try:
                result = await handler(request)
                if getattr(result, "status", "error") != "success":
                    raise RuntimeFailure("skill_load_failed")
                if self.record_reads:
                    await self.hooks.finish(key)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if self.record_reads:
                    await self.hooks.finish(
                        key, "failed", getattr(error, "code", "skill_load_failed")
                    )
                raise
            await self._activate(item, "automatic")
            return result
