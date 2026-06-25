import sqlite3
import pytest


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()
