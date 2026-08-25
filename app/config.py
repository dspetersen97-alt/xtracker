import os

# Project root directory (parent of this file's directory)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    """Application configuration loaded from environment variables."""

    @staticmethod
    def _get_data_dir():
        return os.environ.get("DATA_DIR", os.path.join(_BASE_DIR, "data"))

    @staticmethod
    def _get_port():
        return int(os.environ.get("PORT", 5000))

    @staticmethod
    def _get_secret_key():
        return os.environ.get("SECRET_KEY", "xtracker-dev-key-change-in-prod")


def get_config():
    """Build a config dict from current environment."""
    data_dir = Config._get_data_dir()
    return {
        "DATA_DIR": data_dir,
        "PORT": Config._get_port(),
        "SECRET_KEY": Config._get_secret_key(),
        "DB_PATH": os.path.join(data_dir, "xtracker.db"),
    }