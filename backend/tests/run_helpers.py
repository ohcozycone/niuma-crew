"""Drive separate execution completion and business adoption in lifecycle scenarios."""


def complete_run(client):
    def complete(intent):
        client.app.state.runs.complete(intent)
        client.app.state.conversation_acceptance.process(intent.run_id)

    return complete


def scenario_database(client):
    """进程内客户端使用应用数据库，进程恢复测试显式持有同一临时库。"""
    return client.app.state.database if hasattr(client, "app") else client.database


def empty_conversation(client, agent_id):
    """为读取/运行场景建立空对话夹具；首次发送契约另经真实 HTTP 验证。"""
    from app.conversations.queries import read_conversation
    from app.conversations.writes import create_conversation

    actor = client.app.state.auth.resolve(client.cookies.get("app_session"))
    with scenario_database(client).transaction() as db:
        row = create_conversation(db, agent_id, actor.user_id)
        return read_conversation(db, row).model_dump(mode="json")


def checkpoint_store(client):
    return client.app.state.run_worker.task_factory.keywords["checkpoints"]


def reply_path(client, reply_id):
    from sqlalchemy import select

    from app.conversations.models import ConversationRun

    with scenario_database(client).transaction() as db:
        conversation = db.scalar(
            select(ConversationRun.conversation_id).where(ConversationRun.run_id == reply_id)
        )
        assert conversation is not None, reply_id
        return f"/api/conversations/{conversation}/responses/{reply_id}"


def read_reply(client, reply_id):
    result = client.get(reply_path(client, reply_id))
    assert result.status_code == 200, result.text
    return result.json()["response"]


def latest_model(reply):
    if reply["status"] not in ("queued", "running", "cancelling"):
        return None
    return next((step for step in reversed(reply["steps"]) if step["kind"] == "model_call"), None)


def active_step(reply):
    if reply["status"] not in ("queued", "running", "cancelling"):
        return None
    return next((step for step in reversed(reply["steps"]) if step["status"] == "running"), None)


def load_run(client, id):
    from app.execution.models import Run

    with scenario_database(client).transaction() as db:
        return db.get(Run, id)


def cancel_run(client, id):
    """供无对话宿主测试在自己的事务里请求取消。"""
    from app.execution.store import require_run

    with scenario_database(client).transaction() as db:
        client.app.state.runs.cancel(db, require_run(db, id))


async def execute_run(client, run_id):
    """直接驱动真实单次任务；持续调度另由 Worker 测试覆盖。"""
    worker = client.app.state.run_worker
    await worker.task_factory(run_id, worker._complete).execute()
