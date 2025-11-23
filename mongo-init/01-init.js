// Switch to the database you want to use
db = db.getSiblingDB('steam_db');

// Create the games collection
db.createCollection('games');
db.createCollection('review');

print("Games collection created successfully!");