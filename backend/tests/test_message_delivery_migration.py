"""0004 -> 0005 keeps content, rejects unknown formats and rolls back DDL."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from legacy_execution_helpers import seed_legacy
from sqlalchemy import URL


def old_database(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setenv("DATABASE_URL", str(URL.create("sqlite+pysqlite", database=str(path))))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    ids = seed_legacy(config, path)
    command.upgrade(config, "0004")
    return path, config, ids


def test_plain_history_partial_empty_reply_and_checkpoint_are_preserved(tmp_path, monkeypatch):
    path, config, ids = old_database(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM ci_feedback")
        db.execute("UPDATE runs SET progress_payload=NULL")
        db.execute("UPDATE run_results SET structured=NULL")
        replies = dict(db.execute("SELECT run_id,response_id FROM conversation_runs"))
    digest = hashlib.sha256(ids["checkpoint"].read_bytes()).digest()
    command.upgrade(config, "0005")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM ci_diagnoses").fetchone() == (0,)
        bodies = dict(db.execute("SELECT id,body FROM messages"))
        assert len(bodies) == 5
        assert bodies[ids["user"]] == "原始问题"
        assert bodies[replies[ids["first"]]] == "正式回答"
        assert bodies[replies[ids["failed"]]] == "失败片段"
        assert bodies[replies[ids["active"]]] is None
        assert dict(db.execute("SELECT run_id,reply_message_id FROM conversation_runs")) == replies
        assert not {"run_results", "ci_feedback"} & {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert hashlib.sha256(ids["checkpoint"].read_bytes()).digest() == digest
    with pytest.raises(RuntimeError, match="cannot losslessly"):
        command.downgrade(config, "0004")
    command.upgrade(config, "0020")
    with sqlite3.connect(path) as db:
        assert dict(db.execute("SELECT id,body FROM messages")) == bodies
        assert dict(db.execute("SELECT run_id,reply_message_id FROM conversation_runs")) == replies
        assert db.execute("SELECT count(*) FROM runs").fetchone() == (3,)
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='ci_diagnoses'").fetchall() == []
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert hashlib.sha256(ids["checkpoint"].read_bytes()).digest() == digest


@pytest.mark.parametrize("failure", ["unknown_professional", "missing_answer", "wrong_input"])
def test_preflight_errors_leave_the_old_schema_and_data_untouched(tmp_path, monkeypatch, failure):
    path, config, ids = old_database(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        if failure != "unknown_professional":
            db.execute("DELETE FROM ci_feedback")
            db.execute("UPDATE runs SET progress_payload=NULL")
            db.execute("UPDATE run_results SET structured=NULL")
        if failure == "missing_answer":
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("DELETE FROM run_results WHERE output_key='answer'")
        if failure == "wrong_input":
            db.execute(
                "UPDATE conversation_runs SET input_message_id=? WHERE run_id=?",
                (ids["answer"], ids["failed"]),
            )
    with sqlite3.connect(path) as db:
        before = list(db.iterdump())
    with pytest.raises(RuntimeError):
        command.upgrade(config, "0020")
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004",)


def test_validated_ci_report_progress_and_feedback_keep_their_owner(tmp_path, monkeypatch):
    path, config, ids = old_database(tmp_path, monkeypatch)
    target = {"repository": "owner/repo", "run_id": "99", "attempt": 1, "head_sha": "abc"}
    coverage = {
        "enumerated_jobs": 1,
        "failed_job_ids": ["7"],
        "uninvestigated_job_ids": [],
        "partial": False,
    }
    report = {
        "summary": "已观察到失败",
        "findings": [
            {
                "job_id": "7",
                "verdict": "observed",
                "explanation": "测试失败",
                "evidence": [{"source_id": "S1", "start_line": 1, "end_line": 1}],
                "next_step": "检查断言",
                "verification": "重新运行测试",
            }
        ],
        "unknowns": [],
        "coverage": coverage,
        "target": target,
    }
    candidate = {
        "phase": "delivered",
        "calls": [],
        "sources": [
            {
                "id": "S1",
                "job_id": "7",
                "text": "assert failed",
                "sha256": hashlib.sha256(b"assert failed").hexdigest(),
            }
        ],
        "report": report,
        "coverage": coverage,
        "target": target,
    }
    feedback = {"decision": "useful", "note": "有帮助", "created_at": "2026-10-27T00:00:00Z"}
    with sqlite3.connect(path) as db:
        snapshot = json.loads(
            db.execute("SELECT config_snapshot FROM runs WHERE id=?", (ids["first"],)).fetchone()[0]
        )
        snapshot["ci"] = {"repository": "owner/repo"}
        snapshot["work"] = {"kind": "github_ci_diagnosis"}
        db.execute(
            "UPDATE runs SET config_snapshot=?,progress_payload=? WHERE id=?",
            (json.dumps(snapshot), json.dumps(candidate), ids["first"]),
        )
        db.execute(
            "UPDATE run_results SET structured=? WHERE run_id=?",
            (json.dumps(candidate), ids["first"]),
        )
        db.execute(
            "UPDATE ci_feedback SET payload=? WHERE run_id=?", (json.dumps(feedback), ids["first"])
        )
    command.upgrade(config, "0005")
    with sqlite3.connect(path) as db:
        progress, saved_report, saved_feedback = db.execute(
            "SELECT progress_payload,report,feedback FROM ci_diagnoses WHERE run_id=?",
            (ids["first"],),
        ).fetchone()
        assert json.loads(saved_report) == report
        assert json.loads(saved_feedback) == feedback
        assert json.loads(progress)["phase"] == "delivered"
        assert "report" not in json.loads(progress)
    with sqlite3.connect(path) as db:
        before_bodies = dict(db.execute("SELECT id,body FROM messages"))
        before_runs = dict(db.execute("SELECT id,status FROM runs"))
    command.upgrade(config, "0020")
    with sqlite3.connect(path) as db:
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='ci_diagnoses'").fetchall() == []
        )
        assert dict(db.execute("SELECT id,body FROM messages")) == before_bodies
        assert dict(db.execute("SELECT id,status FROM runs")) == before_runs
        snapshot = json.loads(
            db.execute("SELECT config_snapshot FROM runs WHERE id=?", (ids["first"],)).fetchone()[0]
        )
        assert snapshot["retired_work"] == "github_ci_diagnosis"
        assert snapshot["ci"] == {"repository": "owner/repo"}
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
