import json
import tempfile
from pathlib import Path
from alembic import command
from alembic.config import Config
from conftest import app_config
from app.bootstrap import create_app
from app.auth.service import AuthService
from app.infrastructure.database.session import Database
from scenario_client import ScenarioClient

root=Path(tempfile.mkdtemp(prefix='niuma-configuration-review-'))
config=app_config.__wrapped__(root)
import os
os.environ['DATABASE_URL']=config.database.url.render_as_string(hide_password=False)
command.upgrade(Config('/Users/minjo/workspace/niuma-crew/backend/alembic.ini'), 'head')
db=Database(config.database)
AuthService(db,config.auth).initialize_admin('admin','fixture-password')
db.close()
with ScenarioClient(create_app(config),headers={'Origin':'http://localhost:3000','Content-Type':'application/json'}) as c:
    assert c.post('/api/auth/login',json={'username':'admin','password':'fixture-password'}).status_code==200
    a=c.post('/api/agents',json={'name':'未绑定','avatar_id':'admin'}).json()
    results={'empty_connections_unconfigured':c.get('/api/agents?model_configured=false').json()['total']}
    enabled=c.post('/api/model-connections',json={'name':'已启用','api_key':'fake-offline-key'}).json()
    disabled=c.post('/api/model-connections',json={'name':'停用','api_key':'fake-offline-key','enabled':False}).json()
    b=c.post('/api/agents',json={'name':'可用绑定','avatar_id':'admin','model_connection_id':enabled['id']}).json()
    d=c.post('/api/agents',json={'name':'后来停用','avatar_id':'admin','model_connection_id':enabled['id']}).json()
    # Switch d to a second live connection then disable it, as disabled binding is rejected on writes.
    c.patch('/api/model-connections/'+disabled['id'],json={'expected_config_revision':1,'expected_credential_revision':1,'enabled':True})
    c.patch('/api/agents/'+d['id'],json={'expected_revision':1,'model_connection_id':disabled['id']})
    c.patch('/api/model-connections/'+disabled['id'],json={'expected_config_revision':2,'expected_credential_revision':1,'enabled':False})
    results['all_names']=[i['name'] for i in c.get('/api/agents').json()['items']]
    results['configured_true']=[i['name'] for i in c.get('/api/agents?model_configured=true').json()['items']]
    results['configured_false']=[i['name'] for i in c.get('/api/agents?model_configured=false').json()['items']]
    c.post('/api/auth/guest',json={})
    results['public_configured_false']=[i['name'] for i in c.get('/api/public/agents?model_configured=false').json()['items']]
    p=c.get('/api/public/agents/'+d['id']).json()
    results['disabled_public_model_configured']=p['model_configured']
    before=c.get('/api/agents/'+a['id']).json()
    patch=c.patch('/api/agents/'+a['id'],json={'expected_revision':before['revision'],'tool_grants':[]}).json()
    results['empty_grants_patch_revision']=[before['revision'],patch['revision']]
    put=c.put('/api/agents/'+a['id']+'/tool-grants',json={'expected_revision':patch['revision'],'grants':[]}).json()
    results['empty_grants_put_revision']=put['agent_revision']
    import io, base64, zipfile
    from fastapi.testclient import TestClient
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('SKILL.md', '---\nname: broken\ndescription: Corrupt fixture\n---\nRead.')
    corrupt = bytearray(stream.getvalue())
    with zipfile.ZipFile(io.BytesIO(corrupt)) as archive:
        info = archive.infolist()[0]
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        corrupt[offset:offset+info.compress_size] = b'\xff' * info.compress_size
    raw_client = TestClient(c.app, headers=c.headers, cookies=c.cookies, raise_server_exceptions=False)
    try:
        result = raw_client.post('/api/skills/import/preview', json={'archive_base64': base64.b64encode(corrupt).decode()})
        results['corrupt_zip_preview_status'] = result.status_code
        results['corrupt_zip_preview_body'] = result.text
    finally:
        raw_client.close()
    print(json.dumps(results,ensure_ascii=False,indent=2))
