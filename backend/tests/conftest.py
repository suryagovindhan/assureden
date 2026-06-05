import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.db.session import engine, get_db
from app.main import app

@pytest.fixture(scope="session")
def db_engine():
    yield engine

@pytest.fixture
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db):
    def _get_db_override():
        yield db
    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
