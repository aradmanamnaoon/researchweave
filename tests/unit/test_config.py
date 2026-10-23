from researchweave.app.config import AppConfig, load_config


def test_default_configuration() -> None:
    config = load_config()
    assert config.application_title == "ResearchWeave"
    assert config.diagnostics_enabled is False
    assert AppConfig(application_title="Custom").application_title == "Custom"
