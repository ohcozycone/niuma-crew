"""Retire real 0011 data without changing ordinary or mixed conversation history."""

import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.operations import Operations

CI_SKILL_ID = "6e69bf0e-84ca-44fd-8afb-d299a63d4381"
BACKEND = Path(__file__).resolve().parents[1]
TIMESTAMP = "2026-10-29T01:02:03.000000Z"


@pytest.fixture
def retirement_database(tmp_path, monkeypatch):
    database = tmp_path / "retirement.db"
    # Isolate all configuration, including .env loading, from the developer setup.
    monkeypatch.setattr(
        "app.config._read_values",
        lambda backend_dir: {
            "DATABASE_URL": "sqlite+pysqlite:///" + str(database),
            "APP_DATA_DIR": str(tmp_path),
        },
    )
    configuration = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(configuration, "0011")
    return SimpleNamespace(path=database, configuration=configuration, directory=tmp_path)


def insert(db, table, **values):
    columns = ",".join(values)
    db.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


def seed_history(path):
    ids = {key: str(uuid4()) for key in ("user", "agent", "ordinary_agent", "ordinary_skill")}
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        insert(db, "users", id=ids["user"], username="retirement-user", role="member")
        insert(
            db,
            "agents",
            id=ids["agent"],
            name="Mixed employee",
            avatar_id="admin",
            ci_repository="example/project",
        )
        insert(db, "agents", id=ids["ordinary_agent"], name="Ordinary", avatar_id="admin")
        insert(db, "skills", id=CI_SKILL_ID, name="Fixed experiment", instructions="Old method")
        insert(
            db,
            "skills",
            id=ids["ordinary_skill"],
            name="CI is just a user skill name",
            instructions="A normal user-owned method",
        )
        for skill in (CI_SKILL_ID, ids["ordinary_skill"]):
            insert(db, "agent_skills", agent_id=ids["agent"], skill_id=skill)

        def conversation(name, agent):
            id = str(uuid4())
            insert(
                db,
                "conversations",
                id=id,
                agent_id=agent,
                owner_user_id=ids["user"],
                title=name,
                last_message_sequence=0,
            )
            ids[name] = id
            return id

        mixed = conversation("mixed", ids["agent"])
        sequences = {}

        def attempt(name, status, *, marker=None, parent=None, conversation_id=None):
            run_id, input_id, reply_id = (str(uuid4()) for _ in range(3))
            current_conversation = conversation_id or conversation(
                name + "_conversation", ids["agent"]
            )
            sequence = sequences.get(current_conversation, 0) + 1
            sequences[current_conversation] = sequence + 1
            snapshot = {
                "schema_version": 3,
                "skills": [],
                "checkpoint_resumable": marker is None,
                "selected_skill_ids": [],
            }
            if marker == "snapshot":
                snapshot["ci"] = {"repository": "example/project"}
            if marker == "work":
                snapshot["work"] = {"kind": "github_ci_diagnosis"}
            terminal = status not in ("queued", "running", "cancelling")
            insert(
                db,
                "runs",
                id=run_id,
                agent_id=ids["agent"],
                owner_user_id=ids["user"],
                initiated_by_user_id=ids["user"],
                initiated_by_session_id=None,
                origin_kind="conversation",
                operation="conversation.send",
                trigger="user",
                mode="execute",
                client_request_id=str(uuid4()),
                request_hash="frozen-request",
                retry_of_run_id=parent,
                config_snapshot=json.dumps(snapshot),
                input_snapshot=json.dumps([{"id": input_id, "role": "user", "content": name}]),
                checkpoint_id="ordinary-checkpoint" if marker is None else None,
                status=status,
                revision=4,
                actions_revision=3,
                model_calls=2,
                skill_reads=1,
                tool_calls=1,
                usage=json.dumps({"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}),
                started_at=TIMESTAMP if status != "queued" else None,
                cancel_requested_at=TIMESTAMP if status == "cancelling" else None,
                finished_at=TIMESTAMP if terminal else None,
            )
            insert(
                db,
                "messages",
                id=input_id,
                conversation_id=current_conversation,
                sequence=sequence,
                role="user",
                body="Original " + name,
            )
            insert(
                db,
                "messages",
                id=reply_id,
                conversation_id=current_conversation,
                sequence=sequence + 1,
                role="assistant",
                body="Delivered " + name if status == "succeeded" else None,
            )
            insert(
                db,
                "conversation_runs",
                run_id=run_id,
                conversation_id=current_conversation,
                input_message_id=input_id,
                reply_message_id=reply_id,
                active=int(not terminal),
            )
            db.execute(
                "UPDATE conversations SET last_message_sequence=? WHERE id=?",
                (sequence + 1, current_conversation),
            )
            ids[name] = run_id
            ids[name + "_reply"] = reply_id
            if marker == "record":
                insert(
                    db,
                    "ci_diagnoses",
                    run_id=run_id,
                    progress_payload=json.dumps({"phase": "collecting"}),
                    revision=2,
                )
            return run_id

        attempt("ordinary_success", "succeeded", conversation_id=mixed)
        attempt("ci_success", "succeeded", marker="snapshot", conversation_id=mixed)
        attempt("ci_failed", "failed", marker="work", conversation_id=mixed)
        attempt("ci_queued", "queued", marker="work", conversation_id=mixed)
        attempt("ci_running", "running", marker="snapshot")
        attempt("ci_cancelling", "cancelling", marker="snapshot")
        attempt("ci_record_only", "running", marker="record")
        attempt("ordinary_active", "running")
        attempt("ordinary_queued", "queued")
        attempt("ci_retry", "failed", marker="work", parent=ids["ci_failed"])
        for name, kind in (
            ("ci_running", "model_call"),
            ("ci_cancelling", "tool_call"),
            ("ci_record_only", "validation"),
            ("ordinary_active", "model_call"),
        ):
            id = str(uuid4())
            insert(
                db,
                "run_actions",
                id=id,
                run_id=ids[name],
                sequence=1,
                action_key=name,
                call_key=name,
                kind=kind,
                status="running",
                safe_details="{}",
                skill_id=None,
                started_at=TIMESTAMP,
            )
            ids[name + "_action"] = id
        insert(
            db,
            "run_actions",
            id=str(uuid4()),
            run_id=ids["ci_success"],
            sequence=1,
            action_key="ci:skill",
            call_key="ci:skill",
            kind="skill_activation",
            skill_id=CI_SKILL_ID,
            status="succeeded",
            safe_details="{}",
            started_at=TIMESTAMP,
            finished_at=TIMESTAMP,
        )
        db.commit()
    return ids


def table_rows(db, table, order="id"):
    return [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}")]


def test_retirement_preserves_mixed_history_and_closes_only_active_ci(retirement_database):
    fixture = retirement_database
    ids = seed_history(fixture.path)
    with closing(sqlite3.connect(fixture.path)) as db:
        db.row_factory = sqlite3.Row
        messages = table_rows(db, "messages")
        all_run_ids = [row["id"] for row in table_rows(db, "runs")]
        snapshots = {row["id"]: row["config_snapshot"] for row in table_rows(db, "runs")}
        ordinary = {
            name: dict(db.execute("SELECT * FROM runs WHERE id=?", (ids[name],)).fetchone())
            for name in ("ordinary_success", "ordinary_active", "ordinary_queued")
        }
        finished_ci = {
            name: dict(db.execute("SELECT * FROM runs WHERE id=?", (ids[name],)).fetchone())
            for name in ("ci_success", "ci_failed", "ci_retry")
        }
        ordinary_action = dict(
            db.execute(
                "SELECT * FROM run_actions WHERE id=?", (ids["ordinary_active_action"],)
            ).fetchone()
        )
        indexes = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE tbl_name='agents' AND type='index'"
            )
        }
    command.upgrade(fixture.configuration, "0020")
    command.upgrade(fixture.configuration, "0020")
    with closing(sqlite3.connect(fixture.path)) as db:
        db.row_factory = sqlite3.Row
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0020"
        assert table_rows(db, "messages") == messages
        assert [row["id"] for row in table_rows(db, "runs")] == all_run_ids
        ordinary_ids = {ids[name] for name in ordinary}
        for row in table_rows(db, "runs"):
            snapshot = json.loads(row["config_snapshot"])
            if row["id"] not in ordinary_ids:
                assert snapshot.pop("retired_work") == "github_ci_diagnosis"
            assert snapshot == json.loads(snapshots[row["id"]])
        record_only = json.loads(
            db.execute(
                "SELECT config_snapshot FROM runs WHERE id=?", (ids["ci_record_only"],)
            ).fetchone()[0]
        )
        assert "ci" not in record_only and "work" not in record_only
        assert record_only["retired_work"] == "github_ci_diagnosis"
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='ci_diagnoses'").fetchall()
        assert "ci_repository" not in {row[1] for row in db.execute("PRAGMA table_info(agents)")}
        for name, before in ordinary.items():
            after = dict(db.execute("SELECT * FROM runs WHERE id=?", (ids[name],)).fetchone())
            assert {key: after[key] for key in before} == before
        for name, before in finished_ci.items():
            after = dict(db.execute("SELECT * FROM runs WHERE id=?", (ids[name],)).fetchone())
            before_without_snapshot = {
                key: value for key, value in before.items() if key != "config_snapshot"
            }
            after.pop("config_snapshot")
            assert {key: after[key] for key in before_without_snapshot} == before_without_snapshot
        assert (
            dict(
                db.execute(
                    "SELECT * FROM run_actions WHERE id=?", (ids["ordinary_active_action"],)
                ).fetchone()
            )
            == ordinary_action
        )
        assert {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE tbl_name='agents' AND type='index'"
            )
        } == indexes
        for name in ("ci_queued", "ci_running", "ci_record_only", "ci_cancelling"):
            row = db.execute("SELECT * FROM runs WHERE id=?", (ids[name],)).fetchone()
            assert row["status"] == ("cancelled" if name == "ci_cancelling" else "interrupted")
            assert row["finished_at"] is not None and row["revision"] == 5
            assert row["model_calls"] == 2 and row["skill_reads"] == 1 and row["tool_calls"] == 1
            assert row["actions_revision"] == (3 if name == "ci_queued" else 4)
            assert not db.execute(
                "SELECT active FROM conversation_runs WHERE run_id=?", (ids[name],)
            ).fetchone()[0]
        model = db.execute(
            "SELECT * FROM run_actions WHERE id=?", (ids["ci_running_action"],)
        ).fetchone()
        tool = db.execute(
            "SELECT * FROM run_actions WHERE id=?", (ids["ci_cancelling_action"],)
        ).fetchone()
        validation = db.execute(
            "SELECT * FROM run_actions WHERE id=?", (ids["ci_record_only_action"],)
        ).fetchone()
        assert model["status"] == tool["status"] == "unknown"
        assert validation["status"] == "interrupted"
        assert model["finished_at"] and tool["finished_at"] and validation["finished_at"]
        usage = json.loads(
            db.execute("SELECT usage FROM runs WHERE id=?", (ids["ci_running"],)).fetchone()[0]
        )
        assert usage and all(value is None for value in usage.values())
        assert (
            json.loads(
                db.execute("SELECT usage FROM runs WHERE id=?", (ids["ci_cancelling"],)).fetchone()[
                    0
                ]
            )["total_tokens"]
            == 18
        )
        assert (
            db.execute("SELECT revision FROM conversations WHERE id=?", (ids["mixed"],)).fetchone()[
                0
            ]
            == 2
        )
        assert (
            db.execute("SELECT revision FROM agents WHERE id=?", (ids["agent"],)).fetchone()[0] == 2
        )
        assert (
            db.execute(
                "SELECT revision FROM agents WHERE id=?", (ids["ordinary_agent"],)
            ).fetchone()[0]
            == 1
        )
        assert [row[0] for row in db.execute("SELECT id FROM skills")] == [ids["ordinary_skill"]]
        assert [row[0] for row in db.execute("SELECT skill_id FROM agent_skills")] == [
            ids["ordinary_skill"]
        ]
        assert (
            db.execute("SELECT skill_id FROM run_actions WHERE action_key='ci:skill'").fetchone()[0]
            is None
        )
        assert (
            db.execute(
                "SELECT retry_of_run_id FROM runs WHERE id=?", (ids["ci_retry"],)
            ).fetchone()[0]
            == ids["ci_failed"]
        )


