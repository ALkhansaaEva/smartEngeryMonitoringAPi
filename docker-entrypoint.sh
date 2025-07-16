#!/bin/bash
set -e

# Optional: Remove any existing PID file (if uvicorn or gunicorn uses one)
# rm -f /app/uvicorn.pid

# Execute the main container process (specified in CMD)
exec "$@"
