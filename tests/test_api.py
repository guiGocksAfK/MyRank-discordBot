from __future__ import annotations

import httpx
import pytest

from myrank.errors import (
    ApiError,
    ApiUnavailableError,
    NotLinkedError,
    RateLimitedError,
)
from tests.conftest import SETTINGS


def json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


async def test_envia_bot_key_e_discord_id_em_toda_chamada(make_client) -> None:
    capturado: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado.update(request.headers)
        return json_response([])

    client = await make_client(handler)
    await client.get_categories(123456789)

    assert capturado["x-bot-key"] == SETTINGS.bot_api_key
    assert capturado["x-discord-id"] == "123456789"


async def test_401_de_vinculo_vira_not_linked(make_client) -> None:
    message = "Esta conta do Discord nao esta vinculada a um usuario do MyRank."
    client = await make_client(lambda _: json_response({"message": message}, 401))

    with pytest.raises(NotLinkedError):
        await client.get_categories(1)


async def test_401_de_configuracao_nao_vira_not_linked(make_client) -> None:
    """Bot key invalida e header ausente tambem sao 401, mas sao bug/config nosso --
    nao podem virar a mensagem de "vincule sua conta" pro usuario."""
    client = await make_client(lambda _: json_response({"message": "Bot key invalida."}, 401))

    with pytest.raises(ApiUnavailableError):
        await client.get_categories(1)


async def test_403_rota_fora_do_escopo_vira_unavailable(make_client) -> None:
    client = await make_client(lambda _: httpx.Response(403))

    with pytest.raises(ApiUnavailableError):
        await client.get_categories(1)


async def test_429_vira_rate_limited_com_retry_after(make_client) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "12"}, json={})

    client = await make_client(handler)

    with pytest.raises(RateLimitedError) as exc:
        await client.get_categories(1)
    assert exc.value.retry_after == 12.0


async def test_400_usa_mensagem_do_backend(make_client) -> None:
    client = await make_client(lambda _: json_response({"message": "Nota deve ser 0 a 10"}, 400))

    with pytest.raises(ApiError) as exc:
        await client.create_work(1, {"score": 99})
    assert exc.value.user_message == "Nota deve ser 0 a 10"


async def test_500_nao_vaza_detalhe_do_servidor(make_client) -> None:
    client = await make_client(
        lambda _: httpx.Response(500, text="NullPointerException em WorkService:42")
    )

    with pytest.raises(ApiUnavailableError) as exc:
        await client.get_categories(1)
    assert "NullPointer" not in str(exc.value)


async def test_backend_fora_do_ar_falha_limpo(make_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = await make_client(handler)

    with pytest.raises(ApiUnavailableError):
        await client.get_categories(1)


async def test_lista_aceita_envelope_paginado(make_client) -> None:
    payload = {"content": [{"id": 1, "name": "Filmes", "isDefault": True}]}
    client = await make_client(lambda _: json_response(payload))

    categorias = await client.get_categories(1)

    assert [c.name for c in categorias] == ["Filmes"]


async def test_delete_sem_corpo_nao_quebra(make_client) -> None:
    client = await make_client(lambda _: httpx.Response(204))

    await client.delete_work(1, 7)


async def test_repr_nao_vaza_a_api_key(make_client) -> None:
    client = await make_client(lambda _: json_response({}))

    assert SETTINGS.bot_api_key not in repr(client)
    assert SETTINGS.bot_api_key not in repr(SETTINGS)
    assert SETTINGS.discord_token not in repr(SETTINGS)
