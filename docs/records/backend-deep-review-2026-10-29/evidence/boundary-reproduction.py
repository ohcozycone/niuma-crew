from dataclasses import replace
from pathlib import Path

from conftest import api_client, migrated_config, app_config
from sqlalchemy import func, select
from app.files.models import StoredFile
from app.errors import InvalidInputError
from test_mcp_accounts import member
from test_capability_runtime import setup
from test_agent_foundations import send, run_id
from app.sandboxes.models import SandboxResource
from app.infrastructure.database.fields import utc_now
from datetime import timedelta


def test_quota_rejection_leaves_finalized_bytes(api_client):
    files = api_client.app.state.files
    actor = api_client.app.state.auth.resolve(api_client.cookies.get('app_session'))
    files.config = replace(files.config, max_owner_bytes=1)
    files.save(actor.user_id, 'ok.txt', b'x')
    rejected = 0
    for _ in range(3):
        try:
            files.save(actor.user_id, 'rejected.txt', b'xx')
        except InvalidInputError as error:
            assert error.code == 'file_quota_exceeded'
            rejected += 1
    with files.database.transaction() as db:
        rows = db.scalar(select(func.count()).select_from(StoredFile))
        accounted_bytes = db.scalar(select(func.sum(StoredFile.size)))
    finalized = [p for p in files.directory.iterdir() if not p.name.startswith('.')]
    actual_bytes = sum(p.stat().st_size for p in finalized)
    print({'rejected_uploads': rejected, 'metadata_rows': rows, 'accounted_bytes': accounted_bytes, 'finalized_files': len(finalized), 'actual_bytes': actual_bytes})
    assert rows == 1 and accounted_bytes == 1
    assert len(finalized) == 4 and actual_bytes == 7


def test_member_reads_other_users_sandbox_resource(api_client):
    _, _, _, conversation = setup(api_client)
    accepted = send(api_client, conversation)
    rid = run_id(api_client, accepted)
    with api_client.app.state.database.transaction() as db:
        db.add(SandboxResource(run_id=rid, deployment_id='review', server_identity='review', state='unknown', expires_at=utc_now()+timedelta(minutes=4), last_error='sandbox_create_unknown'))
    actor = member(api_client)
    response = api_client.get('/api/sandbox-status')
    print({'member_status': response.status_code, 'foreign_run_visible': any(r['run_id'] == rid for r in response.json()['resources'])})
    assert response.status_code == 200
    assert any(r['run_id'] == rid for r in response.json()['resources'])


def test_personal_connection_route_is_not_served_by_backend(tmp_path):
    from fastapi import FastAPI
    from scenario_client import ScenarioClient as TestClient
    from app.api.frontend_delivery import mount_frontend
    (tmp_path / 'index.html').write_text('<html>client-root</html>')
    app = FastAPI()
    mount_frontend(app, tmp_path)
    client = TestClient(app)
    known = client.get('/agents/review-agent')
    personal = client.get('/agents/review-agent/connections')
    print({'agent_route': known.status_code, 'personal_connection_route': personal.status_code})
    assert known.status_code == 200
    assert personal.status_code == 404
