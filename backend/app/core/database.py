from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    if "sqlite" in settings.DATABASE_URL:
        with engine.connect() as conn:
            from sqlalchemy import text
            try:
                res = conn.execute(text("PRAGMA table_info(messages)"))
                cols = [row[1] for row in res.fetchall()]
                if "attachments" not in cols:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN attachments JSON DEFAULT '[]'"))
                    conn.commit()
            except Exception:
                pass
