"""Seed frozen text-only schemas without calling newer application projections."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.auth.actor import Actor
from app.auth.models import User
from app.auth.service import AuthService
from app.files.service import FileService
from app.infrastructure.database.session import Database
from app.knowledge.chunking import split_document
from app.knowledge.contracts import ChunkingRules
from app.knowledge.lexical import lexical_terms, lexical_version
from app.knowledge.loading import text_document
from app.values import new_uuid, utc_now


def seed_text_library(settings, monkeypatch, revision):
    monkeypatch.setenv("DATABASE_URL", settings.database.url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, revision)
    database = Database(settings.database)
    AuthService(database, settings.auth).initialize_admin("admin", "test-password-auth")
    with database.transaction() as db:
        owner = db.scalar(select(User.id))
    files = FileService(database, settings.files)
    body = "# 交通与住宿\n高铁二等座，住宿每晚四百元。".encode()
    file = files.save(owner, "规则.md", body)
    kb, document_id = new_uuid(), new_uuid()
    document = text_document(body, document_id, "规则.md")
    chunks = split_document(document, ChunkingRules(chunk_tokens=800, overlap_tokens=120), len)
    with database.transaction() as db:
        db.execute(
            text(
                "INSERT INTO knowledge_bases(id,owner_user_id,client_request_id,name,description) VALUES (:id,:owner,:request,'历史资料','')"
            ),
            {"id": kb, "owner": owner, "request": new_uuid()},
        )
        db.execute(
            text(
                "INSERT INTO knowledge_documents(id,knowledge_base_id,client_request_id,file_id,title,content_hash,snapshot,lexical_version) VALUES (:id,:kb,:request,:file,'规则',:hash,:snapshot,:lexical)"
            ),
            {
                "id": document_id,
                "kb": kb,
                "request": new_uuid(),
                "file": file["id"],
                "hash": hashlib.sha256(body).hexdigest(),
                "snapshot": document.model_dump_json(),
                "lexical": lexical_version(),
            },
        )
        for position, chunk in enumerate(chunks):
            db.execute(
                text(
                    "INSERT INTO knowledge_chunks(id,document_id,position,snapshot) VALUES (:id,:doc,:position,:snapshot)"
                ),
                {
                    "id": chunk.id,
                    "doc": document_id,
                    "position": position,
                    "snapshot": json.dumps(chunk.model_dump(mode="json")),
                },
            )
            db.execute(
                text(
                    "INSERT INTO knowledge_fts(chunk_id,knowledge_base_id,tokens) VALUES (:id,:kb,:tokens)"
                ),
                {"id": chunk.id, "kb": kb, "tokens": " ".join(lexical_terms(chunk.index_text))},
            )
    actor = Actor("user", "", owner, "admin", "admin", utc_now() + timedelta(hours=1))
    return database, files, config, actor, kb, document_id, chunks
