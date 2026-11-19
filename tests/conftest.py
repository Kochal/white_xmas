import pytest

from whitexmas.config import Config


@pytest.fixture
def cfg() -> Config:
    return Config.load()
