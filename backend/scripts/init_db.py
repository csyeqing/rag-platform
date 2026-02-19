from __future__ import annotations

from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.models import User
from app.db.session import SessionLocal


def main() -> None:
    init_db()
    settings = get_settings()
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == settings.default_admin_username).first()
        print('Database initialization completed.')
        if admin:
            print(
                f"Default admin ready: username={admin.username}, role={admin.role.value}, is_active={admin.is_active}"
            )


if __name__ == '__main__':
    main()
