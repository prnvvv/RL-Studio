from __future__ import annotations

from logging.config import fileConfig
from sqlalchemy import create_engine

from backend.database.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file.
config = configparser = type("config", (), {"get_main_option": lambda s, k: None})()

# Interpret the config file for Python logging.
# This line resolves the file config specified in the [alembic] section
# in your alembic.ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is obtained
    from the DB-API.

    By skipping the Engine creation we don't even need
    a DBAPI to be available.

    """
    url = config.get_main_option("URL")
    context = alembic.context
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with Alembic's
    context.

    """
    connectable = create_engine(config.get_main_option("URL"))

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()
