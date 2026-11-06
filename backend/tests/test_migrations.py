"""The frozen Agent baseline, incremental migrations and atomic migration failure."""

import hashlib
import io
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from legacy_execution_helpers import seed_legacy
from sqlalchemy import URL

BACKEND_DIR = Path(__file__).resolve().parents[1]
TABLES = {
    "evaluation_batches",
    "evaluation_cases",
    "identifier_sequence",
    "users",
    "auth_sessions",
    "external_identities",
    "agents",
    "skills",
    "agent_skills",
    "model_connections",
    "organization_rules",
    "conversations",
    "runs",
    "run_actions",
    "messages",
    "conversation_runs",
    "tool_connections",
    "mcp_services",
    "personal_tool_bindings",
    "agent_tool_grants",
    "stored_files",
    "message_files",
    "sandbox_resources",
    "knowledge_bases",
    "knowledge_documents",
    "knowledge_chunks",
    "knowledge_vector_indexes",
    "knowledge_vector_memberships",
    "knowledge_processing_batches",
    "knowledge_processing_items",
    "knowledge_employee_settings",
    "knowledge_employee_libraries",
    "knowledge_run_evidence",
}

FTS_TABLES = {"knowledge_fts"} | {
    "knowledge_fts_" + part for part in ("data", "idx", "content", "docsize", "config")
}


def test_initial_migration_cli_is_repeatable_and_cwd_independent(tmp_path):
    path = tmp_path / "nested/平台 % database.db"
    env = {**os.environ, "DATABASE_URL": str(URL.create("sqlite+pysqlite", database=str(path)))}

    def run(*args, expected_success=True):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(BACKEND_DIR / "alembic.ini"), *args],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
        )
        if expected_success:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout + result.stderr
        return result

    run("upgrade", "head", "--sql")
    assert not path.exists()
    # The historical empty schema remains reversible before the retirement.
    run("upgrade", "0011")
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM ci_diagnoses").fetchone() == (0,)
        assert "ci_repository" in {row[1] for row in db.execute("PRAGMA table_info(agents)")}
    run("downgrade", "base")
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("alembic_version",)
        ]
        assert db.execute("SELECT count(*) FROM alembic_version").fetchone() == (0,)
    run("upgrade", "head")
    run("upgrade", "head")
    run("check")
    assert "0024" in run("current").stdout
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [("0024",)]
        assert {"thread_id", "base_checkpoint_id", "base_run_id"} <= {
            column[1] for column in db.execute("PRAGMA table_info(runs)")
        }
        assert "ci_repository" not in {row[1] for row in db.execute("PRAGMA table_info(agents)")}
        assert db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        } == TABLES | FTS_TABLES | {"alembic_version"}
        for table in TABLES:
            expected = 1 if table in {"organization_rules", "identifier_sequence"} else 0
            assert db.execute(f'SELECT count(*) FROM "{table}"').fetchone() == (expected,)
        assert db.execute("SELECT instructions, revision FROM organization_rules").fetchone() == (
            "",
            0,
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
    rejected = run("downgrade", "base", expected_success=False)
    assert "执行证据不支持有损降级" in rejected.stderr
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0024",)
        assert {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        } == TABLES | FTS_TABLES | {"alembic_version"}
    run("check")


def test_offline_initial_sql_can_initialize_a_database(tmp_path, monkeypatch):
    path = tmp_path / "from-sql.db"
    monkeypatch.setenv("DATABASE_URL", str(URL.create("sqlite+pysqlite", database=str(path))))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    output = io.StringIO()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    assert not path.exists()
    with sqlite3.connect(path) as db:
        db.executescript(output.getvalue())
        assert {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        } == TABLES | FTS_TABLES | {"alembic_version"}
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    command.check(config)


def test_failed_migration_rolls_back_ddl_and_revision(tmp_path, monkeypatch):
    path = tmp_path / "rollback.db"
    monkeypatch.setenv("DATABASE_URL", str(URL.create("sqlite+pysqlite", database=str(path))))
    scripts = tmp_path / "migrations"
    shutil.copytree(
        BACKEND_DIR / "migrations", scripts, ignore=shutil.ignore_patterns("__pycache__")
    )
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(scripts))
    command.upgrade(config, "head")
    previous_head = ScriptDirectory.from_config(config).get_current_head()
    (scripts / "versions/9999_failure.py").write_text(
        f'from alembic import op\nrevision = "9999"\ndown_revision = "{previous_head}"\n'
        'def upgrade():\n    op.execute("CREATE TABLE unfinished (id INTEGER PRIMARY KEY)")\n'
        '    raise RuntimeError("injected failure")\n'
        "def downgrade():\n    pass\n"
    )
    with pytest.raises(RuntimeError, match="injected failure"):
        command.upgrade(config, "head")
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (previous_head,)
        ]
        assert db.execute("SELECT name FROM sqlite_master WHERE name='unfinished'").fetchall() == []
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_unique_agent_name_upgrade_rejects_duplicates_without_changes(tmp_path, monkeypatch):
    path = tmp_path / "duplicate-agents.db"
    monkeypatch.setenv("DATABASE_URL", str(URL.create("sqlite+pysqlite", database=str(path))))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "0002")
    with sqlite3.connect(path) as db:
        for _ in range(2):
            db.execute(
                "INSERT INTO agents (id, name, avatar_id) VALUES (?, '老赵', 'admin')",
                (str(uuid4()),),
            )
    with pytest.raises(RuntimeError, match="现有员工名称重复"):
        command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [("0002",)]
        assert db.execute("SELECT count(*) FROM agents WHERE name = '老赵'").fetchone() == (2,)
        assert "ix_agents_name" not in {
            index[1] for index in db.execute("PRAGMA index_list(agents)")
        }
        db.execute("UPDATE agents SET name = '小李' WHERE rowid = (SELECT min(rowid) FROM agents)")
    command.upgrade(config, "head")
    command.check(config)


