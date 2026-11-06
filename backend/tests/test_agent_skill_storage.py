"""Verify configuration persistence and integrity against the actual migrations."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, delete, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.config import DatabaseConfig
from app.infrastructure.database.models import Agent, AgentSkill, Skill
from app.infrastructure.database.session import Database

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(tmp_path, monkeypatch):
    config = DatabaseConfig(
        url=URL.create("sqlite+pysqlite", database=str(tmp_path / "configuration.db"))
    )
    monkeypatch.setenv("DATABASE_URL", config.url.render_as_string(hide_password=False))
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    database = Database(config)
    yield database
    database.close()


def create_assignment(database):
    with database.transaction() as session:
        agent = Agent(name="行政管家", avatar_id="admin")
        skill = Skill(name="文档摘要", instructions="提取结论、依据与待办。")
        session.add_all([agent, skill])
        session.flush()
        session.add(AgentSkill(agent_id=agent.id, skill_id=skill.id))
    return agent.id, skill.id


def test_configuration_survives_reopening_and_skill_is_reusable(database):
    with database.transaction() as session:
        agent = Agent(
            name="  行政管家  ",
            code="OS-001",
            category="财务行政",
            description="整理制度与办公通知。",
            role_label="ADMINISTRATIVE ASSISTANT",
            avatar_id="admin",
            system_prompt="回答需说明依据。",
            is_active=False,
            is_favorite=True,
            example_tasks=["梳理通知重点。"],
            deliverables=["一页摘要"],
        )
        other = Agent(name="行政助理", avatar_id="other")
        skill = Skill(
            name="  文档摘要  ",
            category="知识处理",
            description="提炼文档重点。",
            instructions="先识别主题，再提取结论、依据与待办。",
            input_description="原始文档",
            output_description="结构化摘要",
            example="梳理通知重点。",
        )
        session.add_all([agent, other, skill])
        session.flush()
        for item in (agent, other, skill):
            assert UUID(item.id).version == 4
        assert len({agent.id, other.id, skill.id}) == 3
        session.add_all(
            [AgentSkill(agent_id=item.id, skill_id=skill.id) for item in (agent, other)]
        )
    database.close()
    reopened = Database(DatabaseConfig(url=database.engine.url))
    try:
        with reopened.transaction() as session:
            saved = session.get(Agent, agent.id)
            assert saved.name == "行政管家"
            assert saved.code == "OS-001"
            assert saved.category == "财务行政"
            assert saved.description == "整理制度与办公通知。"
            assert saved.role_label == "ADMINISTRATIVE ASSISTANT"
            assert saved.avatar_id == "admin"
            assert saved.system_prompt == "回答需说明依据。"
            assert saved.revision == 1
            assert saved.is_active is False and saved.is_favorite is True
            assert saved.example_tasks == ["梳理通知重点。"]
            assert saved.deliverables == ["一页摘要"]
            assert saved.created_at.tzinfo is UTC
            assert saved.updated_at == saved.created_at
            definition = session.get(Skill, skill.id)
            assert definition.name == "文档摘要"
            assert definition.category == "知识处理"
            assert definition.description == "提炼文档重点。"
            assert definition.instructions == "先识别主题，再提取结论、依据与待办。"
            assert definition.input_description == "原始文档"
            assert definition.output_description == "结构化摘要"
            assert definition.example == "梳理通知重点。"
            assert set(
                session.scalars(select(AgentSkill.agent_id).where(AgentSkill.skill_id == skill.id))
            ) == {agent.id, other.id}
    finally:
        reopened.close()


def test_defaults_and_in_place_list_edits_are_persisted_without_sharing(database):
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
    with database.transaction() as session:
        first = Agent(name="甲", avatar_id="admin", updated_at=old_time)
        second = Agent(name="乙", avatar_id="admin")
        session.add_all([first, second])
    with database.transaction() as session:
        first = session.get(Agent, first.id)
        created_at = first.created_at
        assert first.code is None and first.role_label is None
        assert first.category == "其他"
        assert first.description == "" and first.system_prompt == ""
        assert first.is_active is True and first.is_favorite is False
        assert first.example_tasks == [] and first.deliverables == []
        first.example_tasks.append("新增示例")
        first.deliverables.append("文档")
    with database.transaction() as session:
        first = session.get(Agent, first.id)
        second = session.get(Agent, second.id)
        assert first.example_tasks == ["新增示例"] and first.deliverables == ["文档"]
        assert second.example_tasks == [] and second.deliverables == []
        assert first.created_at == created_at
        assert first.updated_at > old_time


def test_renaming_keeps_ids_and_saved_ids_cannot_be_reassigned(database):
    agent_id, skill_id = create_assignment(database)
    with database.transaction() as session:
        agent = session.get(Agent, agent_id)
        skill = session.get(Skill, skill_id)
        agent.name = "新名称"
        skill.name = "新技能名称"
        for item in (agent, skill):
            with pytest.raises(ValueError, match="ID 不可修改"):
                item.id = str(uuid4())
    with database.transaction() as session:
        assert session.get(Agent, agent_id).name == "新名称"
        assert session.get(Skill, skill_id).name == "新技能名称"
        assert session.get(AgentSkill, (agent_id, skill_id)) is not None


@pytest.mark.parametrize("operation", ["insert", "update"])
def test_agent_name_unique_index_protects_direct_sql(database, operation):
    from app.employees.service import agent_conflict

    agent_id, _ = create_assignment(database)
    other_id = str(uuid4())
    with database.transaction() as session:
        session.add(Agent(id=other_id, name="小李", avatar_id="admin"))
    with pytest.raises(IntegrityError) as error:
        with database.transaction() as session:
            if operation == "insert":
                session.execute(
                    text("INSERT INTO agents (id, name, avatar_id) VALUES (:id, :name, 'admin')"),
                    {"id": str(uuid4()), "name": "行政管家"},
                )
            else:
                session.execute(
                    text("UPDATE agents SET name = :name WHERE id = :id"),
                    {"id": other_id, "name": "行政管家"},
                )
    conflict = agent_conflict(error.value)
    assert conflict is not None and conflict.code == "agent_name_conflict"
    with database.transaction() as session:
        assert session.get(Agent, agent_id).name == "行政管家"
        assert session.get(Agent, other_id).name == "小李"


def test_optional_values_normalize_to_null_and_codes_are_unique(database):
    with database.transaction() as session:
        first = Agent(name="甲", avatar_id="admin", code=" ", role_label="\t")
        second = Agent(name="乙", avatar_id="admin")
        session.add_all([first, second])
    assert first.code is None and first.role_label is None
    with database.transaction() as session:
        session.get(Agent, first.id).code = " OS-001 "
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.get(Agent, second.id).code = "OS-001"
    with database.transaction() as session:
        assert session.get(Agent, first.id).code == "OS-001"
        assert session.get(Agent, second.id).code is None


@pytest.mark.parametrize("missing", ["agent", "skill"])
def test_assignments_require_existing_records(database, missing):
    agent_id, skill_id = create_assignment(database)
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.add(
                AgentSkill(
                    agent_id=str(uuid4()) if missing == "agent" else agent_id,
                    skill_id=str(uuid4()) if missing == "skill" else skill_id,
                )
            )


def test_duplicate_assignment_is_rejected(database):
    agent_id, skill_id = create_assignment(database)
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.add(AgentSkill(agent_id=agent_id, skill_id=skill_id))


def test_delete_rules_preserve_shared_skills_and_other_agents(database):
    agent_id, skill_id = create_assignment(database)
    with database.transaction() as session:
        other = Agent(name="乙", avatar_id="admin")
        session.add(other)
        session.flush()
        session.add(AgentSkill(agent_id=other.id, skill_id=skill_id))
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.delete(session.get(Skill, skill_id))
    with database.transaction() as session:
        session.delete(session.get(Agent, agent_id))
    with database.transaction() as session:
        assert session.get(AgentSkill, (agent_id, skill_id)) is None
        assert session.get(AgentSkill, (other.id, skill_id)) is not None
        assert session.get(Skill, skill_id) is not None
        session.delete(session.get(Agent, other.id))
    with database.transaction() as session:
        session.delete(session.get(Skill, skill_id))
    with database.transaction() as session:
        assert session.get(Skill, skill_id) is None


def test_agent_edit_and_assignment_replacement_roll_back_together(database):
    agent_id, skill_id = create_assignment(database)
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.get(Agent, agent_id).system_prompt = "尚未提交的修改"
            session.execute(delete(AgentSkill).where(AgentSkill.agent_id == agent_id))
            session.add(AgentSkill(agent_id=agent_id, skill_id=str(uuid4())))
    with database.transaction() as session:
        assert session.get(Agent, agent_id).system_prompt == ""
        assert session.get(AgentSkill, (agent_id, skill_id)) is not None


@pytest.mark.parametrize("field", ["example_tasks", "deliverables"])
@pytest.mark.parametrize("value", [[1], ["合法", None], {"wrong": "shape"}])
def test_json_fields_reject_non_string_arrays(database, field, value):
    with pytest.raises((ValueError, StatementError)):
        with database.transaction() as session:
            session.add(Agent(name="甲", avatar_id="admin", **{field: value}))


@pytest.mark.parametrize(
    "model, values",
    [
        (Agent, {"name": " \n\t\u3000", "avatar_id": "admin"}),
        (Agent, {"name": "甲", "avatar_id": " "}),
        (Skill, {"name": " \n\t\u3000"}),
    ],
)
def test_required_text_is_validated_before_persistence(model, values):
    with pytest.raises(ValueError, match="必填文本"):
        model(**values)


def test_uuid_and_timezone_normalization(database):
    identifier = str(uuid4())
    local_time = datetime(2026, 10, 17, 18, 30, tzinfo=timezone(timedelta(hours=8)))
    with database.transaction() as session:
        agent = Agent(id=identifier.upper(), name="甲", avatar_id="admin", created_at=local_time)
        session.add(agent)
    with database.transaction() as session:
        saved = session.get(Agent, identifier.upper())
        assert saved.id == identifier
        assert saved.created_at == datetime(2026, 10, 17, 10, 30, tzinfo=UTC)
        assert (
            session.execute(
                text("SELECT created_at FROM agents WHERE id = :id"), {"id": identifier}
            ).scalar_one()
            == "2026-10-17T10:30:00.000000Z"
        )
    with pytest.raises(ValueError):
        Agent(id="not-a-uuid", name="甲", avatar_id="admin")
    with pytest.raises(StatementError, match="时区"):
        with database.transaction() as session:
            session.add(Skill(name="技能", created_at=datetime(2026, 10, 17)))


@pytest.mark.parametrize(
    "column, value",
    [
        ("id", None),
        ("name", "   "),
        ("avatar_id", ""),
        ("code", ""),
        ("is_active", 2),
        ("is_favorite", -1),
        ("example_tasks", "not-json"),
        ("example_tasks", "{}"),
        ("deliverables", "null"),
    ],
)
def test_database_constraints_also_protect_direct_sql_writes(database, column, value):
    agent_id, _ = create_assignment(database)
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.execute(
                text(f"UPDATE agents SET {column} = :value WHERE id = :id"),
                {"value": value, "id": agent_id},
            )
