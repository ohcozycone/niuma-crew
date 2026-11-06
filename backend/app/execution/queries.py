"""Read existing execution facts and private artifacts; no separate trace ledger."""

import json

from sqlalchemy import func, or_, select

from app.auth.permissions import permissions_for, require_permission
from app.errors import InvalidInputError, NotFoundError
from app.execution.evidence import redact
from app.execution.models import RunAction
from app.execution.store import require_run
from app.files.models import StoredFile

PREVIEW_BYTES = 256 * 1024


class ExecutionQueries:
    def __init__(self, database, files, logs):
        self.database, self.files, self.logs = database, files, logs

    def read(self, actor, run_id, *, offset=0, limit=100, action_id=None):
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
                        value["metrics"] = self._model_metrics(
                            row, artifact(row, "request"), artifact(row, "response")
                        )
                    projections[row.id] = value
                return projections[row.id]

            query = select(RunAction).where(RunAction.run_id == run_id)
            total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
            actions = list(
                db.scalars(query.order_by(RunAction.sequence).offset(offset).limit(limit))
            )
            # Failure navigation must work even when the failed action is outside this page.
            failed_query = query.where(
                or_(RunAction.status == "failed", RunAction.error_code.is_not(None))
            )
            failed_total = db.scalar(select(func.count()).select_from(failed_query.subquery())) or 0
            failures = list(db.scalars(failed_query.order_by(RunAction.sequence).limit(20)))
            result = {
                "run": {
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
                    # Historical recovery data is labelled as such, never as a wire response.
                    "saved_tool_feedback": redact(action.result_payload) if diagnostic else None,
                }
        result["logs"] = self.logs.read(run_id) if diagnostic else None
        return result

    @staticmethod
    def _model_metrics(row, request, response):
        """Project numeric evidence only; restricted or truncated files remain unknown."""
        sent = (request.get("document") or {}).get("payload", {})
        received = (response.get("document") or {}).get("payload", {})
        usage = received.get("usage")
        source = "response"
        if not isinstance(usage, dict) or not usage:
            usage = row.safe_details.get("usage")
            source = "action"
        usage = usage if isinstance(usage, dict) else {}
        output_details = usage.get("output_token_details")
        reasoning = output_details.get("reasoning") if isinstance(output_details, dict) else None

        def count(value):
            return value if type(value) is int and value >= 0 else None

        limit_field = "max_completion_tokens" if "max_completion_tokens" in sent else "max_tokens"
        return {
            "usage": {
                **{
                    key: count(usage.get(key))
                    for key in ("input_tokens", "output_tokens", "total_tokens")
                },
                "reasoning_tokens": count(usage.get("reasoning_tokens", reasoning)),
            },
            "usage_source": source if usage else None,
            "output_limit": count(sent.get(limit_field)),
            "output_limit_field": limit_field if count(sent.get(limit_field)) is not None else None,
        }

    @staticmethod
    def _action(row):
        return {
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
        }

    @staticmethod
    def _require_action(db, run_id, action_id):
        row = db.get(RunAction, action_id)
        if not row or row.run_id != run_id:
            raise NotFoundError("action_not_found", "动作不存在。")
        return row

    def _artifact(self, db, file_id, run_id, allowed):
        if not allowed:
            return {"status": "restricted"}
        if not file_id:
            return {"status": "not_collected"}
        file = db.get(StoredFile, file_id)
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

    def download(self, actor, run_id, action_id, direction):
        require_permission(actor, "runs:read")
        require_permission(actor, "agents:read")
        require_permission(actor, "organization_rules:read")
        if direction not in ("request", "response"):
            raise NotFoundError("evidence_not_found", "证据不存在。")
        with self.database.transaction() as db:
            require_run(db, run_id, actor)
            action = self._require_action(db, run_id, action_id)
            file = (
                db.get(StoredFile, getattr(action, direction + "_file_id"))
                if getattr(action, direction + "_file_id")
                else None
            )
            if not file or file.purpose != "evidence" or file.origin_run_id != run_id:
                raise NotFoundError("evidence_not_found", "该动作未采集此项证据。")
            file_id = file.id
        return self.files.read(file_id)
