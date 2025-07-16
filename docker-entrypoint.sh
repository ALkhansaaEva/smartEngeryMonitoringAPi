#!/bin/bash
set -e

# Optional: Remove any existing PID file (if uvicorn or gunicorn uses one)
# rm -f /app/uvicorn.pid

# Wait until MySQL is ready
echo "⏳ Waiting for MySQL at mysql:3306..."
while ! nc -z mysql 3306; do
  sleep 1
done
echo "✅ MySQL is up - starting app..."

# Execute the main container process (specified in CMD)
exec "$@"
