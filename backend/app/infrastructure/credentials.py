"""Fernet encryption with a stable server-only key outside SQLite."""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CredentialUnavailableError(Exception):
    """The configured encryption key or encrypted value cannot be read."""


class CredentialVault:
    def __init__(self, path: Path, configured_key: str | None = None):
        self.path, self.configured_key = path, configured_key

    def _cipher(self, *, allow_create: bool = False) -> Fernet:
        try:
            if self.configured_key is not None:
                return Fernet(self.configured_key.encode("ascii"))
            if not self.path.exists() and allow_create:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".credentials-key-")
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(Fernet.generate_key())
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        os.link(temporary, self.path)
                    except FileExistsError:
                        pass
                finally:
                    os.unlink(temporary)
            return Fernet(self.path.read_bytes().strip())
        except (OSError, ValueError, UnicodeError):
            raise CredentialUnavailableError(
                "Credential encryption material is unavailable"
            ) from None

    def encrypt(self, value: str, *, allow_create: bool) -> str:
        return self._cipher(allow_create=allow_create).encrypt(value.encode()).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._cipher().decrypt(value.encode("ascii")).decode()
        except (InvalidToken, ValueError, UnicodeError):
            raise CredentialUnavailableError(
                "Credential encryption material is unavailable"
            ) from None
