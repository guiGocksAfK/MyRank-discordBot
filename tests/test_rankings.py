"""/ranking e /criadores: rotas do client, fallback e o que aparece na tela."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx

from cogs.ranking import RankingCog
from myrank.errors import ApiUnavailableError
from myrank.models import Category, Work
from myrank.rankings import CreatorRank
from tests.conftest import ClientFactory
from ui import embeds
from ui.views import CreatorsView, RankingView

CREATOR_JSON = {
    "id": "vince gilligan", "name": "Vince Gilligan", "type": "Diretor", "count": 2,
    "average": 9.5, "score": 10.1,
    "works": [{"id": 1, "title": "Breaking Bad", "type": "serie", "score": 10}],
}


def interaction() -> Any:
    value = MagicMock()
    value.user.id = 123
    value.response.defer = AsyncMock()
    value.followup.send = AsyncMock()
    return value


async def run(callback_owner: RankingCog, name: str, i: Any, **kwargs: Any) -> None:
    callback: Any = getattr(callback_owner, name).callback
    await callback(callback_owner, i, **kwargs)


async def test_client_routes(make_client: ClientFactory) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, str(request.url.params)))
        if request.url.path.endswith("/creators"):
            return httpx.Response(200, json=[CREATOR_JSON])
        return httpx.Response(200, json=[{"id": 1, "title": "X", "score": 8, "finalScore": 9}])

    client = await make_client(handler)
    await client.unified_ranking(1)
    await client.unified_ranking(1, "time", 7)
    creators = await client.creator_ranking(1, "weighted", "Diretor")
    assert creators[0] == CreatorRank.from_api(CREATOR_JSON)
    assert creators[0].works[0].title == "Breaking Bad"
    assert seen == [
        ("/api/rankings/unified", ""),
        ("/api/rankings/unified", "sort=time&table=7"),
        ("/api/rankings/creators", "order=weighted&type=Diretor"),
    ]


def test_ranking_numbers_follow_the_backend_list() -> None:
    works = [Work(9, "Primeira", 7.0, 9.0, 0, 1, "Filmes", position=5),
             Work(3, "Segunda", 9.0, 8.0, 60, 2, "Series", position=1)]
    geral = embeds.ranking(works, 10, 2, 2, None, "score")
    assert geral.title == "Ranking geral (por nota)"
    assert [f.name for f in geral.fields] == ["#11. Primeira", "#12. Segunda"]
    assert geral.fields[0].value == "Nota: 7.0 | Filmes"  # nota pura e a tabela
    tabela = embeds.ranking(works, 0, 1, 1, "Filmes", "weighted")
    assert tabela.fields[0].value == "Nota final: 9.0"  # a posicao manual nao vira numero


async def test_ranking_uses_unified_route_and_falls_back() -> None:
    api: Any = MagicMock()
    api.unified_ranking = AsyncMock(return_value=[Work(1, "X", 8, 8, 0)])
    api.get_categories = AsyncMock(return_value=[Category(4, "Filmes")])
    bot: Any = MagicMock()
    bot.api = api
    cog = RankingCog(bot)

    i = interaction()
    await run(cog, "ranking", i, tabela=4, ordem="time")
    api.unified_ranking.assert_awaited_once_with(123, "time", 4)
    view = i.followup.send.call_args.kwargs["view"]
    assert isinstance(view, RankingView) and view.embed().title == "Ranking - Filmes (por tempo)"

    api.unified_ranking = AsyncMock(side_effect=ApiUnavailableError("x"))
    api.list_works = AsyncMock(return_value=[])
    await run(cog, "ranking", interaction())
    api.list_works.assert_awaited_once_with(123, None)


def test_creators_embed() -> None:
    item = CreatorRank.from_api(CREATOR_JSON)
    embed = CreatorsView([item], 123, "weighted", "Diretor").embed()
    assert embed.title == "Criadores -- Diretor (ponderado)"
    assert embed.fields[0].name == "#1. Vince Gilligan"
    assert embed.fields[0].value == (
        "Diretor · 2 obras · media 9.5 · ponderada 10.1\nBreaking Bad"
    )
    vazio = embeds.creators([], 0, 1, 1, "avg", None)
    assert vazio.title == "Criadores (por media)"
    assert "preencha o criador" in (vazio.description or "")
