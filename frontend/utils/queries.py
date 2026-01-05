# frontend/utils/queries.py

Q_KPI_OVERVIEW = """
SELECT
  (SELECT COUNT(*) FROM dwh.game) AS total_games,
  (SELECT COUNT(*) FROM dwh.review) AS total_reviews,
  COALESCE((SELECT AVG(review_score) FROM dwh.game), 0) AS avg_score_0_100
"""

Q_TOP_GAMES = """
SELECT
  g.id_game,
  g.name,
  COUNT(*) AS reviews,
  AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment,
  AVG(r.votes_up)::numeric(10,2) AS avg_votes_up
FROM dwh.review r
JOIN dwh.game g ON g.id_game = r.id_game
GROUP BY g.id_game, g.name
ORDER BY reviews DESC
LIMIT :limit
"""

Q_REVIEWS_BY_DAY = """
SELECT
  make_date(d.year, d.month, d.day) AS day,
  COUNT(*) AS reviews,
  AVG(r.sentiment_round)::numeric(10,2) AS avg_sentiment
FROM dwh.review r
JOIN dwh.date d ON d.id_date = r.id_date
GROUP BY 1
ORDER BY 1
"""

Q_SENTIMENT_DIST = """
SELECT sentiment_round, COUNT(*) AS n
FROM dwh.review
GROUP BY sentiment_round
ORDER BY sentiment_round
"""

Q_LANG_DIST = """
SELECT language, COUNT(*) AS n
FROM dwh.usertable
GROUP BY language
ORDER BY n DESC
LIMIT 20
"""
