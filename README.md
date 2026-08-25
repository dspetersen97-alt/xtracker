# xtracker

A personal exercise tracker web app. Log workouts (hikes, walks, runs, cardio, strength training), view history, and track progress with charts — all from any device on your local network.

Built with Flask, SQLite, Pico CSS, and Chart.js. Designed to run as a Docker container on TrueNAS SCALE or any Docker host.

## Features

- **Multi-activity tracking** — hike, walk, run, cardio, strength training, plus custom types
- **Strength training** — log exercises with sets, reps, and weight per session
- **Workout history** — filter by type or date range, paginated list with detail views
- **Progress charts** — weekly summaries (workouts, distance, duration, type breakdown)
- **Per-exercise drill-down** — distance/pace trends for outdoor activities, weight/volume progression for strength
- **Custom exercise types** — define your own activity types with configurable fields
- **Mobile-first** — responsive design optimized for phone use
- **Local network access** — accessible from any device on your home network
- **Docker-ready** — single container with persistent volume for easy deployment

## Quick Start (Local Development)

### Prerequisites

- Python 3.10+
- pip

### Install and Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server
python run.py
```

The app will be available at `http://localhost:5000` and from other devices at `http://<your-ip>:5000`.

### Run Tests

```bash
python -m pytest tests/ -v
```

## Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t xtracker .

# Run with docker compose
docker compose up -d
```

The app will be available on port 5000. Data is persisted in the `./data` directory (mounted as a volume).

### Docker Compose Configuration

```yaml
services:
  xtracker:
    build: .
    container_name: xtracker
    ports:
      - "5000:5000"
    volumes:
      - ./data:/data
    environment:
      - DATA_DIR=/data
      - PORT=5000
    restart: unless-stopped
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `/data` | Directory for the SQLite database file |
| `PORT` | `5000` | Port the app listens on |
| `SECRET_KEY` | (dev default) | Flask secret key for sessions |

## TrueNAS SCALE Deployment

### Option 1: Custom App (Docker Image)

1. **Build and push the image** (or use a local registry):
   ```bash
   docker build -t xtracker:latest .
   # If using a local registry:
   docker tag xtracker:latest your-registry:5000/xtracker:latest
   docker push your-registry:5000/xtracker:latest
   ```

2. **In TrueNAS SCALE**, go to **Apps > Discover Apps > Custom App**

3. **Configure the app:**
   - **Application Name:** `xtracker`
   - **Image Repository:** `your-registry:5000/xtracker` (or wherever you pushed it)
   - **Image Tag:** `latest`

4. **Port Forwarding:**
   - Container Port: `5000`
   - Node Port: `5000` (or any available port)

5. **Storage:**
   - Add a **Host Path Volume**:
     - Host Path: `/mnt/your-pool/apps/xtracker/data` (create this dataset first)
     - Mount Path: `/data`

6. **Environment Variables:**
   - `DATA_DIR` = `/data`
   - `PORT` = `5000`

7. **Security Context:**
   - The container runs as a non-root user (`xtracker`, UID 999)
   - If you have permission issues, set the dataset permissions to match UID 999

8. **Deploy** — the app will be available at `http://<truenas-ip>:5000`

### Option 2: Docker Compose on TrueNAS

1. SSH into your TrueNAS SCALE system
2. Create a directory for the app:
   ```bash
   mkdir -p /mnt/your-pool/apps/xtracker
   cd /mnt/your-pool/apps/xtracker
   ```
3. Copy the project files (or git clone)
4. Create the data directory:
   ```bash
   mkdir -p data
   chown 999:999 data
   ```
5. Run:
   ```bash
   docker compose up -d
   ```

### Data Backup

The entire application state is in a single SQLite file at `<DATA_DIR>/xtracker.db`. To back up:

```bash
# Simple file copy (while app is running — SQLite WAL mode handles this safely)
cp /mnt/your-pool/apps/xtracker/data/xtracker.db /mnt/your-pool/backups/xtracker-$(date +%Y%m%d).db
```

Or use TrueNAS snapshot/replication on the dataset containing the data directory.

## Project Structure

```
xtracker/
├── app/
│   ├── __init__.py          # App factory with error handlers
│   ├── config.py            # Configuration from environment variables
│   ├── database.py          # SQLite connection and schema initialization
│   ├── models.py            # Data layer (CRUD operations)
│   ├── stats.py             # Aggregation queries for charts
│   ├── routes/
│   │   ├── main.py          # Home page, health check
│   │   ├── activities.py    # Log workout, history, detail, delete
│   │   ├── progress.py      # Summary dashboard, per-type drill-down
│   │   └── settings.py      # Custom exercise type management
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS
├── tests/                   # pytest test suite
├── Dockerfile               # Production container (non-root, gunicorn)
├── docker-compose.yml       # Development/deployment compose file
├── requirements.txt         # Python dependencies
├── Makefile                 # Common tasks
└── run.py                   # Development entry point
```

## Tech Stack

- **Backend:** Python 3.12, Flask
- **Database:** SQLite with WAL mode
- **Frontend:** Server-rendered Jinja2 templates, Pico CSS, Chart.js
- **Production server:** Gunicorn
- **Container:** Docker (Python 3.12-slim base, non-root user)

## License

See [LICENSE](LICENSE) file.
