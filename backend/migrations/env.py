"""Alembic environment; migration is always an explicit command."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from ima.infrastructure.db.base import metadata

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

target_metadata = metadata


def get_url() -> str:
    return os.environ.get("IMA_DATABASE_URL", context.config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema="ima",
    )
    context.execute("CREATE SCHEMA IF NOT EXISTS ima")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = context.config.get_section(context.config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # Alembic creates its version table before running the first revision.
        # Bootstrap the isolated schema before that bookkeeping step.
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ima"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table_schema="ima",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
