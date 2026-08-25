#!/bin/sh
# Ensure the data directory is writable by the xtracker user.
# Container starts as root so we can fix permissions, then drops to xtracker.

if [ "$(id -u)" = "0" ]; then
    # Fix ownership of the data directory (handles host-mounted volumes)
    chown -R xtracker:xtracker /data
    # Drop to non-root user and exec the CMD
    exec gosu xtracker "$@"
fi

# Already running as non-root — just verify we can write
if [ ! -w /data ]; then
    echo "ERROR: /data is not writable by user $(id -u)."
    echo "Fix on host with: sudo chown $(id -u):$(id -g) ./data"
    exit 1
fi

exec "$@"
