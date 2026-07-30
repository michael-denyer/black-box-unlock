"""Load and resolve project-specific review configuration."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .core.exceptions import ConfigurationError
from .path_roles import PathRoleRule
from .review import ReviewParameters

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

CONFIG_FILE_NAME = ".bbu.toml"


class ReviewProfile(BaseModel):
    """Optional policy values supplied by one named profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    days: int | None = Field(default=None, ge=1)
    min_coupling: float | None = Field(default=None, ge=0.0, le=1.0)
    min_shared_revisions: int | None = Field(default=None, ge=1)
    include_ci: bool | None = None
    max_actions: int | None = Field(default=None, ge=1, le=3)


class ReviewOverrides(ReviewProfile):
    """Caller overrides applied after a named profile."""


class ProjectConfig(BaseModel):
    """Validated contents of one ``.bbu.toml`` file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_profile: str | None = None
    path_roles: tuple[PathRoleRule, ...] = ()
    profiles: dict[str, ReviewProfile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def default_profile_exists(self) -> "ProjectConfig":
        if self.default_profile is not None and self.default_profile not in self.profiles:
            raise ValueError(f"default_profile {self.default_profile!r} is not defined")
        if any(not name.strip() or name != name.strip() for name in self.profiles):
            raise ValueError("profile names must not be empty or padded with whitespace")
        return self


class ResolvedReviewSettings(BaseModel):
    """Effective review policy and path rules after config resolution."""

    model_config = ConfigDict(frozen=True)

    parameters: ReviewParameters
    path_roles: tuple[PathRoleRule, ...] = ()


def load_project_config(repo_path: Path) -> ProjectConfig:
    """Parse and validate ``.bbu.toml`` at the external configuration seam."""
    config_path = repo_path.resolve() / CONFIG_FILE_NAME
    if not config_path.exists():
        return ProjectConfig()
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
        return ProjectConfig.model_validate(raw)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
        raise ConfigurationError(f"Invalid {CONFIG_FILE_NAME}: {error}") from error


def resolve_review_settings(
    repo_path: Path,
    *,
    profile_name: str | None = None,
    overrides: ReviewOverrides | None = None,
) -> ResolvedReviewSettings:
    """Resolve one named profile, then apply explicit caller overrides."""
    config = load_project_config(repo_path)
    selected_name = profile_name if profile_name is not None else config.default_profile
    values = ReviewParameters().model_dump(exclude={"profile", "config_path"})

    if selected_name is not None:
        profile = config.profiles.get(selected_name)
        if profile is None:
            available = ", ".join(sorted(config.profiles)) or "none"
            raise ConfigurationError(
                f"Unknown review profile {selected_name!r}; available profiles: {available}"
            )
        values.update(profile.model_dump(exclude_none=True))

    if overrides is not None:
        values.update(overrides.model_dump(exclude_none=True))

    config_path = CONFIG_FILE_NAME if (repo_path.resolve() / CONFIG_FILE_NAME).exists() else None
    return ResolvedReviewSettings(
        parameters=ReviewParameters(
            **values,
            profile=selected_name or "default",
            config_path=config_path,
        ),
        path_roles=config.path_roles,
    )
