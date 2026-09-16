from __future__ import annotations

import httpx
import pytest

from myrank.errors import (
    ApiError,
    ApiUnavailableError,
    NotLinkedError,
    RateLimitedError,
)
from tests.conftest import SETTINGS, ClientFactory


def json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


async def test_envia_bot_key_e_discord_id_em_toda_chamada(make_client: ClientFactory) -> None:
    capturado: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado.update(request.headers)
        return json_response([])

    client = await make_client(handler)
    await client.get_categories(123456789)

    assert capturado["x-bot-key"] == SETTINGS.bot_api_key
    assert capturado["x-discord-id"] == "123456789"


async def test_401_de_vinculo_vira_not_linked(make_client: ClientFactory) -> None:
    message = "Esta conta do Discord nao esta vinculada a um usuario do MyRank."
    client = await make_client(lambda _: json_response({"message": message}, 401))

    with pytest.raises(NotLinkedError):
        await client.get_categories(1)


async def test_401_de_configuracao_nao_vira_not_linked(make_client: ClientFactory) -> None:
    """Bot key invalida e header ausente tambem sao 401, mas sao bug/config nosso --
    nao podem virar a mensagem de "vincule sua conta" pro usuario."""
    client = await make_client(lambda _: json_response({"message": "Bot key invalida."}, 401))

    with pytest.raises(ApiUnavailableError):
        await client.get_categories(1)


async def test_403_rota_fora_do_escopo_vira_unavailable(make_client: ClientFactory) -> None:
    client = await make_client(lambda _: httpx.Response(403))

    with pytest.raises(ApiUnavailableError):
        await client.get_categories(1)


async def test_429_vira_rate_limited_com_retry_after(make_client: ClientFactory) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "12"}, json={})

    client = await make_client(handler)

    with pytest.raises(RateLimitedError) as exc:
        await client.get_categories(1)
    assert exc.value.retry_after == 12.0


async def test_400_usa_mensagem_do_backend(make_client: ClientFactory) -> None:
    client = await make_client(lambda _: json_response({"message": "Nota deve ser 0 a 10"}, 400))

    with pytest.raises(ApiError) as exc:
        await client.create_work(1, {"score": 99})
    assert exc.value.user_message == "Nota deve ser 0 a 10"


async def test_500_nao_vaza_detalhe_do_servidor(make_client: ClientFactory) -> None:
    client = await make_client(
        lambda _: httpx.Response(500, text="NullPointerException em WorkService:42")
    )

    with pytest.raises(ApiUnavailableError) as exc:
        await client.get_categories(1)
    assert "NullPointer" not in str(exc.value)


async def test_backend_fora_do_ar_falha_limpo(make_client: ClientFactory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = await make_client(handler)

    with pytest.raises(ApiUnavailableError):
        await client.get_categories(1)


async def test_lista_aceita_envelope_paginado(make_client: ClientFactory) -> None:
    payload = {"content": [{"id": 1, "name": "Filmes", "isDefault": True}]}
    client = await make_client(lambda _: json_response(payload))

    categorias = await client.get_categories(1)

    assert [c.name for c in categorias] == ["Filmes"]


async def test_delete_sem_corpo_nao_quebra(make_client: ClientFactory) -> None:
    client = await make_client(lambda _: httpx.Response(204))

    await client.delete_work(1, 7)


async def test_repr_nao_vaza_a_api_key(make_client: ClientFactory) -> None:
    client = await make_client(lambda _: json_response({}))

    assert SETTINGS.bot_api_key not in repr(client)
    assert SETTINGS.bot_api_key not in repr(SETTINGS)
    assert SETTINGS.discord_token not in repr(SETTINGS)


async def test_external_search_uses_backend_external_id(make_client: ClientFactory) -> None:
    payload = [{
        "externalId": "1396",
        "title": "Breaking Bad",
        "posterUrl": "https://example.com/poster.jpg",
        "releaseDate": "2008-01-20",
    }]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/external/search/tv"
        assert request.url.params["query"] == "Breaking Bad"
        return json_response(payload)

    client = await make_client(handler)
    results = await client.external_search(123, "tv", "Breaking Bad")
    assert len(results) == 1
    assert results[0].external_id == "1396"
    assert results[0].title == "Breaking Bad"
    assert results[0].year == "2008"


async def test_external_details_without_id(make_client: ClientFactory) -> None:
    payload = {
        "title": "Breaking Bad", "imageUrl": "https://example.com/poster.jpg",
        "creator": "Vince Gilligan", "releaseDate": "2008-01-20", "timeMinutes": 3000,
    }
    client = await make_client(lambda _: json_response(payload))
    details = await client.external_details(123, "tv", "1396")
    assert details.title == "Breaking Bad"
    assert details.time_minutes == 3000
    assert details.creator == "Vince Gilligan"
