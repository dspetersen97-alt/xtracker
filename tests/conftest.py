import os
import tempfile

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    """Create application for testing with a temp database."""
    data_dir = str(tmp_path)
    test_app = create_app(config_overrides={
        "DATA_DIR": data_dir,
        "DB_PATH": os.path.join(data_dir, "xtracker.db"),
        "TESTING": True,
    })
    yield test_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Push an application context for model tests."""
    with app.app_context():
        yield app
