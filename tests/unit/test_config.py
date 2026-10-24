from pathlib import Path

from researchweave.app.config import AppConfig, load_config


def test_default_configuration() -> None:
    config = load_config()
    assert config.application_title == "ResearchWeave"
    assert config.diagnostics_enabled is False
    assert AppConfig(application_title="Custom").application_title == "Custom"


def test_explicit_data_directory_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RESEARCHWEAVE_DATA_DIR", str(tmp_path))
    assert load_config().data_directory == tmp_path
