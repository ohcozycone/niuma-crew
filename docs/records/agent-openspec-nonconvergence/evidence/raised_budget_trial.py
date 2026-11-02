"""Run the original real agent in a private database copy with raised guard limits.

Credentials remain in the existing vault and are never printed or exported.
The source database, original run, and deployment configuration are never changed.
"""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.bootstrap import create_app
from app.config import load_config

RUN_ID = "215e531a-bb8b-4fee-a47c-b17f69168021"


def backup_database(source: Path, target: Path, *, immutable: bool = False) -> None:
    """Copy a consistent SQLite snapshot without opening the source for writing."""
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    with sqlite3.connect(source.as_uri() + suffix, uri=True) as reader:
        with sqlite3.connect(target) as writer:
            reader.backup(writer)
    target.chmod(0o600)


def prepare(mode: str, directory: Path):
    """Build an isolated copy of the accepted request, preserving frozen inputs."""
    original = load_config()
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    source_db = Path(original.database.url.database)
    copied_db = directory / "app.db"
    backup_database(source_db, copied_db)
    copied_files = directory / "files"
    copied_files.mkdir(mode=0o700)
    with sqlite3.connect(copied_db) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM runs WHERE id=?", (RUN_ID,)).fetchone()
        assert row["status"] == "failed" and row["model_calls"] == 8
        snapshot = json.loads(row["config_snapshot"])
        session = db.execute(
            "SELECT revoked_at FROM auth_sessions WHERE id=?", (row["initiated_by_session_id"],)
        ).fetchone()
        session_binding_refreshed = session is None or session[0] is not None
        if session_binding_refreshed:
            replacement = db.execute(
                "SELECT id FROM auth_sessions WHERE user_id=? AND revoked_at IS NULL "
                "ORDER BY last_seen_at DESC LIMIT 1",
                (row["initiated_by_user_id"],),
            ).fetchone()
            if replacement is None:
                raise RuntimeError(
                    "No current session for the original user; authorization cannot proceed"
                )
            db.execute(
                "UPDATE runs SET initiated_by_session_id=? WHERE id=?", (replacement[0], RUN_ID)
            )
        baseline = {
            key: row[key]
            for key in ("model_calls", "tool_calls", "skill_reads", "started_at", "finished_at")
        }
        baseline["usage"] = json.loads(row["usage"])
        changes = {
            "max_model_calls": (snapshot["max_model_calls"], 24),
            "recursion_limit": (snapshot["recursion_limit"], 256),
            "run_timeout": (snapshot["run_timeout"], 600),
        }
        snapshot.update({key: value[1] for key, value in changes.items()})
        if mode == "resume":
            for file in db.execute(
                "SELECT storage_key FROM stored_files WHERE origin_run_id=?", (RUN_ID,)
            ):
                source = original.files.directory / file["storage_key"]
                shutil.copyfile(source, copied_files / file["storage_key"])
            checkpoint = source_db.with_suffix(".checkpoints.sqlite")
            assert not list(checkpoint.parent.glob(checkpoint.name + "-*"))
            backup_database(
                checkpoint, copied_db.with_suffix(".checkpoints.sqlite"), immutable=True
            )
        else:
            db.execute("DELETE FROM run_actions WHERE run_id=?", (RUN_ID,))
            db.execute("DELETE FROM stored_files WHERE origin_run_id=?", (RUN_ID,))
            db.execute(
                "UPDATE runs SET model_calls=0,tool_calls=0,skill_reads=0,usage=NULL,"
                "checkpoint_id=NULL WHERE id=?",
                (RUN_ID,),
            )
        db.execute(
            "UPDATE runs SET status='queued',error_code=NULL,finished_at=NULL,"
            "cancel_requested_at=NULL,started_at=NULL,config_snapshot=?,revision=revision+1 "
            "WHERE id=?",
            (json.dumps(snapshot, ensure_ascii=False), RUN_ID),
        )
        db.execute("UPDATE conversation_runs SET active=1 WHERE run_id=?", (RUN_ID,))
        binding = db.execute(
            "SELECT reply_message_id FROM conversation_runs WHERE run_id=?", (RUN_ID,)
        ).fetchone()
        db.execute("UPDATE messages SET body=NULL WHERE id=?", (binding[0],))
        db.commit()
    settings = replace(
        original,
        database=replace(original.database, url=original.database.url.set(database=str(copied_db))),
        files=replace(original.files, directory=copied_files),
        skills=replace(
            original.skills,
            directory=original.skills.directory or source_db.parent / "skill-assets",
        ),
        runtime=replace(original.runtime, enabled=False),
        runner_lock_file=directory / "runner.lock",
    )
    evidence = {
        "mode": mode,
        "same_user_session_binding_refreshed": session_binding_refreshed,
        "guard_changes": changes,
        "baseline": baseline,
        "snapshot_identity": {
            "model_id": snapshot["model_id"],
            "provider": snapshot["provider"],
            "system_prompt_sha256": hashlib.sha256(snapshot["system_prompt"].encode()).hexdigest(),
            "tool_names": [item["tool_name"] for item in snapshot["tools"]],
            "input": "OpenSpec 是 skill 还是 mcp ？",
        },
        "isolation": "Private database copy, no source database writes, original vault read only",
        "limitations": [
            "Resume is an experimental reactivation in the copy, not a supported retry of a terminal run.",
            "Fresh retains the original accepted snapshot, rather than recapturing current configuration.",
            "Only the raised model, graph and total-time guards differ from the original snapshot.",
        ],
    }
    (directory / "setup.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    return settings, evidence


def export_result(directory: Path, evidence: dict, elapsed: float) -> dict:
    """Export only task output, safe action metadata, and reported token usage."""
    with sqlite3.connect(directory / "app.db") as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT status,error_code,model_calls,tool_calls,skill_reads,usage "
            "FROM runs WHERE id=?",
            (RUN_ID,),
        ).fetchone()
        result = dict(row)
        result["usage"] = json.loads(result["usage"]) if result["usage"] else None
        reply = db.execute(
            "SELECT m.body FROM messages m JOIN conversation_runs c ON m.id=c.reply_message_id "
            "WHERE c.run_id=?",
            (RUN_ID,),
        ).fetchone()
        result["final_answer"] = reply[0]
        actions = []
        for action in db.execute(
            "SELECT sequence,kind,status,safe_details,error_code,started_at,finished_at "
            "FROM run_actions WHERE run_id=? ORDER BY sequence",
            (RUN_ID,),
        ):
            item = dict(action)
            details = json.loads(item.pop("safe_details"))
            item["details"] = {
                key: details[key]
                for key in ("round", "tool", "model_tool", "query", "finish_reason", "output_bytes")
                if key in details
            }
            actions.append(item)
        result["actions"] = actions
    checkpoint = directory / "app.checkpoints.sqlite"
    if checkpoint.exists():
        with sqlite3.connect(checkpoint) as db:
            row = db.execute(
                "SELECT type,checkpoint FROM checkpoints WHERE thread_id=? "
                "ORDER BY checkpoint_id DESC LIMIT 1",
                (RUN_ID,),
            ).fetchone()
            if row:
                state = JsonPlusSerializer().loads_typed((row[0], row[1]))["channel_values"]
                result["per_model_usage"] = [
                    {"usage": message.usage_metadata, "tool_calls": message.tool_calls}
                    for message in state.get("messages", [])
                    if message.type == "ai"
                ]
    result.update(evidence)
    result["new_execution_seconds"] = elapsed
    if evidence["mode"] == "resume":
        result["new_model_calls"] = result["model_calls"] - evidence["baseline"]["model_calls"]
        result["new_tool_calls"] = result["tool_calls"] - evidence["baseline"]["tool_calls"]
        result["incremental_usage"] = {
            key: value - evidence["baseline"]["usage"][key]
            if value is not None and evidence["baseline"]["usage"].get(key) is not None
            else None
            for key, value in (result["usage"] or {}).items()
        }
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


