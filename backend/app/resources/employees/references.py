from sqlalchemy import func, select

from app.common.errors import ConflictError
from app.resources.employees.models import Agent, AgentSkill


def skill_assignments(db, skill_ids):
    """调用方事务中的装配事实；返回普通值，不泄漏可变记录。"""
    return [
        dict(skill_id=row.skill_id, enabled=row.enabled, parameters=row.parameters)
        for row in db.scalars(select(AgentSkill).where(AgentSkill.skill_id.in_(skill_ids)))
    ]


def model_employees(db, connection_id):
    return [
        dict(id=id, name=name)
        for id, name in db.execute(
            select(Agent.id, Agent.name)
            .where(Agent.model_connection_id == connection_id)
            .order_by(Agent.name, Agent.id)
        )
    ]


def assert_model_unused(db, connection_id):
    if model_employees(db, connection_id):
        raise ConflictError("model_connection_in_use", "仍有员工使用这个大脑，请先更换或解除装配。")


def employee_active(db, id):
    row = db.get(Agent, id)
    return row is not None and row.is_active


def skill_assignment_counts(db, ids):
    return dict(
        db.execute(
            select(AgentSkill.skill_id, func.count())
            .where(AgentSkill.skill_id.in_(ids))
            .group_by(AgentSkill.skill_id)
        ).all()
    )