def test_empty_database_reaches_head_and_preserves_agent_constraints(retirement_database):
    fixture = retirement_database
    command.upgrade(fixture.configuration, "0020")
    with closing(sqlite3.connect(fixture.path)) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0020"
        assert "ci_repository" not in {row[1] for row in db.execute("PRAGMA table_info(agents)")}
        insert(db, "agents", id=str(uuid4()), name="Unique name", avatar_id="admin")
        with pytest.raises(sqlite3.IntegrityError):
            insert(db, "agents", id=str(uuid4()), name="Unique name", avatar_id="admin")
        with pytest.raises(sqlite3.IntegrityError):
            insert(db, "agents", id=str(uuid4()), name=" ", avatar_id="admin")


def test_full_upgrade_sql_contains_retirement_and_no_filesystem_changes(retirement_database):
    fixture = retirement_database
    output = io.StringIO()
    fixture.configuration.output_buffer = output
    command.upgrade(fixture.configuration, "base:head", sql=True)
    sql = output.getvalue()
    assert "DROP TABLE ci_diagnoses" in sql and "DROP COLUMN ci_repository" in sql
    assert "THEN 'unknown'" in sql and "_retiring_ci_runs" in sql
    assert not list(fixture.directory.glob("*.zip"))


def test_downgrade_refuses_to_fake_lost_reports(retirement_database):
    fixture = retirement_database
    command.upgrade(fixture.configuration, "0020")
    with pytest.raises(RuntimeError, match="restore the verified database"):
        command.downgrade(fixture.configuration, "0011")
    with closing(sqlite3.connect(fixture.path)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0020"
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='ci_diagnoses'").fetchall()


def test_retirement_leaves_editable_source_archiving_to_deployment(retirement_database):
    fixture = retirement_database
    source = fixture.directory / "portable-skills" / "old-ci"
    source.mkdir(parents=True)
    document = source / "SKILL.md"
    document.write_text("---\nname: old-ci\n---\nOld CI method\n")
    with closing(sqlite3.connect(fixture.path)) as db:
        insert(
            db,
            "skills",
            id=CI_SKILL_ID,
            name="Old CI",
            instructions="Old method",
            source_path="old-ci",
        )
        db.commit()
    command.upgrade(fixture.configuration, "0020")
    assert document.read_text() == "---\nname: old-ci\n---\nOld CI method\n"
    with closing(sqlite3.connect(fixture.path)) as db:
        assert db.execute("SELECT id FROM skills WHERE id=?", (CI_SKILL_ID,)).fetchone() is None


def test_failed_retirement_rolls_back_states_and_schema_together(retirement_database, monkeypatch):
    fixture = retirement_database
    ids = seed_history(fixture.path)
    with closing(sqlite3.connect(fixture.path)) as db:
        db.row_factory = sqlite3.Row
        before = {
            table: table_rows(db, table, order)
            for table, order in (
                ("runs", "id"),
                ("run_actions", "id"),
                ("messages", "id"),
                ("agents", "id"),
                ("skills", "id"),
                ("ci_diagnoses", "run_id"),
            )
        }
    original = Operations.drop_column

    def failed_drop(operation, table_name, column_name, **kwargs):
        if table_name == "agents" and column_name == "ci_repository":
            raise RuntimeError("injected schema change failure")
        return original(operation, table_name, column_name, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Operations, "drop_column", failed_drop)
        with pytest.raises(RuntimeError, match="injected schema change failure"):
            command.upgrade(fixture.configuration, "0020")
    with closing(sqlite3.connect(fixture.path)) as db:
        db.row_factory = sqlite3.Row
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0011"
        for table, rows in before.items():
            order = "run_id" if table == "ci_diagnoses" else "id"
            assert table_rows(db, table, order) == rows
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute("SELECT id FROM skills WHERE id=?", (CI_SKILL_ID,)).fetchone()[0]
            == CI_SKILL_ID
        )
    command.upgrade(fixture.configuration, "0020")
    with closing(sqlite3.connect(fixture.path)) as db:
        assert (
            db.execute("SELECT status FROM runs WHERE id=?", (ids["ci_running"],)).fetchone()[0]
            == "interrupted"
        )
