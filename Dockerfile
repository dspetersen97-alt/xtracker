FROM python:3.12-slim

# Create non-root user
RUN groupadd -r xtracker && useradd -r -g xtracker -d /app -s /sbin/nologin xtracker

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /data && chown -R xtracker:xtracker /data /app

# Switch to non-root user
USER xtracker

# Environment variables
ENV DATA_DIR=/data
ENV PORT=5000

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Run with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "run:app"]