def migration_config(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_URL", str(URL.create("sqlite+pysqlite", database=str(path))))
    return path, Config(str(BACKEND_DIR / "alembic.ini"))


def test_execution_upgrade_preserves_content_links_and_does_not_rewrite_sdk(tmp_path, monkeypatch):
    path, config = migration_config(tmp_path, monkeypatch)
    ids = seed_legacy(config, path)
    checkpoint_digest = hashlib.sha256(ids["checkpoint"].read_bytes()).hexdigest()
    command.upgrade(config, "0004")
    assert hashlib.sha256(ids["checkpoint"].read_bytes()).hexdigest() == checkpoint_digest
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert db.execute("SELECT count(*) FROM messages").fetchone() == (3,)
        assert db.execute("SELECT body FROM messages WHERE id=?", (ids["user"],)).fetchone() == (
            "原始问题",
        )
        assert dict(db.execute("SELECT output_key,content FROM run_results")) == {
            "answer": "正式回答",
            "partial": "失败片段",
        }
        assert db.execute("SELECT result_id FROM messages WHERE id=?", (ids["answer"],)).fetchone()[
            0
        ]
        assert db.execute("SELECT status FROM runs WHERE id=?", (ids["active"],)).fetchone() == (
            "interrupted",
        )
        assert db.execute("SELECT status FROM run_actions").fetchone() == ("unknown",)
        assert db.execute("SELECT sum(active) FROM conversation_runs").fetchone() == (0,)
        import json

        inputs = json.loads(
            db.execute("SELECT input_snapshot FROM runs WHERE id=?", (ids["active"],)).fetchone()[0]
        )
        assert [item["content"] for item in inputs] == ["原始问题", "正式回答", "后续问题"]
        assert json.loads(db.execute("SELECT payload FROM ci_feedback").fetchone()[0]) == {
            "accepted": True
        }
        assert "conversation_id" not in {row[1] for row in db.execute("PRAGMA table_info(runs)")}
        assert "checkpoint_id" not in {
            row[1] for row in db.execute("PRAGMA table_info(conversations)")
        }
    with pytest.raises(RuntimeError, match="不支持有损降级"):
        command.downgrade(config, "0003")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004",)
        assert db.execute("SELECT count(*) FROM messages").fetchone() == (3,)


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_execution_upgrade_preflights_history_and_preserves_old_database(
    tmp_path, monkeypatch, failure
):
    path, config = migration_config(tmp_path, monkeypatch)
    ids = seed_legacy(config, path)
    with sqlite3.connect(path) as db:
        before = db.execute("SELECT * FROM runs ORDER BY id").fetchall()
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    if failure == "missing":
        ids["checkpoint"].unlink()
    else:
        ids["checkpoint"].write_bytes(b"not a sqlite database")
    with pytest.raises(RuntimeError, match="checkpoint"):
        command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0003",)
        assert db.execute("SELECT * FROM runs ORDER BY id").fetchall() == before
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            == tables
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_remove_duplicate_checkpoint_revision_preserves_legacy_data(tmp_path, monkeypatch):
    path, config = migration_config(tmp_path, monkeypatch)
    ids = seed_legacy(config, path, "0001")

    def rows():
        with sqlite3.connect(path) as db:
            columns = [
                row[1]
                for row in db.execute("PRAGMA table_info(runs)")
                if row[1] != "base_checkpoint_id"
            ]
            return db.execute("SELECT " + ",".join(columns) + " FROM runs ORDER BY id").fetchall()

    before = rows()
    command.upgrade(config, "0002")
    assert rows() == before
    command.downgrade(config, "0001")
    assert rows() == before
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT base_checkpoint_id FROM runs WHERE id=?", (ids["active"],)
        ).fetchone()[0]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_unique_name_revision_keeps_existing_identity(tmp_path, monkeypatch):
    path, config = migration_config(tmp_path, monkeypatch)
    command.upgrade(config, "0002")
    id = str(uuid4())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO agents (id,name,avatar_id) VALUES (?,'老赵','admin')", (id,))
    command.upgrade(config, "0003")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id,name FROM agents").fetchall() == [(id, "老赵")]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO agents (id,name,avatar_id) VALUES (?,'老赵','admin')", (str(uuid4()),)
            )
    command.upgrade(config, "head")
    command.check(config)


