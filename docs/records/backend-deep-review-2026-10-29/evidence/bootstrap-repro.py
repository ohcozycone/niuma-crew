import asyncio,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import URL
sys.path.insert(0,str(Path.cwd()/'backend'))
import app.bootstrap as boot
from app.config import AppConfig
from app.execution.config import RuntimeConfig
from app.infrastructure.database.session import DatabaseConfig,Database
from app.skills.config import SkillConfig

def config(p,enabled=False):
 return AppConfig(database=DatabaseConfig(URL.create('sqlite+pysqlite',database=str(p/'app.db'))),model_encryption_key_file=p/'key',runner_lock_file=p/'runner.lock',runtime=RuntimeConfig(enabled=enabled),skills=SkillConfig(library_directory=p/'library'))
async def startup_case(p):
 closed=[]; created=[]
 class TrackingDatabase(Database):
  def __init__(self,*a,**k):super().__init__(*a,**k);created.append(self)
  def close(self):closed.append(True);super().close()
 with patch.object(boot,'Database',TrackingDatabase),patch.object(boot,'ToolService',side_effect=RuntimeError('injected construction failure')):
  a=boot.create_app(config(p))
  try:
   async with a.router.lifespan_context(a):pass
  except RuntimeError as e:print('startup_error=',str(e))
 print('startup: databases_created=',len(created),'database_close_calls=',len(closed))
 assert len(created)==1 and not closed
 for db in created:db.close()
async def shutdown_case(p):
 calls=[];created=[]
 class TrackingDatabase(Database):
  def __init__(self,*a,**k):super().__init__(*a,**k);created.append(self)
  def close(self):calls.append('database.close');super().close()
 class Runner:
  def __init__(self,*a,**k):pass
  async def start(self):calls.append('runner.start')
  async def stop(self):calls.append('runner.stop');raise RuntimeError('injected stop failure')
 class Sandboxes:
  def __init__(self,*a,**k):pass
  async def start(self):calls.append('sandboxes.start')
  async def stop(self):calls.append('sandboxes.stop')
 class Files:
  def __init__(self,*a,**k):pass
  async def start(self,*a):calls.append('files.start')
  async def stop(self):calls.append('files.stop')
 class Tools:
  def __init__(self,*a,**k):pass
  async def close(self):calls.append('tools.close')
 with patch.object(boot,'Database',TrackingDatabase),patch.object(boot,'Runner',Runner),patch.object(boot,'SandboxService',Sandboxes),patch.object(boot,'FileService',Files),patch.object(boot,'ToolService',Tools):
  a=boot.create_app(config(p,True))
  try:
   async with a.router.lifespan_context(a):pass
  except RuntimeError as e:print('shutdown_error=',str(e))
 print('shutdown_calls=',calls)
 assert 'runner.stop' in calls and all(x not in calls for x in ['sandboxes.stop','files.stop','tools.close','database.close'])
 for db in created:db.close()
async def main():
 with tempfile.TemporaryDirectory(prefix='niuma-bootstrap-review-') as d:
  await startup_case(Path(d)/'startup');await shutdown_case(Path(d)/'shutdown')
asyncio.run(main())
