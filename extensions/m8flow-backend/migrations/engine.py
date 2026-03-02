import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def make_engine():
    uri = os.environ["M8FLOW_BACKEND_DATABASE_URI"]
    return create_engine(uri, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False)