def test_mcp_account_upgrade_preserves_secrets_and_defaults_legacy_mcp_to_personal(
    tmp_path, monkeypatch
):
    path = tmp_path / "mcp-legacy.db"
    monkeypatch.setenv("DATABASE_URL", str(URL.create("sqlite+pysqlite", database=str(path))))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "0006")
    user_id, connection_id, agent_id, grant_id = [str(uuid4()) for _ in range(4)]
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO users (id,username,role) VALUES (?, 'legacy','member')", (user_id,))
        db.execute(
            "INSERT INTO agents (id,name,avatar_id) VALUES (?, 'legacy','admin')", (agent_id,)
        )
        db.execute(
            "INSERT INTO tool_connections (id,name,kind,auth_type,public_config,encrypted_credentials,approved_catalog,enabled,config_revision,credential_revision,catalog_revision,created_by_user_id) VALUES (?, 'legacy','mcp_http','bearer',?, 'opaque-preserved-ciphertext','[]',1,1,1,1,?)",
            (connection_id, '{"url":"https://mcp.tavily.com/mcp"}', user_id),
        )
        db.execute(
            "INSERT INTO agent_tool_grants (id,agent_id,tool_connection_id,tools,scope_policy,enabled,revision) VALUES (?,?,?,'[]','{}',1,1)",
            (grant_id, agent_id, connection_id),
        )
    command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT service_id,account_scope,encrypted_credentials FROM tool_connections"
        ).fetchone() == (connection_id, "personal", "opaque-preserved-ciphertext")
        assert db.execute("SELECT owner_user_id FROM mcp_services").fetchone() == (user_id,)
        assert db.execute("SELECT account_mode FROM agent_tool_grants").fetchone() == ("personal",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    command.check(config)


def test_thread_upgrade_preserves_legacy_runs_and_checkpoint_file(tmp_path, monkeypatch):
    path, config = migration_config(tmp_path, monkeypatch)
    ids = seed_legacy(config, path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE runs SET ci_result = NULL, ci_feedback = NULL")
    command.upgrade(config, "0019")
    checkpoint_digest = hashlib.sha256(ids["checkpoint"].read_bytes()).hexdigest()
    with sqlite3.connect(path) as db:
        before = db.execute(
            "SELECT id,status,input_snapshot,result_text,checkpoint_id FROM runs ORDER BY id"
        ).fetchall()
    command.upgrade(config, "0020")
    with sqlite3.connect(path) as db:
        assert (
            db.execute(
                "SELECT id,status,input_snapshot,result_text,checkpoint_id FROM runs ORDER BY id"
            ).fetchall()
            == before
        )
        assert all(id == thread for id, thread in db.execute("SELECT id,thread_id FROM runs"))
        assert db.execute(
            "SELECT count(*) FROM runs WHERE base_run_id IS NOT NULL OR base_checkpoint_id IS NOT NULL"
        ).fetchone() == (0,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
    assert hashlib.sha256(ids["checkpoint"].read_bytes()).hexdigest() == checkpoint_digest


def test_thread_downgrade_rejects_shared_state_before_changing_schema(tmp_path, monkeypatch):
    path, config = migration_config(tmp_path, monkeypatch)
    seed_legacy(config, path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE runs SET ci_result = NULL, ci_feedback = NULL")
    command.upgrade(config, "0020")
    with sqlite3.connect(path) as db:
        db.execute("UPDATE runs SET thread_id = 'conversation:legacy'")
    with pytest.raises(RuntimeError, match="Shared thread history"):
        command.downgrade(config, "0019")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0020",)
        assert {"thread_id", "base_run_id", "base_checkpoint_id"} <= {
            column[1] for column in db.execute("PRAGMA table_info(runs)")
        }


def test_numeric_upgrade_rejects_existing_execution_rows_without_changing_them(
    tmp_path, monkeypatch
):
    path, config = migration_config(tmp_path, monkeypatch)
    seed_legacy(config, path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE runs SET ci_result = NULL, ci_feedback = NULL")
    command.upgrade(config, "0020")
    with sqlite3.connect(path) as db:
        before = db.execute("SELECT id,status,result_text FROM runs ORDER BY id").fetchall()
    with pytest.raises(RuntimeError, match="仅支持空库"):
        command.upgrade(config, "head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0020",)
        assert db.execute("SELECT id,status,result_text FROM runs ORDER BY id").fetchall() == before
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
