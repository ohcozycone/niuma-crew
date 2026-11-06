"""Opaque tokens are issued after commit; password work runs outside write transactions."""

import hashlib
import re
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta

from pwdlib import PasswordHash
from sqlalchemy import delete, select, update

from app.auth.actor import Actor
from app.auth.config import AuthConfig
from app.auth.models import AuthSession, ExternalIdentity, User
from app.errors import AuthenticationError, PermissionDeniedError
from app.infrastructure.database.session import Database
from app.values import utc_now

PASSWORDS = PasswordHash.recommended()
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,64}", value):
        raise ValueError("用户名需为 3～64 位英文字母、数字、下划线、短横线或点。")
    return value


def hash_password(password: str) -> str:
    if not 8 <= len(password) <= 20:
        raise ValueError("密码长度必须为 8～20 个字符。")
    return PASSWORDS.hash(password)


def authentication_required() -> AuthenticationError:
    return AuthenticationError("authentication_required", "登录已失效，请重新登录或选择游客浏览。")


class AuthService:
    def __init__(
        self, database: Database, config: AuthConfig, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.database, self.config, self.clock = database, config, clock

    def initialize_admin(self, username: str, password: str) -> None:
        username, hashed = normalize_username(username), hash_password(password)
        with self.database.transaction() as db:
            # Acquire SQLite's writer reservation before testing for the first account.
            db.execute(
                update(User)
                .where(User.id == "00000000-0000-0000-0000-000000000000")
                .values(role="admin")
            )
            if db.scalar(select(User.id).where(User.role == "admin").limit(1)):
                raise ValueError("管理员已经初始化；请使用维护命令，不会覆盖现有账号。")
            db.add(User(username=username, password_hash=hashed, role="admin"))

    def maintain_user(self, username: str, operation: str, password: str | None = None) -> None:
        username = normalize_username(username)
        if operation not in {"reset-password", "disable-user", "enable-user", "revoke-sessions"}:
            raise ValueError("未知账号维护操作。")
        values = {}
        if operation == "reset-password":
            values["password_hash"] = hash_password(password or "")
        elif operation in {"disable-user", "enable-user"}:
            values["is_active"] = operation == "enable-user"
        with self.database.transaction() as db:
            # Writing first serializes maintenance against concurrent session issuance.
            user_id = db.scalar(
                update(User)
                .where(User.username == username, User.role == "admin")
                .values(updated_at=self.clock(), **values)
                .returning(User.id)
            )
            if user_id is None:
                raise ValueError("用户不存在。")
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user_id)
                .values(revoked_at=self.clock())
            )

    def login(self, username: str, password: str, old_token: str | None) -> tuple[Actor, str]:
        username = username.strip().lower()
        with self.database.transaction() as db:
            user = db.scalar(select(User).where(User.username == username, User.role == "admin"))
        valid = PASSWORDS.verify(password, user.password_hash if user else DUMMY_HASH)
        if not valid or user is None or not user.is_active:
            raise AuthenticationError("invalid_credentials", "用户名或密码错误。")
        now = self.clock()
        token = secrets.token_urlsafe(32)
        with self.database.transaction() as db:
            # Conditional write rechecks the verified password and active state under the write lock.
            confirmed = db.scalar(
                update(User)
                .where(
                    User.id == user.id,
                    User.password_hash == user.password_hash,
                    User.is_active.is_(True),
                )
                .values(updated_at=User.updated_at)
                .returning(User.id)
            )
            if confirmed is None:
                raise AuthenticationError("invalid_credentials", "用户名或密码错误。")
            if old_token:
                db.execute(
                    update(AuthSession)
                    .where(AuthSession.token_hash == token_digest(old_token))
                    .values(revoked_at=now)
                )
            session = AuthSession(
                kind="user",
                user_id=user.id,
                token_hash=token_digest(token),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(seconds=self.config.max_age_seconds),
            )
            db.add(session)
            db.flush()
            actor = self._actor(session, user)
        return actor, token

    def github_login(
        self, github_id: str, username: str, old_token: str | None
    ) -> tuple[Actor, str]:
        """Only called with the identity verified by the server's GitHub client."""
        now, token = self.clock(), secrets.token_urlsafe(32)
        with self.database.transaction() as db:
            # Reserve SQLite's writer before reading: two callbacks cannot create two users.
            db.execute(
                update(User)
                .where(User.id == "00000000-0000-0000-0000-000000000000")
                .values(updated_at=now)
            )
            external = db.scalar(
                select(ExternalIdentity).where(
                    ExternalIdentity.provider == "github",
                    ExternalIdentity.provider_user_id == github_id,
                )
            )
            if external:
                user = db.get(User, external.user_id)
                if not user or not user.is_active or user.role != "member":
                    raise PermissionDeniedError("github_account_disabled", "当前账号无法登录。")
                user.username = username
            else:
                user = User(username=username, password_hash=None, role="member")
                db.add(user)
                db.flush()
                db.add(
                    ExternalIdentity(user_id=user.id, provider="github", provider_user_id=github_id)
                )
            if old_token:
                db.execute(
                    update(AuthSession)
                    .where(AuthSession.token_hash == token_digest(old_token))
                    .values(revoked_at=now)
                )
            session = AuthSession(
                kind="user",
                user_id=user.id,
                token_hash=token_digest(token),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(seconds=self.config.max_age_seconds),
            )
            db.add(session)
            db.flush()
            actor = self._actor(session, user)
        return actor, token

    def guest(self, old_token: str | None) -> tuple[Actor, str | None]:
        try:
            return self.resolve(old_token), None
        except AuthenticationError:
            # 仅无效身份允许回退为游客；存储或服务故障应继续交给调用方处理。
            pass
        now, token = self.clock(), secrets.token_urlsafe(32)
        with self.database.transaction() as db:
            session = AuthSession(
                kind="guest",
                token_hash=token_digest(token),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(seconds=self.config.guest_max_age_seconds),
            )
            db.add(session)
            db.flush()
            actor = self._actor(session, None)
        return actor, token

    @staticmethod
    def _actor(session: AuthSession, user: User | None) -> Actor:
        return Actor(
            session.kind,
            session.id,
            session.user_id,
            user.username if user else None,
            user.role if user else "guest",
            session.expires_at,
        )

    def resolve(self, token: str | None) -> Actor:
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise authentication_required()
        now = self.clock()
        with self.database.transaction() as db:
            session = db.scalar(
                select(AuthSession).where(AuthSession.token_hash == token_digest(token))
            )
            actor = self._validated_actor(db, session, now)
            previous_seen = session.last_seen_at
        # Separate read and conditional write avoids upgrading a WAL read snapshot.
        touch_interval = min(300, max(1, self.config.idle_timeout_seconds // 10))
        if session.kind == "user" and (now - previous_seen).total_seconds() >= touch_interval:
            with self.database.transaction() as db:
                db.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.id == actor.session_id,
                        AuthSession.revoked_at.is_(None),
                        AuthSession.last_seen_at == previous_seen,
                        AuthSession.expires_at > now,
                    )
                    .values(last_seen_at=now)
                )
        return actor

    def validate_session(self, db, session_id: str | None) -> Actor:
        """Read-only validation in the caller's snapshot; never touches last_seen."""
        now = self.clock()
        session = db.get(AuthSession, session_id) if session_id else None
        return self._validated_actor(db, session, now)

    def _validated_actor(self, db, session, now) -> Actor:
        if not session or session.revoked_at or session.expires_at <= now:
            raise authentication_required()
        user = db.get(User, session.user_id) if session.user_id else None
        if session.kind == "user" and (
            not user
            or not user.is_active
            or (now - session.last_seen_at).total_seconds() >= self.config.idle_timeout_seconds
        ):
            raise authentication_required()
        return self._actor(session, user)

    def resolve_session(self, session_id: str | None) -> Actor:
        with self.database.transaction() as db:
            return self.validate_session(db, session_id)

    def logout(self, token: str | None) -> None:
        if token:
            with self.database.transaction() as db:
                db.execute(
                    update(AuthSession)
                    .where(AuthSession.token_hash == token_digest(token))
                    .values(revoked_at=self.clock())
                )

    def cleanup(self) -> int:
        now = self.clock()
        with self.database.transaction() as db:
            result = db.execute(
                delete(AuthSession).where(
                    (AuthSession.expires_at <= now)
                    | AuthSession.revoked_at.is_not(None)
                    | (
                        (AuthSession.kind == "user")
                        & (
                            AuthSession.last_seen_at
                            <= now - timedelta(seconds=self.config.idle_timeout_seconds)
                        )
                    )
                )
            )
            return result.rowcount
