from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.execution.models import ACTIVE, Run, RunAction
from app.files.contracts import FileRetentionCandidate


def model_in_use(db, connection_id):
    return bool(
        db.scalar(
            select(Run.id)
            .where(Run.model_connection_id == connection_id, Run.status.in_(ACTIVE))
            .limit(1)
        )
    )


def retained_file_ids(db: Session, candidates: list[FileRetentionCandidate]) -> set[str]:
    """按执行引用保留输入与成果，不依赖消息关系。"""
    ids = {row.id for row in candidates}
    origins = {row.origin_run_id for row in candidates if row.origin_run_id}
    retained: set[str] = set()
    for request_id, response_id in db.execute(
        select(RunAction.request_file_id, RunAction.response_file_id).where(
            RunAction.run_id.in_(origins)
        )
    ):
        retained.update(value for value in (request_id, response_id) if value in ids)
    active = set(db.scalars(select(Run.id).where(Run.id.in_(origins), Run.status.in_(ACTIVE))))
    retained.update(row.id for row in candidates if row.origin_run_id in active)
    for record in db.execute(
        select(Run.config_snapshot, Run.result_data).execution_options(yield_per=128)
    ):
        snapshot = cast(dict, record[0])
        result = cast(dict | None, record[1])
        refs = [*snapshot.get("input_files", []), *(result or {}).get("output_files", [])]
        retained.update(ref["id"] for ref in refs if ref["id"] in ids)
    details: dict
    for details in db.scalars(
        select(RunAction.safe_details).where(
            RunAction.run_id.in_(origins), RunAction.kind == "tool_call"
        )
    ):
        if details.get("result_file_id") in ids:
            retained.add(details["result_file_id"])
        retained.update(
            source["file_id"]
            for source in cast(list[dict], details.get("sources", []))
            if source.get("file_id") in ids
        )
    return retained & ids
