"""Custom exceptions for black-box-unlock."""


class BlackBoxUnlockError(Exception):
    """Base exception for all black-box-unlock errors."""


class NotAGitRepoError(BlackBoxUnlockError):
    """Raised when path is not a git repository."""


class GitToolNotFoundError(BlackBoxUnlockError):
    """Raised when required git tool is not installed."""
