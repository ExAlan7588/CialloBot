from __future__ import annotations


class UserCommandError(Exception):
    def __init__(self, message: str, *, ephemeral: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.ephemeral = ephemeral
