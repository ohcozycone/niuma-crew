from types import SimpleNamespace

from sqlalchemy import select

from app.resources.model_connections.models import ModelConnection


def connection_fact(db, id):
    row = db.get(ModelConnection, id)
    return (
        SimpleNamespace(
            id=row.id,
            name=row.name,
            enabled=row.enabled,
            capability=row.capability,
            config_revision=row.config_revision,
            credential_revision=row.credential_revision,
            model_id=row.model_id,
            preset_id=row.preset_id,
        )
        if row
        else None
    )


def embedding_connections(db):
    return [
        connection_fact(db, id)
        for id in db.scalars(
            select(ModelConnection.id)
            .where(ModelConnection.enabled.is_(True), ModelConnection.capability == "embedding")
            .order_by(ModelConnection.name, ModelConnection.id)
        )
    ]


def chat_connection_ids():
    return select(ModelConnection.id).where(
        ModelConnection.enabled.is_(True), ModelConnection.capability == "chat"
    )
