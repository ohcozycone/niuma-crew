"""Worker-facing persistence. No HTTP identities or provider objects cross this boundary."""

from sqlalchemy import func, select

from app.agent_runtime.contracts import ContentUpdate
from app.errors import ConflictError, PermissionDeniedError
from app.execution.contracts import SUPPORTED_SNAPSHOT_VERSIONS, Completion
from app.execution.errors import ExecutionFailure
from app.execution.models import ACTIVE, TERMINAL, Run, RunAction
from app.execution.queries import require_run
from app.infrastructure.database.fields import utc_now
from app.infrastructure.database.transactions import reserve_writer
from app.tools.contracts import ToolPermit


class RunStore:
    def __init__(self, database):
        self.database = database

    def recover(self, resume=False):
        terminal = []
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            for row in db.scalars(select(Run).where(Run.status.in_(ACTIVE))):
                if row.status == "cancelling":
                    terminal.append(Completion(row.id, None, "cancelled"))
                elif (
                    resume
                    and row.config_snapshot.get("schema_version") in SUPPORTED_SNAPSHOT_VERSIONS
                    and row.config_snapshot.get("checkpoint_resumable", False)
                ):
                    row.status = "queued"
                    self._close_actions(db, row, "interrupted", "runtime_interrupted")
                    row.revision += 1
                else:
                    terminal.append(Completion(row.id, None, "interrupted", "runtime_interrupted"))
        return terminal

    def load(self, id: str):
        with self.database.transaction() as db:
            row = require_run(db, id)
            return row, row.input_snapshot

    def queued_metadata(self):
        with self.database.transaction() as db:
            return [
                (row.id, row.created_at if row.started_at is None else None)
                for row in db.scalars(
                    select(Run).where(Run.status == "queued").order_by(Run.created_at, Run.id)
                )
            ]

    def claim(self, id):
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status != "queued":
                return False
            row.status, row.started_at = "running", row.started_at or utc_now()
            row.revision += 1
            return True

    def checkpoint_saved(self, id, checkpoint_id):
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status in ACTIVE:
                row.checkpoint_id = checkpoint_id

    def restore_control(self, id):
        with self.database.transaction() as db:
            row = require_run(db, id)
            steps = list(db.scalars(select(RunAction).where(RunAction.run_id == id)))
            return {
                "active_skills": {
                    step.skill_id
                    for step in steps
                    if step.kind == "skill_activation" and step.status == "succeeded"
                },
                "contents": [
                    ContentUpdate(
                        step.action_key,
                        step.output_text,
                        step.reasoning_text,
                        step.reasoning_truncated,
                        step.safe_details.get("has_tool_calls", False),
                    )
                    for step in steps
                    if step.kind == "model_call"
                ],
                "usage": row.usage if row.started_at else None,
            }

    def state(self, id):
        with self.database.transaction() as db:
            row = require_run(db, id)
            return row.status, row.initiated_by_session_id

    def active_ids(self):
        with self.database.transaction() as db:
            return list(db.scalars(select(Run.id).where(Run.status.in_(ACTIVE))))

    @classmethod
    def finish(cls, db, row: Run, intent: Completion) -> None:
        if intent.status not in TERMINAL:
            raise ValueError("Invalid terminal execution status")
        cls._write_progress(db, row, intent.progress)
        unfinished = cls._close_actions(
            db,
            row,
            "interrupted"
            if intent.status == "interrupted"
            else "cancelled"
            if intent.status == "cancelled"
            else "failed",
            intent.error,
        )
        row.status, row.error_code, row.finished_at = intent.status, intent.error, utc_now()
        if intent.usage is not None and not unfinished:
            row.usage = intent.usage
        row.revision += 1

    @staticmethod
    def _close_actions(db, row, status, error):
        unfinished_model = False
        changed = False
        for step in db.scalars(
            select(RunAction).where(RunAction.run_id == row.id, RunAction.status == "running")
        ):
            changed = True
            if step.kind == "model_call":
                unfinished_model = True
                # An unfinished request may have consumed tokens without reporting usage.
                row.usage = {
                    key: None
                    for key in (
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                        "cached_input_tokens",
                        "reasoning_tokens",
                    )
                }
            actual = "unknown" if step.kind in ("model_call", "tool_call") else status
            step.status, step.error_code, step.finished_at = actual, error, utc_now()
        if changed:
            row.actions_revision += 1
        return unfinished_model

    @staticmethod
    def _set_content(step, content: ContentUpdate):
        step.output_text = content.output_text
        step.reasoning_text = content.reasoning_text
        step.reasoning_truncated = content.reasoning_truncated
        step.safe_details = {**step.safe_details, "has_tool_calls": content.has_tool_calls}

    @classmethod
    def _write_progress(cls, db, row, contents):
        changed = False
        for content in contents:
            step = db.scalar(
                select(RunAction).where(
                    RunAction.run_id == row.id, RunAction.action_key == content.key
                )
            )
            if step and step.status == "running":
                cls._set_content(step, content)
                changed = True
        return changed

    def update_progress(self, id: str, contents: list[ContentUpdate]):
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status == "running" and self._write_progress(db, row, contents):
                row.revision += 1

    def start_action(
        self, id, key, kind, details=None, skill_id=None, *, budget=None, authorize=None
    ):
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if authorize:
                authorize(db)
            if budget:
                self._reserve(row, budget)
            return self._start_action(db, row, key, kind, details, skill_id)

    @staticmethod
    def _reserve(row, counter):
        limit = {
            "model_calls": "max_model_calls",
            "skill_reads": "max_skill_reads",
            "tool_calls": "max_tool_calls",
        }[counter]
        count = getattr(row, counter) + 1
        if count > row.config_snapshot[limit]:
            raise ExecutionFailure("agent_budget_exceeded")
        setattr(row, counter, count)
        return count

    def start_model(self, id, authorize):
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            authorize(db)
            number = self._reserve(row, "model_calls")
            key = f"model:{number}"
            return number, self._start_action(db, row, key, "model_call", {"round": number})

    def _start_action(self, db, row, key, kind, details=None, skill_id=None):
        id = row.id
        if row.status != "running":
            raise ConflictError("runtime_interrupted", "执行已停止。")
        existing = db.scalar(
            select(RunAction)
            .where(RunAction.run_id == id, RunAction.call_key == key)
            .order_by(RunAction.sequence.desc())
            .limit(1)
        )
        retry_read = (details or {}).get("recovery") == "readonly" or (
            row.config_snapshot.get("schema_version") == 2
            and (details or {}).get("tool") == "read_file"
        )
        if existing and not (kind == "tool_call" and retry_read):
            raise ConflictError("runtime_interrupted", "Action already recorded")
        if skill_id and skill_id not in row.config_snapshot.get("authorized_skill_ids", []):
            raise PermissionDeniedError("skill_not_allowed", "Skill is not authorized")
        sequence = (
            db.scalar(select(func.max(RunAction.sequence)).where(RunAction.run_id == id)) or 0
        ) + 1
        db.add(
            RunAction(
                run_id=id,
                sequence=sequence,
                action_key=key if existing is None else f"{key}:attempt:{sequence}",
                call_key=key,
                parent_action_id=self._parent_action(db, id, key),
                kind=kind,
                skill_id=skill_id,
                safe_details=details or {},
                started_at=utc_now(),
            )
        )
        row.revision += 1
        row.actions_revision += 1
        return key if existing is None else f"{key}:attempt:{sequence}"

    @staticmethod
    def _parent_action(db, id, key):
        tool_id = key.removeprefix("tool:")
        for item in db.scalars(
            select(RunAction)
            .where(RunAction.run_id == id, RunAction.kind == "model_call")
            .order_by(RunAction.sequence.desc())
        ):
            if tool_id in item.safe_details.get("tool_call_ids", []):
                return item.id
        return None

    def finish_action(
        self,
        id,
        key,
        status="succeeded",
        error=None,
        details=None,
        usage=None,
        content=None,
        *,
        result_payload=None,
    ):
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status not in ("running", "cancelling"):
                raise ConflictError("runtime_interrupted", "执行已停止。")
            step = db.scalar(
                select(RunAction).where(RunAction.run_id == id, RunAction.action_key == key)
            )
            if (
                step
                and step.status == "succeeded"
                and status == "succeeded"
                and step.kind in ("tool_call", "skill_activation")
            ):
                return
            if not step or step.status != "running":
                raise ConflictError("runtime_interrupted", "步骤已结束，不覆盖记录。")
            if row.status == "cancelling":
                status = "cancelled"
            step.status, step.error_code, step.finished_at = status, error, utc_now()
            if details:
                step.safe_details = {**step.safe_details, **details}
            if content is not None:
                self._set_content(step, content)
            if usage is not None:
                row.usage = usage
            if result_payload is not None:
                step.result_payload = result_payload
                step.result_ref = "action:" + step.id
            row.revision += 1
            row.actions_revision += 1

    def begin_tool(self, id, invocation, authorize):
        with self.database.transaction() as db:
            reserve_writer(db, Run.__table__)
            row = require_run(db, id)
            if row.status != "running":
                raise ExecutionFailure("runtime_interrupted")
            binding = authorize(db)
            prior = db.scalar(
                select(RunAction)
                .where(RunAction.run_id == id, RunAction.call_key == invocation.key)
                .order_by(RunAction.sequence.desc())
                .limit(1)
            )
            if prior is not None:
                if prior.safe_details.get("fingerprint") != invocation.fingerprint:
                    raise ExecutionFailure("runtime_interrupted")
                if (
                    binding.get("recovery") == "readonly"
                    and prior.status == "succeeded"
                    and prior.result_payload is not None
                ):
                    return ToolPermit(
                        prior.action_key, invocation.fingerprint, prior.result_payload
                    )
                if binding.get("recovery") != "readonly":
                    raise ExecutionFailure("tool_result_unknown")
            count = sum(
                1
                for action in db.scalars(
                    select(RunAction).where(RunAction.run_id == id, RunAction.kind == "tool_call")
                )
                if action.safe_details.get("binding_id") == invocation.binding_id
            )
            if count >= binding["scope_policy"].get("max_calls", 32):
                raise ExecutionFailure("agent_budget_exceeded")
            self._reserve(row, "tool_calls")
            if invocation.skill_id:
                self._reserve(row, "skill_reads")
            details = {
                "tool": binding.get("tool_name", invocation.name),
                "model_tool": invocation.name,
                "name": binding.get("tool_name", invocation.name),
                "binding_id": invocation.binding_id,
                "fingerprint": invocation.fingerprint,
                "recovery": binding.get("recovery", "never"),
            }
            key = self._start_action(
                db, row, invocation.key, "tool_call", details, invocation.skill_id
            )
            return ToolPermit(key, invocation.fingerprint)
