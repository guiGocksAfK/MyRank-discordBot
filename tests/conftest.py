from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from myrank.api import MyRankClient
from myrank.config import Settings

SETTINGS = Settings(
    discord_token="token-de-teste",
    api_url="http://localhost:8080/api",
    bot_api_key="chave-secreta-de-teste",
    guild_id=None,
    log_level="INFO",
)

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
async def make_client() -> AsyncIterator[Callable[[Handler], MyRankClient]]:
    """Fabrica de MyRankClient com MockTransport -- sem rede e sem Discord.

    So e possivel porque `myrank/` nao importa discord.py: o client recebe um
    `discord_id: int`, nunca uma Interaction.
    """
    created: list[MyRankClient] = []

    async def factory(handler: Handler) -> MyRankClient:
        client = MyRankClient(SETTINGS)
        await client.start(transport=httpx.MockTransport(handler))
        created.append(client)
        return client

    yield factory  # type: ignore[misc]

    for client in created:
        await client.aclose()
