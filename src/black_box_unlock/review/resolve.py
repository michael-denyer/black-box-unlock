"""Resolve the review policy from the ``.bbu.toml`` table, a profile, and the request."""

from dataclasses import dataclass
from pathlib import Path

from ..config import CONFIG_FILE_NAME, load_project_config
from ..core.exceptions import ConfigurationError
from ..path_roles import PathRoleRule
from .models import ChangeReviewRequest, ReviewParameters


@dataclass(frozen=True)
class ResolvedReviewSettings:
    parameters: ReviewParameters
    path_roles: tuple[PathRoleRule, ...]


def resolve_review_settings(
    repo_path: Path,
    request: ChangeReviewRequest,
) -> ResolvedReviewSettings:
    """Layer the ``[coupling]`` table, then the selected profile, then the request.

    Raises:
        ConfigurationError: If ``.bbu.toml`` is invalid or names an unknown profile.
    """
    config = load_project_config(repo_path)
    name = request.profile if request.profile is not None else config.default_profile
    parameters = ReviewParameters(
        coupling=config.coupling,
        profile=name or "default",
        config_path=(
            CONFIG_FILE_NAME if (repo_path.resolve() / CONFIG_FILE_NAME).exists() else None
        ),
    )
    if name is not None:
        profile = config.profiles.get(name)
        if profile is None:
            available = ", ".join(sorted(config.profiles)) or "none"
            raise ConfigurationError(
                f"Unknown review profile {name!r}; available profiles: {available}"
            )
        parameters = parameters.apply(profile)
    return ResolvedReviewSettings(parameters.apply(request), config.path_roles)
