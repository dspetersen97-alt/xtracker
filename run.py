from app import create_app
from app.config import get_config

app = create_app()

if __name__ == "__main__":
    config = get_config()
    app.run(host="0.0.0.0", port=config["PORT"], debug=True)
