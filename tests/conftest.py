"""Offline suite cannot accidentally bill a real model provider."""
import pytest
from pydantic_ai import models


@pytest.fixture(autouse=True)
def no_live_model(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
