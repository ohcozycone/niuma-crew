"""普通测试的迁移夹具不能替代真实应用进程的模型注册。"""

import subprocess
import sys
from pathlib import Path

from app.infrastructure.database.session import Database
from app.resources.environments.legacy_models import WorkspaceProfile


def test_fresh_application_process_registers_and_reads_legacy_native_connection(migrated_config):
    database = Database(migrated_config.database)
    try:
        with database.transaction() as db:
            legacy = WorkspaceProfile(name="历史只读工作区", enabled=False)
            db.add(legacy)
            db.flush()
            identifier = legacy.id
    finally:
        database.close()
    code = """
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import URL
from app.bootstrap.app import create_app
from app.config import AppConfig, DatabaseConfig
from app.resources.skills.config import SkillConfig
from app.resources.mcp.models import ToolConnection
from app.runtime.execution.config import RuntimeConfig
root = Path(sys.argv[1])
config = AppConfig(database=DatabaseConfig(url=URL.create('sqlite+pysqlite',database=str(root/'app.db'))),
    model_encryption_key_file=root/'secrets/model-connections.key', runner_lock_file=root/'runtime/runner.lock',
    runtime=RuntimeConfig(enabled=False), skills=SkillConfig(library_directory=root/'.agents/skills'))
with TestClient(create_app(config)) as client:
    with client.app.state.database.transaction() as db:
        row = db.get(ToolConnection, sys.argv[2])
        assert row.kind == 'native' and not row.enabled
        assert type(row).__module__ == 'app.resources.environments.legacy_models'
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(Path(migrated_config.database.url.database).parent),
            identifier,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
