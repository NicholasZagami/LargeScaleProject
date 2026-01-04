#!/bin/bash
set -e

echo "Starting Cassandra initialization..."

# Install cqlsh and cassandra-driver
echo "Installing dependencies..."
pip3 install --no-cache-dir cqlsh cassandra-driver

# Wait for Cassandra to be ready
echo "Waiting for Cassandra to start..."
MAX_RETRIES=30
RETRY_COUNT=0
until cqlsh cassandra -e "DESCRIBE CLUSTER" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Error: Cassandra did not become ready in time"
        exit 1
    fi
    echo "Cassandra is unavailable - sleeping (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 5
done

echo "Cassandra is up - executing schema script"

# Execute schema creation
cqlsh cassandra -f /init-scripts/01-schema.cql

echo "Schema created successfully!"

# Load data
echo "Loading data from JSON export..."
python3 /init-scripts/02-load-data.py

echo "Cassandra initialization completed!"
