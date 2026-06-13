"""Test factories for building typed git-history models."""

from black_box_unlock.git.log import Commit, CommitFile


def make_commit(
    paths: list[str] | None = None,
    *,
    timestamp: str = "2026-01-01T00:00:00+00:00",
    author_email: str = "a@x.com",
    message: str = "feat: x",
    files: list[dict] | None = None,
) -> Commit:
    """Build a Commit for tests.

    `paths` is shorthand for files with zero line counts; pass `files` (a list of
    dicts) when a test needs explicit line counts.
    """
    if files is not None:
        file_models = [CommitFile(**f) for f in files]
    else:
        file_models = [CommitFile(path=p) for p in (paths or [])]
    return Commit(
        timestamp=timestamp, author_email=author_email, message=message, files=file_models
    )
