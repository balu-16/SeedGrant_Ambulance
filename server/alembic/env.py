import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401
from app.db.base import Base

config = context.config
# override sqlalchemy.url from env (sync URL for migrations)
# NOTE: escape % as %% — ConfigParser interpolation chokes on URL-encoded
# passwords (e.g. %40 for @), which silently broke all offline/online runs.
try:
    from app.core.config import get_settings
    config.set_main_option(
        "sqlalchemy.url", get_settings().SYNC_DATABASE_URL.replace("%", "%%")
    )
except Exception as e:
    from app.core.logging import get_logger

    get_logger("alembic.env").warning(
        "sqlalchemy_url_override_failed", error=str(e)
    )

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # psycopg3 + pgbouncer (transaction mode) also chokes on prepared
    # statements — disable them so `alembic upgrade head` works on pooler URLs.
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"prepare_threshold": None},
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
