"""Shared error types."""


class ReelStudioError(Exception):
    """Base class for user-facing errors (reported as HTTP 4xx)."""


class ValidationError(ReelStudioError):
    """reel.yaml failed validation. `problems` lists each reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


class NotFoundError(ReelStudioError):
    """A requested scene/artifact does not exist."""
