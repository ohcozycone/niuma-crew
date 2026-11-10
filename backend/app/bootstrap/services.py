from app.conversations.references import assert_employee_unused as conversation_history
from app.employees.references import assert_model_unused as employee_model
from app.evaluations.references import assert_employee_unused as evaluation_history
from app.execution.references import assert_model_unused as execution_model
from app.knowledge.references import assert_model_unused as knowledge_model


def check_employee_history(db, agent_id):
    evaluation_history(db, agent_id)
    conversation_history(db, agent_id)


def check_model_references(db, connection_id):
    knowledge_model(db, connection_id)
    execution_model(db, connection_id)
    employee_model(db, connection_id)
