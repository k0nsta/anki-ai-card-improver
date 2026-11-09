from typing import Literal

ErrorKind = Literal[
    "no_config",
    "auth",
    "rate_limit",
    "server",
    "timeout",
    "network",
    "bad_response",
]


class AiError(Exception):
    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
