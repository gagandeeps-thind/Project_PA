from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# We use SQLite for local development. It will create a file named 'fitness_mvp.db'
# NOTE: For Production Phase 2 (Domain Expansion), this MUST be migrated to 
# PostgreSQL with the PostGIS extension to handle spatial polygon intersect queries.
SQLALCHEMY_DATABASE_URL = "sqlite:///./fitness_mvp.db"

# The engine is the actual connection to the database.
# (check_same_thread=False is a specific requirement just for SQLite in FastAPI)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# SessionLocal is what we will use to actually talk to the database in our API endpoints
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class that all of our Database Models will inherit from
Base = declarative_base()