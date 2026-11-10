import json
from copy import deepcopy
from dataclasses import fields

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.actor import Actor
from app.auth.permissions import permissions_for, require_permission
from app.common.errors import InvalidInputError, NotFoundError
from app.runtime.contracts.runs import RunState
from app.runtime.execution.errors import failure_kind
from app.runtime.execution.evidence import redact
from app.runtime.execution.metrics import diagnostic_metrics
from app.runtime.execution.models import Run, RunAction
from app.runtime.execution.store import require_run

PREVIEW_BYTES = 256 * 1024


class ExecutionQueries:
    def __init__(self, database, files, logs):
        self.database, self.files, self.logs = database, files, logs

    def read(
        self,
        actor: Actor,
        run_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        action_id: str | None = None,
    ) -> dict:
        require_permission(actor, "runs:read")
        diagnostic = {"agents:read", "organization_rules:read"} <= permissions_for(actor)
        with self.database.transaction() as db:
            run = require_run(db, run_id, actor)
            artifacts = {}
            projections = {}

            def artifact(row, direction):
                key = (row.id, direction)
                if key not in artifacts:
                    artifacts[key] = self._artifact(
                        db, getattr(row, direction + "_file_id"), run_id, diagnostic
                    )
                return artifacts[key]

            def project(row):
                if row.id not in projections:
                    value = self._action(row)
                    if row.kind == "model_call":
                        value["metrics"] = diagnostic_metrics(
                            (artifact(row, "request").get("document") or {}).get("payload", {}),
                            (artifact(row, "response").get("document") or {}).get("payload", {}),
                            row.safe_details.get("usage"),
                        )
                    projections[row.id] = value
                return projections[row.id]

            query = select(RunAction).where(RunAction.run_id == run_id)
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            actions = list(
                db.scalars(query.order_by(RunAction.sequence).offset(offset).limit(limit))
            )
            # 失败导航独立于当前动作页，避免遗漏页外失败。
            failed_query = query.where(
                or_(RunAction.status == "failed", RunAction.error_code.is_not(None))
            )
            failed_total = db.scalar(select(func.count()).select_from(failed_query.subquery())) or 0
            failures = list(db.scalars(failed_query.order_by(RunAction.sequence).limit(20)))
            result = {
                "run": {
                    **{
                        key: getattr(run, key)
                        for key in (
                            "id",
                            "agent_id",
                            "origin_kind",
                            "status",
                            "revision",
                            "actions_revision",
                            "error_code",
                            "started_at",
                            "finished_at",
                            "usage",
                        )
                    },
                    "error_kind": failure_kind(run.error_code),
                },
                "configuration": {
                    key: run.config_snapshot.get(key)
                    for key in ("agent_revision", "agent_name", "model_id", "schema_version")
                },
                "can_inspect_inputs": diagnostic,
                "actions": {
                    "items": [project(row) for row in actions],
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                },
                "failures": {
                    "items": [project(row) for row in failures],
                    "total": failed_total,
                },
            }
            preferred = next(
                (row for row in failures if run.error_code and row.error_code == run.error_code),
                failures[0] if failures else actions[0] if actions else None,
            )
            if action_id or preferred:
                action = self._require_action(db, run_id, action_id) if action_id else preferred
                result["selected"] = {
                    **project(action),
                    "request": artifact(action, "request"),
                    "response": artifact(action, "response"),
                    # 恢复载荷不作为真实上游响应展示。
                    "saved_tool_feedback": redact(action.result_payload) if diagnostic else None,
                }
        result["logs"] = self.logs.read(run_id) if diagnostic else None
        return result

    @staticmethod
    def _action(row):
        return {
            "error_kind": failure_kind(row.error_code),
            **{
                key: getattr(row, key)
                for key in (
                    "id",
                    "sequence",
                    "action_key",
                    "parent_action_id",
                    "kind",
                    "status",
                    "safe_details",
                    "output_text",
                    "reasoning_text",
                    "reasoning_truncated",
                    "error_code",
                    "started_at",
                    "finished_at",
                )
            },
        }

    @staticmethod
    def _require_action(db, run_id, action_id):
        row = db.get(RunAction, action_id)
        if not row or row.run_id != run_id:
            raise NotFoundError("action_not_found")
        return row

    def _artifact(self, db, file_id, run_id, allowed):
        if not allowed:
            return {"status": "restricted"}
        if not file_id:
            return {"status": "not_collected"}
        file = self.files.metadata(db, file_id)
        if not file or file.purpose != "evidence" or file.origin_run_id != run_id:
            return {"status": "unavailable"}
        try:
            content = self.files.read(file.id)
            parsed = json.loads(content) if len(content) <= PREVIEW_BYTES else None
        except (OSError, NotFoundError, InvalidInputError, ValueError):
            return {"status": "unavailable"}
        truncated = len(content) > PREVIEW_BYTES
        return {
            "status": "available",
            "size": file.size,
            "content_hash": file.content_hash,
            "truncated": truncated,
            "document": parsed,
            "preview": content[:PREVIEW_BYTES].decode("utf-8", errors="replace")
            if truncated
            else None,
        }

    def download(self, actor: Actor, run_id: str, action_id: str, direction: str) -> bytes:
        require_permission(actor, "runs:read")
        require_permission(actor, "agents:read")
        require_permission(actor, "organization_rules:read")
        if direction not in ("request", "response"):
            raise NotFoundError("evidence_not_found")
        with self.database.transaction() as db:
            require_run(db, run_id, actor)
            action = self._require_action(db, run_id, action_id)
            file = (
                self.files.metadata(db, getattr(action, direction + "_file_id"))
                if getattr(action, direction + "_file_id")
                else None
            )
            if not file or file.purpose != "evidence" or file.origin_run_id != run_id:
                raise NotFoundError("evidence_not_found")
            file_id = file.id
        return self.files.read(file_id)


def run_state(row: Run) -> RunState:
    return RunState(
        **{field.name: deepcopy(getattr(row, field.name)) for field in fields(RunState)}
    )


def read_run(db: Session, run_id: str, actor: Actor | None = None) -> RunState:
    """在调用方事务内读取独立值，不返回可变的执行记录。"""
    return run_state(require_run(db, run_id, actor))


def optional_run(db: Session, run_id: str) -> RunState | None:
    row = db.get(Run, run_id)
    return run_state(row) if row else None
