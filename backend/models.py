from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(100))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    # Relationships
    queries = relationship("Query", back_populates="user")

class Query(Base):
    __tablename__ = 'queries'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    query_text = Column(Text)
    timestamp = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="queries")
    interactions = relationship("Interaction", back_populates="query")

class Interaction(Base):
    __tablename__ = 'interactions'

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey('queries.id'))
    response = Column(Text)
    timestamp = Column(DateTime)

    # Relationships
    query = relationship("Query", back_populates="interactions")