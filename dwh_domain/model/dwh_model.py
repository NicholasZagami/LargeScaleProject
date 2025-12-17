from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DECIMAL, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class DateTable(Base):
    __tablename__ = 'date'

    ID_date = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer)
    month = Column(Integer)
    day = Column(Integer)

    # Relationships
    reviews = relationship('Review', back_populates='date')


class User(Base):
    __tablename__ = 'user'

    ID_user = Column(Integer, primary_key=True, autoincrement=True)
    playtime_at_review = Column(Float)
    playtime_forever = Column(Float)
    review_number = Column(Integer)
    language = Column(String(50))
    last_played = Column(Date)

    # Relationships
    reviews = relationship('Review', back_populates='user')


class Game(Base):
    __tablename__ = 'game'

    ID_game = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))
    price = Column(DECIMAL(10, 2))
    review_score = Column(Integer)
    required_age = Column(Integer)
    free_to_play = Column(Boolean)
    release_date = Column(Date)

    # Relationships
    reviews = relationship('Review', back_populates='game')
    genres = relationship('Genre', secondary='genre_game', back_populates='games')
    categories = relationship('Category', secondary='category_game', back_populates='games')
    publishers = relationship('Publisher', secondary='publisher_game', back_populates='games')


class Review(Base):
    __tablename__ = 'review'

    ID_user = Column(Integer, ForeignKey('user.ID_user'), primary_key=True)
    ID_game = Column(Integer, ForeignKey('game.ID_game'), primary_key=True)
    ID_date = Column(Integer, ForeignKey('date.ID_date'), primary_key=True)
    votes_up = Column(Integer)
    votes_funny = Column(Integer)
    comment_count = Column(Integer)
    review_word_count = Column(Integer)
    sentiment = Column(Integer)
    review_text = Column(Text)

    # Relationships
    user = relationship('User', back_populates='reviews')
    game = relationship('Game', back_populates='reviews')
    date = relationship('Date', back_populates='reviews')


class Genre(Base):
    __tablename__ = 'genre'

    ID_genre = Column(Integer, primary_key=True, autoincrement=True)
    genre = Column(String(100))

    # Relationships
    games = relationship('Game', secondary='genre_game', back_populates='genres')


class Category(Base):
    __tablename__ = 'category'

    ID_category = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(100))

    # Relationships
    games = relationship('Game', secondary='category_game', back_populates='categories')


class Publisher(Base):
    __tablename__ = 'publisher'

    ID_publisher = Column(Integer, primary_key=True, autoincrement=True)
    publisher = Column(String(255))

    # Relationships
    games = relationship('Game', secondary='publisher_game', back_populates='publishers')


# Bridge Tables (Association Tables)

class GenreGame(Base):
    __tablename__ = 'genre_game'

    ID_game = Column(Integer, ForeignKey('game.ID_game'), primary_key=True)
    ID_genre = Column(Integer, ForeignKey('genre.ID_genre'), primary_key=True)


class CategoryGame(Base):
    __tablename__ = 'category_game'

    ID_game = Column(Integer, ForeignKey('game.ID_game'), primary_key=True)
    ID_category = Column(Integer, ForeignKey('category.ID_category'), primary_key=True)


class PublisherGame(Base):
    __tablename__ = 'publisher_game'

    ID_game = Column(Integer, ForeignKey('game.ID_game'), primary_key=True)
    ID_publisher = Column(Integer, ForeignKey('publisher.ID_publisher'), primary_key=True)