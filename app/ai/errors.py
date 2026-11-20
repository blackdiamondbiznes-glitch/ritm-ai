"""Errors the generator and the job handler understand."""


class AIConfigError(Exception):
    """Missing key or a rejected credential. Do not retry."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AITransient(Exception):
    """Timeout, rate limit or a provider outage. The job may retry."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AIOutputError(Exception):
    """The model reply was not the expected JSON object."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
