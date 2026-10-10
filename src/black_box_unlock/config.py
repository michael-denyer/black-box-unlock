"""Load and resolve project-specific review configuration."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .core.exceptions import ConfigurationError
from .core.models import CouplingPolicy
from .path_roles import PathRoleRule

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


class ProjectConfig(BaseModel):
    """Validated contents of one ``.bbu.toml`` file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_profile: str | None = None
    coupling: CouplingPolicy = Field(default_factory=CouplingPolicy)
    path_roles: tuple[PathRoleRule, ...] = ()
    profiles: dict[str, ReviewProfile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def default_profile_exists(self) -> "ProjectConfig":
        if self.default_profile is not None and self.default_profile not in self.profiles:
            raise ValueError(f"default_profile {self.default_profile!r} is not defined")
        if any(not name.strip() or name != name.strip() for name in self.profiles):
            raise ValueError("profile names must not be empty or padded with whitespace")
        return self


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


def resolve_coupling_policy(
    repo_path: Path,
    *,
    min_ratio: float | None = None,
    min_shared_revisions: int | None = None,
    max_changeset_size: int | None = None,
) -> CouplingPolicy:
    """Apply explicit overrides over the ``[coupling]`` table of ``.bbu.toml``.

    Raises:
        ConfigurationError: If ``.bbu.toml`` or an override is invalid.
    """
    overrides = {
        "min_ratio": min_ratio,
        "min_shared_revisions": min_shared_revisions,
        "max_changeset_size": max_changeset_size,
    }
    base = load_project_config(repo_path).coupling
    try:
        return CouplingPolicy.model_validate(
            base.model_dump()
            | {key: value for key, value in overrides.items() if value is not None}
        )
    except ValidationError as error:
        raise ConfigurationError(f"Invalid coupling policy: {error}") from error
