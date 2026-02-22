"""Tests for src/config.py (T006)."""
import os
import pytest
from pathlib import Path
from unittest.mock import patch


def test_dry_run_defaults_true():
    """Without DRY_RUN env var and no .env override, DRY_RUN defaults to True."""
    from unittest.mock import patch as _patch
    # Patch the source module so that importlib.reload re-imports the Mock.
    with _patch("dotenv.load_dotenv"):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DRY_RUN", None)
            import importlib, src.config as cfg
            importlib.reload(cfg)
            assert cfg.DRY_RUN is True


def test_dry_run_false_override(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DRY_RUN=false\n")
    with patch.dict(os.environ, {"DRY_RUN": "false"}):
        import importlib, src.config as cfg
        importlib.reload(cfg)
        assert cfg.DRY_RUN is False


def test_vault_root_resolves_to_absolute():
    import src.config as cfg
    assert cfg.VAULT_ROOT.is_absolute()


def test_credential_leak_check_passes_on_clean():
    import src.config as cfg
    assert cfg.credential_leak_check("This is clean content with no secrets.") is True


def test_credential_leak_check_raises_on_leak(tmp_path, monkeypatch):
    """Credential leak check catches .env values in content."""
    import src.config as cfg
    # Inject a fake secret into the env values set.
    monkeypatch.setattr(cfg, "_ENV_VALUES", {"super_secret_value_xyz"})
    with pytest.raises(ValueError, match="Credential leak detected"):
        cfg.credential_leak_check("This content contains super_secret_value_xyz oops")
