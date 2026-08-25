.PHONY: install dev test docker-build docker-run clean

# Install Python dependencies
install:
	pip install -r requirements.txt

# Run development server (accessible on LAN)
dev:
	python run.py

# Run tests
test:
	python -m pytest tests/ -v

# Build Docker image
docker-build:
	docker build -t xtracker .

# Run Docker container
docker-run:
	docker compose up -d

# Stop Docker container
docker-stop:
	docker compose down

# Clean up
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
