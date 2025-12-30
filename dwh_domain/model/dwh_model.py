from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DECIMAL, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class DateTable(Base):
    __tablename__ = 'date'

    ID_date = Column('id_date', String(255), primary_key=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    day = Column(Integer, nullable=False)

    # Relationships
    reviews = relationship('Review', back_populates='date')


class User(Base):
    __tablename__ = 'usertable'

    ID_user = Column('id_usertable', String(255), primary_key=True)
    playtime_at_review = Column(Integer)
    playtime_forever = Column(Integer)
    review_number = Column(Integer)
    language = Column(String(50))
    owned_games = Column(Integer)
    last_played = Column(Date)

    # Relationships
    reviews = relationship('Review', back_populates='user')


class Game(Base):
    __tablename__ = 'game'

    ID_game = Column('id_game', String(255), primary_key=True)
    name = Column(String(255), nullable=False)
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

    ID_rec = Column('id_rec', String(255), primary_key=True)
    ID_user = Column('id_usertable', String(255), ForeignKey('usertable.id_usertable'), nullable=False)
    ID_game = Column('id_game', String(255), ForeignKey('game.id_game'), nullable=False)
    ID_date = Column('id_date', String(255), ForeignKey('date.id_date'), nullable=False)
    votes_up = Column(Integer, default=0)
    votes_funny = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    review_word_count = Column(Integer, default=0)
    sentiment = Column('sentiment_round', Integer, default=0)
    review_text = Column(Text)

    # Relationships
    user = relationship('User', back_populates='reviews')
    game = relationship('Game', back_populates='reviews')
    date = relationship('DateTable', back_populates='reviews')


class Genre(Base):
    __tablename__ = 'genre'

    ID_genre = Column('id_genre', Integer, primary_key=True, autoincrement=True)
    genre = Column('name', String(100), nullable=False, unique=True)

    # Relationships
    games = relationship('Game', secondary='genre_game', back_populates='genres')


class Category(Base):
    __tablename__ = 'category'

    ID_category = Column('id_category', Integer, primary_key=True, autoincrement=True)
    category = Column('name', String(100), nullable=False, unique=True)

    # Relationships
    games = relationship('Game', secondary='category_game', back_populates='categories')


class Publisher(Base):
    __tablename__ = 'publisher'

    ID_publisher = Column('id_publisher', Integer, primary_key=True, autoincrement=True)
    publisher = Column('name', String(255), nullable=False, unique=True)

    # Relationships
    games = relationship('Game', secondary='publisher_game', back_populates='publishers')


# Bridge Tables (Association Tables)

class GenreGame(Base):
    __tablename__ = 'genre_game'

    ID_game = Column('id_game', String(255), ForeignKey('game.id_game'), primary_key=True)
    ID_genre = Column('id_genre', Integer, ForeignKey('genre.id_genre'), primary_key=True)


class CategoryGame(Base):
    __tablename__ = 'category_game'

    ID_game = Column('id_game', String(255), ForeignKey('game.id_game'), primary_key=True)
    ID_category = Column('id_category', Integer, ForeignKey('category.id_category'), primary_key=True)


class PublisherGame(Base):
    __tablename__ = 'publisher_game'

    ID_game = Column('id_game', String(255), ForeignKey('game.id_game'), primary_key=True)
    ID_publisher = Column('id_publisher', Integer, ForeignKey('publisher.id_publisher'), primary_key=True)