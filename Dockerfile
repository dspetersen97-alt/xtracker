FROM python:3.12-slim

# Install system dependencies needed by cryptography and curl_cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with fixed UID
RUN groupadd -r -g 1000 xtracker && useradd -r -u 1000 -g xtracker -d /app -s /sbin/nologin xtracker

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Create data directory
RUN mkdir -p /data && chown -R xtracker:xtracker /data /app

# Environment variables
ENV DATA_DIR=/data
ENV PORT=5000
ENV SECRET_KEY=change-me-in-production

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Start as root so entrypoint can fix permissions, then drop to xtracker
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "run:app"]
