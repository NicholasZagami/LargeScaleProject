-- postgres-init/seed_ui.sql
-- Seed UI-friendly per schema dwh (Postgres)
-- Genera dati fittizi coerenti con il tuo modello: game/review/date/usertable + bridge

BEGIN;

-- 0) Safety: schema deve esistere
CREATE SCHEMA IF NOT EXISTS dwh;

-- 1) Marker table per capire se seed è stato caricato
CREATE TABLE IF NOT EXISTS dwh._etl_meta (
  pipeline_name TEXT PRIMARY KEY,
  loaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
  details JSONB
);

-- 2) Pulizia (per rerun del seed senza duplicati)
-- Ordine importante per FK
TRUNCATE TABLE
  dwh.publisher_game,
  dwh.category_game,
  dwh.genre_game,
  dwh.review,
  dwh.game,
  dwh.usertable,
  dwh.date,
  dwh.publisher,
  dwh.category,
  dwh.genre
RESTART IDENTITY CASCADE;

-- 3) Dimension: Date (ultimi 60 giorni)
INSERT INTO dwh.date (year, month, day)
SELECT
  EXTRACT(YEAR FROM d)::int,
  EXTRACT(MONTH FROM d)::int,
  EXTRACT(DAY FROM d)::int
FROM generate_series(CURRENT_DATE - INTERVAL '59 days', CURRENT_DATE, INTERVAL '1 day') d;

-- 4) Dimension: Genre
INSERT INTO dwh.genre (name)
SELECT unnest(ARRAY[
  'Action','RPG','Strategy','Indie','Simulation','Adventure',
  'Sports','Racing','Puzzle','Horror','Casual','Sandbox'
])
ON CONFLICT (name) DO NOTHING;

-- 5) Dimension: Category
INSERT INTO dwh.category (name)
SELECT unnest(ARRAY[
  'Singleplayer','Multiplayer','Co-op','Open World','VR',
  'Controller','Story Rich','Competitive','Turn-Based','Online PvP'
])
ON CONFLICT (name) DO NOTHING;

-- 6) Dimension: Publisher (25)
INSERT INTO dwh.publisher (name)
SELECT 'Publisher ' || gs
FROM generate_series(1, 25) gs
ON CONFLICT (name) DO NOTHING;

-- 7) Dimension: Game (200)
-- review_score: 0-100 (lo converti a stelle lato UI dividendo per 20, come già fai)
INSERT INTO dwh.game (name, review_score, required_age, free_to_play, release_date)
SELECT
  'Game ' || gs,
  GREATEST(5, LEAST(95, (random()*100)::int)),
  CASE WHEN random() < 0.9 THEN 0 ELSE 18 END,
  (random() < 0.18),
  CURRENT_DATE - ((random()*3650)::int) * INTERVAL '1 day'
FROM generate_series(1, 200) gs;

-- 8) Dimension: UserTable (800)
INSERT INTO dwh.usertable (playtime_at_review, playtime_forever, review_number, language, owned_games, last_played)
SELECT
  (random()*600)::int,
  (random()*2500)::int,
  (random()*300)::int,
  (ARRAY['english','italian','spanish','german','french','portuguese','russian','japanese'])[1 + (random()*7)::int],
  (random()*500)::int,
  NOW() - ((random()*365)::int) * INTERVAL '1 day'
FROM generate_series(1, 800) gs;

-- 9) Bridge: Publisher_Game (1 publisher per game)
INSERT INTO dwh.publisher_game (id_game, id_publisher)
SELECT g.id_game, 1 + (random()*24)::int
FROM dwh.game g;

-- 10) Bridge: Category_Game (1 category per game)
INSERT INTO dwh.category_game (id_game, id_category)
SELECT g.id_game, 1 + (random()*9)::int
FROM dwh.game g;

-- 11) Bridge: Genre_Game (1-2 genres per game)
INSERT INTO dwh.genre_game (id_game, id_genre)
SELECT g.id_game, 1 + (random()*11)::int
FROM dwh.game g;

INSERT INTO dwh.genre_game (id_game, id_genre)
SELECT g.id_game, 1 + (random()*11)::int
FROM dwh.game g
WHERE random() < 0.45
ON CONFLICT DO NOTHING;

-- 12) Fact: Review (20.000)
-- sentiment_round: 0-10
-- id_date: scegli a caso tra le date caricate
INSERT INTO dwh.review (
  id_rec, id_usertable, id_game, id_date,
  votes_up, votes_funny, comment_count,
  review_word_count, sentiment_round, review_text
)
SELECT
  'seed_' || gs,
  1 + (random()*799)::int,
  1 + (random()*199)::int,
  (SELECT id_date FROM dwh.date ORDER BY random() LIMIT 1),
  (random()*250)::int,
  (random()*35)::int,
  (random()*40)::int,
  10 + (random()*400)::int,
  (random()*11)::int,
  'This is a seeded review #' || gs || ' — UI demo content.'
FROM generate_series(1, 20000) gs;

-- 13) Marker: segna caricamento seed
INSERT INTO dwh._etl_meta (pipeline_name, details)
VALUES ('seed_ui_v1', jsonb_build_object(
  'games', (SELECT COUNT(*) FROM dwh.game),
  'reviews', (SELECT COUNT(*) FROM dwh.review),
  'users', (SELECT COUNT(*) FROM dwh.usertable),
  'days', (SELECT COUNT(*) FROM dwh.date)
))
ON CONFLICT (pipeline_name) DO UPDATE
SET loaded_at = NOW(),
    details = EXCLUDED.details;

COMMIT;