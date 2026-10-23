"""Validated, portable application configuration."""

from pathlib import Path

from platformdirs import user_data_dir
from pydantic import BaseModel, ConfigDict, Field


class AppConfig(BaseModel):
    """Configuration with safe offline defaults."""

    model_config = ConfigDict(frozen=True)

    application_title: str = Field(default="ResearchWeave", min_length=1, max_length=120)
    data_directory: Path = Field(default_factory=lambda: Path(user_data_dir("ResearchWeave")))
    diagnostics_enabled: bool = False


def load_config() -> AppConfig:
    """Load offline defaults without reading private configuration files."""
    return AppConfig()
