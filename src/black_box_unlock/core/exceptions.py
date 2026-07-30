"""Custom exceptions for black-box-unlock."""


class BlackBoxUnlockError(Exception):  # [4b] Custom exception classes
    """Base exception for all black-box-unlock errors."""


class NotAGitRepoError(BlackBoxUnlockError):
    """Raised when path is not a git repository."""


class GitToolNotFoundError(BlackBoxUnlockError):
    """Raised when required git tool is not installed."""


class InsufficientHistoryError(BlackBoxUnlockError):
    """Raised when a validation window contains no commits."""


class ChangeSelectionError(BlackBoxUnlockError):
    """Raised when a requested Git change cannot be selected coherently."""


class InvalidRevisionError(ChangeSelectionError):
    """Raised when a requested Git revision cannot be resolved."""
