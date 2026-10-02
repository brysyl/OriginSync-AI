import asyncpg
from asyncpg import Pool


async def configure_connection(connection: asyncpg.Connection) -> None:
    import json

    await connection.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await connection.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_pool(database_url: str) -> Pool:
    return await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
        server_settings={"application_name": "originsync-api"},
        init=configure_connection,
    )