async def run(mode: str, directory: Path, *, prepare_only: bool) -> None:
    """Use the real coordinator, model, tools, authorization and publisher in the copy."""
    settings, evidence = prepare(mode, directory)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        row, _ = app.state.execution_store.load(RUN_ID)
        app.state.runner.coordinator.authorize(row)
        print(
            json.dumps({"phase": "prepared", "mode": mode, "guards": evidence["guard_changes"]}),
            flush=True,
        )
        if prepare_only:
            return
        started = time.monotonic()
        task = asyncio.create_task(app.state.runner.coordinator.run(RUN_ID))
        while not task.done():
            done, _ = await asyncio.wait([task], timeout=15)
            with app.state.database.transaction() as db:
                from app.execution.models import Run

                row = db.get(Run, RUN_ID)
                print(
                    json.dumps(
                        {
                            "phase": "progress",
                            "mode": mode,
                            "status": row.status,
                            "model_calls": row.model_calls,
                            "tool_calls": row.tool_calls,
                            "elapsed_seconds": round(time.monotonic() - started, 2),
                        }
                    ),
                    flush=True,
                )
            if done:
                break
        await task
        result = export_result(directory, evidence, time.monotonic() - started)
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in [
                        "mode",
                        "status",
                        "error_code",
                        "model_calls",
                        "tool_calls",
                        "usage",
                        "new_execution_seconds",
                        "final_answer",
                    ]
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


def main() -> None:
    """Parse experiment-only settings; never alter deployment environment files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("resume", "fresh"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    asyncio.run(run(args.mode, args.directory.resolve(), prepare_only=args.prepare_only))


if __name__ == "__main__":
    main()
