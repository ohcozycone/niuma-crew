"""Build run-local skill files and validate SDK-driven loading."""

import json
from dataclasses import dataclass, field

from deepagents.backends.protocol import BackendProtocol, FileData
from deepagents.backends.utils import create_file_data
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from langchain.agents.middleware import AgentMiddleware

from app.execution import prompts
from app.execution.contracts import AgentContext, RuntimeFailure

SKILLS_ROOT = "/skills/"


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
        body = prompts.skill_instructions(
            item["instructions"], item["parameters"], compatibility=compatibility
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
    backend: BackendProtocol, snapshot: dict, prepared_skills: PreparedSkills
) -> list[AgentMiddleware]:
    """按本轮原生工具许可和技能清单创建文件及技能发现中间件。"""
    selected = {
        binding["tool_name"] for binding in snapshot.get("tools", []) if binding["kind"] == "native"
    }
    if prepared_skills.by_path:
        selected.add("read_file")
    middleware = []
    if selected:
        middleware.append(
            FilesystemMiddleware(
                backend=backend,
                tools=sorted(selected),
                max_execute_timeout=60,
                system_prompt="",
                tool_token_limit_before_evict=None,
                human_message_token_limit_before_evict=None,
            )
        )
    if prepared_skills.by_path:
        middleware.append(
            SkillsMiddleware(
                backend=backend, sources=[SKILLS_ROOT], system_prompt=prompts.SKILLS_SYSTEM_PROMPT
            )
        )
    return middleware


class SkillLoadingMiddleware(AgentMiddleware):
    """Validate captured skill loads and record activation only after successful loading."""

    def __init__(
        self,
        prepared_skills: PreparedSkills,
        context: AgentContext,
        activated=(),
    ):
        self.prepared_skills, self.context = prepared_skills, context
        self.prepared_skills.active_skill_ids.update(activated)

    async def _activate(self, item, source):
        skill_id = item["skill_id"]
        await self.context.guard([skill_id])
        if skill_id in self.prepared_skills.active_skill_ids:
            return
        key = "skill:" + skill_id
        await self.context.start(
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
        await self.context.finish(key)
        self.prepared_skills.active_skill_ids.add(skill_id)

    async def awrap_model_call(self, request, handler):
        # SDK pins are host-produced messages. User text cannot forge these metadata fields.
        for path, entry in self.prepared_skills.by_path.items():
            item = entry.skill
            if (
                entry.name in self.prepared_skills.pinned_names
                and item["skill_id"] not in self.prepared_skills.active_skill_ids
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
        if request.tool_call["name"] != "read_file":
            return await handler(request)
        path = request.tool_call.get("args", {}).get("file_path")
        resource = self.prepared_skills.resource_paths.get(path)
        if resource is not None:
            item, _ = resource
            await self.context.guard([item["skill_id"]])
            return await handler(request)
        entry = self.prepared_skills.by_path.get(path)
        if entry is None:
            return await handler(request)

        # 外层工具中间件已锁定工作区，正文读取与成功激活属于同一个临界区。
        # A method is loaded as a whole. Never label a partial window as full activation.
        request = request.override(
            tool_call={
                **request.tool_call,
                "args": {"file_path": path, "offset": 0, "limit": 1000000},
            }
        )
        result = await handler(request)
        if getattr(result, "status", "error") != "success":
            raise RuntimeFailure("skill_load_failed")
        await self._activate(entry.skill, "automatic")
        return result
