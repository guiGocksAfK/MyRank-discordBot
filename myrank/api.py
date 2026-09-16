"""Cliente HTTP do MyRank.

Regras que este modulo existe para garantir:

* Um unico `httpx.AsyncClient` por processo, criado no `setup_hook` e fechado no
  shutdown. Um client por request vazaria conexao e jogaria fora o pool.
* `discord_id` e parametro obrigatorio de todo metodo. Nao ha como esquecer o
  header por omissao, e o valor vem sempre de `interaction.user.id` -- nunca de
  algo digitado pelo usuario, senao qualquer um agiria como qualquer outro.
* A traducao de status HTTP em excecao acontece em um lugar so (`_raise_for_status`).
* A API key nunca aparece em log, em `repr` ou em mensagem de erro.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx

from myrank.config import Settings
from myrank.errors import (
    ApiError,
    ApiUnavailableError,
    NotLinkedError,
    RateLimitedError,
)
from myrank.models import (
    Badge,
    Category,
    ExternalDetails,
    ExternalResult,
    UserProfile,
    Work,
)

log = logging.getLogger(__name__)

Json = dict[str, Any]

GENERIC_SERVER_MESSAGE = "O MyRank nao respondeu. Tente de novo em instantes."


class MyRankClient:
    """Fachada tipada sobre a API do MyRank. Nao conhece discord.py."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    # ---------------------------------------------------------------- ciclo de vida

    async def start(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Cria o client unico. O transport existe para os testes injetarem MockTransport."""
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            base_url=self._settings.api_url,
            timeout=self._settings.request_timeout,
            headers={"X-Bot-Key": self._settings.bot_api_key},
            transport=transport,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> MyRankClient:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"MyRankClient(api_url={self._settings.api_url!r})"

    # ---------------------------------------------------------------- perfil

    async def get_me(self, discord_id: int) -> UserProfile:
        return UserProfile.from_api(await self._get(discord_id, "/users/me"))

    # ---------------------------------------------------------------- categorias

    async def get_categories(self, discord_id: int) -> list[Category]:
        payload = await self._get(discord_id, "/categories")
        return [Category.from_api(item) for item in _as_list(payload)]

    # ---------------------------------------------------------------- busca externa

    async def external_search(
        self, discord_id: int, endpoint: str, query: str
    ) -> list[ExternalResult]:
        payload = await self._get(
            discord_id, f"/external/search/{endpoint}", params={"query": query}
        )
        return [ExternalResult.from_api(item) for item in _as_list(payload)]

    async def external_details(
        self, discord_id: int, endpoint: str, external_id: str
    ) -> ExternalDetails:
        return ExternalDetails.from_api(
            await self._get(discord_id, f"/external/{endpoint}/{external_id}")
        )

    # ---------------------------------------------------------------- obras

    async def create_work(self, discord_id: int, payload: Json) -> Work:
        """Cria a obra ja com a nota -- nao existe endpoint separado de avaliacao.

        O finalScore vem calculado na resposta; o bot so exibe.
        """
        return Work.from_api(await self._request(discord_id, "POST", "/works", json=payload))

    async def update_work(self, discord_id: int, work_id: int, payload: Json) -> Work:
        return Work.from_api(
            await self._request(discord_id, "PUT", f"/works/{work_id}", json=payload)
        )

    async def delete_work(self, discord_id: int, work_id: int) -> None:
        await self._request(discord_id, "DELETE", f"/works/{work_id}")

    async def list_works(self, discord_id: int, category_id: int | None = None) -> list[Work]:
        path = "/works/unified" if category_id is None else f"/works/category/{category_id}"
        return [Work.from_api(item) for item in _as_list(await self._get(discord_id, path))]

    # ---------------------------------------------------------------- conquistas

    async def get_badges(self, discord_id: int) -> list[Badge]:
        payload = await self._get(discord_id, "/badges")
        return [Badge.from_api(item) for item in _as_list(payload)]

    # ---------------------------------------------------------------- transporte

    async def _get(self, discord_id: int, path: str, **kwargs: Any) -> Any:
        return await self._request(discord_id, "GET", path, **kwargs)

    async def _request(self, discord_id: int, method: str, path: str, **kwargs: Any) -> Any:
        if self._client is None:
            raise RuntimeError("MyRankClient.start() nao foi chamado.")

        try:
            response = await self._client.request(
                method, path, headers={"X-Discord-Id": str(discord_id)}, **kwargs
            )
        except httpx.TimeoutException as exc:
            log.warning("Timeout em %s %s", method, path)
            raise ApiUnavailableError(GENERIC_SERVER_MESSAGE) from exc
        except httpx.TransportError as exc:
            # Backend reiniciando: falha limpa agora, volta a funcionar sozinho depois.
            log.warning("Falha de transporte em %s %s: %s", method, path, exc)
            raise ApiUnavailableError(GENERIC_SERVER_MESSAGE) from exc

        self._raise_for_status(response, method, path)
        return _decode(response)

    def _raise_for_status(self, response: httpx.Response, method: str, path: str) -> None:
        status = response.status_code
        if status < 400:
            return

        if status == 401:
            # A X-Bot-Key e fixa e valida por construcao, entao 401 aqui significa
            # que o backend nao conhece este Discord ID.
            log.info("Discord ID sem vinculo em %s %s", method, path)
            raise NotLinkedError

        if status == 429:
            raise RateLimitedError(_retry_after(response))

        if status >= 500:
            # Detalhe do servidor fica no log; o usuario recebe texto generico.
            log.error("Erro %s do backend em %s %s: %s", status, method, path, response.text[:500])
            raise ApiUnavailableError(GENERIC_SERVER_MESSAGE)

        raise ApiError(status, _error_message(response))


def _decode(response: httpx.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        log.error("Resposta nao-JSON do backend: %s", response.text[:200])
        raise ApiUnavailableError(GENERIC_SERVER_MESSAGE) from None


def _as_list(payload: Any) -> list[Json]:
    """Aceita lista pura ou envelope paginado do Spring (campo content)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            return content
    return []


def _error_message(response: httpx.Response) -> str:
    """Mensagem do GlobalExceptionHandler do backend, quando houver."""
    try:
        body = response.json()
    except ValueError:
        return "Nao foi possivel completar a operacao."
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "Nao foi possivel completar a operacao."


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None
