-- ============================================
-- Create DWH Database
-- ============================================

-- Connect to default database to create DWH
-- Note: This part should be run separately or handled by Docker initialization

-- Create the DWH database
CREATE DATABASE dwh;

-- Connect to the DWH database
\c dwh;

-- ============================================
-- Drop tables if they exist (for clean rebuild)
-- ============================================

DROP TABLE IF EXISTS Genre_Game CASCADE;
DROP TABLE IF EXISTS Category_Game CASCADE;
DROP TABLE IF EXISTS Publisher_Game CASCADE;
DROP TABLE IF EXISTS Review CASCADE;
DROP TABLE IF EXISTS UserTable CASCADE;
DROP TABLE IF EXISTS Game CASCADE;
DROP TABLE IF EXISTS Date CASCADE;
DROP TABLE IF EXISTS Genre CASCADE;
DROP TABLE IF EXISTS Category CASCADE;
DROP TABLE IF EXISTS Publisher CASCADE;

-- ============================================
-- Dimension Tables
-- ============================================

CREATE TABLE Date (
    ID_date SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL
);

CREATE TABLE UserTable (
    ID_UserTable SERIAL PRIMARY KEY,
    playtime_at_review INTEGER,
    playtime_forever INTEGER,
    review_number INTEGER,
    language VARCHAR(50),
    owned_games INTEGER,
    last_played TIMESTAMP
);

CREATE TABLE Genre (
    ID_genre SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE Category (
    ID_category SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE Publisher (
    ID_publisher SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE Game (
    ID_game SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    review_score INTEGER,
    required_age INTEGER,
    free_to_play BOOLEAN,
    release_date DATE
);

-- ============================================
-- Fact Table
-- ============================================

CREATE TABLE Review (
    ID_rec VARCHAR(255) PRIMARY KEY,
    ID_UserTable INTEGER NOT NULL,
    ID_game INTEGER NOT NULL,
    ID_date INTEGER NOT NULL,
    votes_up INTEGER DEFAULT 0,
    votes_funny INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    review_word_count INTEGER DEFAULT 0,
    sentiment_round INTEGER DEFAULT 0,
    review_text TEXT,
    FOREIGN KEY (ID_UserTable) REFERENCES UserTable(ID_UserTable),
    FOREIGN KEY (ID_game) REFERENCES Game(ID_game),
    FOREIGN KEY (ID_date) REFERENCES Date(ID_date)
);

-- ============================================
-- Bridge Tables
-- ============================================

-- Game-Genre Bridge Table
CREATE TABLE Genre_Game (
    ID_game INTEGER NOT NULL,
    ID_genre INTEGER NOT NULL,
    PRIMARY KEY (ID_game, ID_genre),
    FOREIGN KEY (ID_game) REFERENCES Game(ID_game) ON DELETE CASCADE,
    FOREIGN KEY (ID_genre) REFERENCES Genre(ID_genre) ON DELETE CASCADE
);

-- Game-Category Bridge Table
CREATE TABLE Category_Game (
    ID_game INTEGER NOT NULL,
    ID_category INTEGER NOT NULL,
    PRIMARY KEY (ID_game, ID_category),
    FOREIGN KEY (ID_game) REFERENCES Game(ID_game) ON DELETE CASCADE,
    FOREIGN KEY (ID_category) REFERENCES Category(ID_category) ON DELETE CASCADE
);

-- Game-Publisher Bridge Table
CREATE TABLE Publisher_Game (
    ID_game INTEGER NOT NULL,
    ID_publisher INTEGER NOT NULL,
    PRIMARY KEY (ID_game, ID_publisher),
    FOREIGN KEY (ID_game) REFERENCES Game(ID_game) ON DELETE CASCADE,
    FOREIGN KEY (ID_publisher) REFERENCES Publisher(ID_publisher) ON DELETE CASCADE
);

-- ============================================
-- Grants and Permissions
-- ============================================

GRANT ALL PRIVILEGES ON DATABASE dwh TO prefect;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO prefect;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO prefect;