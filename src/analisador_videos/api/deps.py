from collections.abc import Generator

from sqlalchemy.orm import Session

from analisador_videos.db.database import get_db

DbSession = Generator[Session, None, None]
