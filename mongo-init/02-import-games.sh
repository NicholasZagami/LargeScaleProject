#!/bin/bash

# Wait a bit for MongoDB to be fully ready
sleep 5

echo "Importing games data into MongoDB..."

# Import JSON data
mongoimport \
  --host localhost \
  --username admin \
  --password password \
  --authenticationDatabase admin \
  --db steam_db \
  --collection games \
  --file /imports/steam_db.games.json \
  --jsonArray

echo "MongoDB import completed!"