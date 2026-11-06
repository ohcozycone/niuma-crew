"""Attach private evidence to existing execution actions; preserve all work."""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = depends_on = None


def upgrade():
    # Frozen 0023 schema keeps offline SQL reproducible; Alembic disables FK checks
    # for the table copy and verifies every reference before committing.
    for statement in DDL:
        op.execute(statement)


def downgrade():
    raise RuntimeError("执行证据不支持有损降级，请恢复升级前备份。")


DDL = (
    "CREATE TABLE _stored_files_evidence (\n\towner_user_id TEXT NOT NULL, \n\torigin_run_id BIGINT, \n\tname TEXT NOT NULL, \n\tmedia_type TEXT NOT NULL, \n\tsize INTEGER NOT NULL, \n\tcontent_hash TEXT NOT NULL, \n\tstorage_key TEXT NOT NULL, \n\tpurpose TEXT NOT NULL, \n\tid TEXT NOT NULL, \n\tcreated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tupdated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now') || '000Z') NOT NULL, \n\tCONSTRAINT pk_stored_files PRIMARY KEY (id), \n\tCONSTRAINT ck_stored_files_size_nonnegative CHECK (size >= 0), \n\tCONSTRAINT ck_stored_files_purpose_valid CHECK (purpose IN ('input','source','output','evidence')), \n\tCONSTRAINT fk_stored_files_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id), \n\tCONSTRAINT fk_stored_files_origin_run_id_runs FOREIGN KEY(origin_run_id) REFERENCES runs (id), \n\tCONSTRAINT uq_stored_files_storage_key UNIQUE (storage_key)\n)",
    "INSERT INTO _stored_files_evidence (owner_user_id,origin_run_id,name,media_type,size,content_hash,storage_key,purpose,id,created_at,updated_at) SELECT owner_user_id,origin_run_id,name,media_type,size,content_hash,storage_key,purpose,id,created_at,updated_at FROM stored_files",
    "DROP TABLE stored_files",
    "ALTER TABLE _stored_files_evidence RENAME TO stored_files",
    "CREATE INDEX ix_stored_files_origin_run_id ON stored_files (origin_run_id)",
    "CREATE INDEX ix_stored_files_owner_user_id ON stored_files (owner_user_id)",
    "ALTER TABLE run_actions ADD COLUMN request_file_id TEXT REFERENCES stored_files(id)",
    "ALTER TABLE run_actions ADD COLUMN response_file_id TEXT REFERENCES stored_files(id)",
)
