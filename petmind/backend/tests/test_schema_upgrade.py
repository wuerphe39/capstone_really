from sqlalchemy import create_engine

from .. import database


def test_existing_sqlite_outings_gain_consent_column(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "old.db"}')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE outings ('
            'id TEXT PRIMARY KEY, pet_id TEXT, title TEXT, input_mode TEXT, '
            'started_at DATETIME, ended_at DATETIME)')
    monkeypatch.setattr(database, 'engine', engine)
    database.init_db()
    database.init_db()
    with engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(outings)')}
    assert 'store_consent_at' in columns
    engine.dispose()
