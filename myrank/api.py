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

from myrank.account import Account
from myrank.config import Settings
from myrank.errors import (
    ApiError,
    ApiUnavailableError,
    NotLinkedError,
    RateLimitedError,
)
from myrank.insights import Insight, Notification
from myrank.models import (
    Badge,
    Category,
    ExternalDetails,
    ExternalResult,
    Work,
)
from myrank.rankings import CreatorRank
from myrank.social import (
    FeedItem,
    Reactions,
    SocialProfile,
    SocialSummary,
    SocialUser,
    TakeComment,
)

log = logging.getLogger(__name__)

# A IA demora mais que o resto da API; o site espera ate 75 s.
AI_TIMEOUT_SECONDS = 75.0

PEOPLE_LISTS = ("following", "followers", "suggestions", "debaters", "follow-requests")

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

    # ---------------------------------------------------------------- categorias

    async def get_categories(self, discord_id: int) -> list[Category]:
        payload = await self._get(discord_id, "/categories")
        return [Category.from_api(item) for item in _as_list(payload)]

    async def create_category(
        self, discord_id: int, name: str, templates: list[str]
    ) -> Category:
        return Category.from_api(await self._request(
            discord_id, "POST", "/categories", json={"name": name, "templates": templates}
        ))

    async def update_category(
        self, discord_id: int, category_id: int, *,
        name: str | None = None, templates: list[str] | None = None,
    ) -> Category:
        """Campo None = manter (o PUT do backend e parcial)."""
        body: Json = {}
        if name is not None:
            body["name"] = name
        if templates is not None:
            body["templates"] = templates
        return Category.from_api(
            await self._request(discord_id, "PUT", f"/categories/{category_id}", json=body)
        )

    async def delete_category(self, discord_id: int, category_id: int) -> None:
        """Apaga a tabela E todas as obras dela (cascade no banco)."""
        await self._request(discord_id, "DELETE", f"/categories/{category_id}")

    async def set_custom_fields(
        self, discord_id: int, category_id: int, fields: list[Json]
    ) -> Category:
        """Recebe a lista COMPLETA: campo com `id` e mantido/renomeado, sem `id` e
        criado, e o que ficar de fora e removido (com os valores em todas as obras)."""
        return Category.from_api(await self._request(
            discord_id, "PUT", f"/categories/{category_id}/custom-fields", json=fields
        ))

    async def create_subcategory(self, discord_id: int, category_id: int, name: str) -> None:
        await self._request(
            discord_id, "POST", f"/categories/{category_id}/subcategories", json={"name": name}
        )

    async def rename_subcategory(
        self, discord_id: int, category_id: int, subcategory_id: int, name: str
    ) -> None:
        await self._request(
            discord_id, "PUT", f"/categories/{category_id}/subcategories/{subcategory_id}",
            json={"name": name},
        )

    async def delete_subcategory(
        self, discord_id: int, category_id: int, subcategory_id: int
    ) -> None:
        """As obras ficam na tabela, so saem da subcategoria."""
        await self._request(
            discord_id, "DELETE", f"/categories/{category_id}/subcategories/{subcategory_id}"
        )

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
            await self._get(discord_id, f"/external/{endpoint}/{external_id}"), external_id
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

    # ---------------------------------------------------------------- rankings

    async def unified_ranking(
        self, discord_id: int, sort: str | None = None, table_id: int | None = None
    ) -> list[Work]:
        """Ranking geral do site: tabelas do agrupamento "Unificado", ordem manual nos
        empates; com `table_id`, so aquela tabela. `sort` None = a configuracao "nota
        ponderada" da conta."""
        params: dict[str, Any] = {}
        if sort:
            params["sort"] = sort
        if table_id is not None:
            params["table"] = table_id
        payload = await self._get(discord_id, "/rankings/unified", params=params)
        return [Work.from_api(item) for item in _as_list(payload)]

    async def creator_ranking(
        self, discord_id: int, order: str = "avg", creator_type: str | None = None
    ) -> list[CreatorRank]:
        params = {"order": order}
        if creator_type:
            params["type"] = creator_type
        payload = await self._get(discord_id, "/rankings/creators", params=params)
        return [CreatorRank.from_api(item) for item in _as_list(payload)]

    # ---------------------------------------------------------------- conquistas

    async def get_badges(self, discord_id: int) -> list[Badge]:
        payload = await self._get(discord_id, "/badges")
        return [Badge.from_api(item) for item in _as_list(payload)]

    # ---------------------------------------------------------------- social

    async def social_summary(self, discord_id: int) -> SocialSummary:
        return SocialSummary.from_api(await self._get(discord_id, "/social/summary"))

    async def feed(
        self, discord_id: int, page: int, size: int, *, following_only: bool = False
    ) -> list[FeedItem]:
        params = {"page": page, "size": size, "scope": "following" if following_only else "all"}
        payload = await self._get(discord_id, "/social/feed", params=params)
        return [FeedItem.from_api(item) for item in _as_list(payload)]

    async def people(self, discord_id: int, kind: str) -> list[SocialUser]:
        """`kind`: following | followers | suggestions | debaters | follow-requests."""
        if kind not in PEOPLE_LISTS:
            raise ValueError(f"Lista desconhecida: {kind!r}")
        payload = await self._get(discord_id, f"/social/{kind}")
        return [SocialUser.from_api(item) for item in _as_list(payload)]

    async def search_users(self, discord_id: int, query: str) -> list[SocialUser]:
        payload = await self._get(discord_id, "/social/users", params={"q": query})
        return [SocialUser.from_api(item) for item in _as_list(payload)]

    async def profile(self, discord_id: int, user_id: int) -> SocialProfile:
        return SocialProfile.from_api(await self._get(discord_id, f"/social/users/{user_id}"))

    async def toggle_follow(self, discord_id: int, user_id: int) -> SocialUser:
        """Alterna: segue, deixa de seguir, pede (perfil privado) ou cancela o pedido."""
        return SocialUser.from_api(
            await self._request(discord_id, "POST", f"/social/follow/{user_id}")
        )

    async def answer_follow_request(
        self, discord_id: int, requester_id: int, *, approve: bool
    ) -> None:
        action = "approve" if approve else "reject"
        await self._request(
            discord_id, "POST", f"/social/follow-requests/{requester_id}/{action}"
        )

    async def react(self, discord_id: int, event_id: int, kind: str) -> Reactions:
        """Mandar a mesma reacao de novo tira; outra troca."""
        return Reactions.from_api(await self._request(
            discord_id, "POST", f"/social/feed/{event_id}/react", json={"kind": kind}
        ))

    async def post_take(self, discord_id: int, work_id: int, text: str) -> FeedItem:
        return FeedItem.from_api(await self._request(
            discord_id, "POST", "/social/takes", json={"workId": work_id, "text": text}
        ))

    async def edit_take(self, discord_id: int, take_id: int, text: str) -> FeedItem:
        return FeedItem.from_api(await self._request(
            discord_id, "PATCH", f"/social/takes/{take_id}", json={"text": text}
        ))

    async def delete_take(self, discord_id: int, take_id: int) -> None:
        await self._request(discord_id, "DELETE", f"/social/takes/{take_id}")

    async def comments(self, discord_id: int, take_id: int) -> list[TakeComment]:
        payload = await self._get(discord_id, f"/social/takes/{take_id}/comments")
        return [TakeComment.from_api(item) for item in _as_list(payload)]

    async def add_comment(
        self, discord_id: int, take_id: int, text: str, parent_id: int | None = None
    ) -> TakeComment:
        return TakeComment.from_api(await self._request(
            discord_id, "POST", f"/social/takes/{take_id}/comments",
            json={"text": text, "parentCommentId": parent_id},
        ))

    async def edit_comment(self, discord_id: int, comment_id: int, text: str) -> TakeComment:
        return TakeComment.from_api(await self._request(
            discord_id, "PATCH", f"/social/comments/{comment_id}", json={"text": text}
        ))

    async def delete_comment(self, discord_id: int, comment_id: int) -> None:
        await self._request(discord_id, "DELETE", f"/social/comments/{comment_id}")

    # ---------------------------------------------------------------- conta

    async def me(self, discord_id: int) -> Account:
        return Account.from_api(await self._get(discord_id, "/users/me"))

    async def update_me(self, discord_id: int, changes: Json) -> Account:
        """PUT parcial: campo ausente nao muda."""
        return Account.from_api(await self._request(discord_id, "PUT", "/users/me", json=changes))

    # ---------------------------------------------------------------- notificacoes

    async def notifications(self, discord_id: int, page: int, size: int) -> list[Notification]:
        payload = await self._get(
            discord_id, "/notifications", params={"page": page, "size": size}
        )
        return [Notification.from_api(item) for item in _as_list(payload)]

    async def unread_notifications(self, discord_id: int) -> int:
        payload = await self._get(discord_id, "/notifications/unread-count")
        return int(payload.get("count") or 0) if isinstance(payload, dict) else 0

    async def read_all_notifications(self, discord_id: int) -> None:
        await self._request(discord_id, "POST", "/notifications/read-all")

    # ---------------------------------------------------------------- IA Insights

    async def latest_insight(self, discord_id: int) -> Insight | None:
        """None quando a pessoa ainda nao gerou nenhuma analise (204 do backend)."""
        payload = await self._get(discord_id, "/insights/latest", timeout=AI_TIMEOUT_SECONDS)
        return Insight.from_api(payload) if isinstance(payload, dict) and payload else None

    async def generate_insight(
        self, discord_id: int, work_ids: list[int], *, refresh: bool = False
    ) -> Insight:
        """Reaproveita a analise da mesma selecao (cache do backend) se `refresh` for
        False. Gerar de verdade gasta 1 das mensagens de IA do dia."""
        return Insight.from_api(await self._request(
            discord_id, "POST", "/insights/generate",
            json={"workIds": work_ids, "refresh": refresh}, timeout=AI_TIMEOUT_SECONDS,
        ))

    async def ask_insight(self, discord_id: int, insight_id: int, question: str) -> Insight:
        """Pergunta de follow-up; gasta 1 das mensagens de IA do dia."""
        return Insight.from_api(await self._request(
            discord_id, "POST", f"/insights/{insight_id}/chat",
            json={"question": question}, timeout=AI_TIMEOUT_SECONDS,
        ))

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
            # 401 tem 3 causas: bot key invalida, header ausente (essas duas sao bug
            # nosso), ou conta do Discord sem vinculo (a unica que e do usuario). O
            # backend nao diferencia por codigo, so pela mensagem -- entao e nela que
            # a gente olha. Nunca mostrar "conta nao vinculada" pras duas primeiras,
            # senao o usuario tenta se vincular pra um problema que nao e dele.
            message = _error_message(response)
            if "vincul" in message.casefold():
                log.info("Discord ID sem vinculo em %s %s", method, path)
                raise NotLinkedError
            log.error("401 de configuracao (nao de vinculo) em %s %s: %s", method, path, message)
            raise ApiUnavailableError(GENERIC_SERVER_MESSAGE)

        if status == 403:
            # Rota fora do conjunto que aceita a bot key (ou o filtro ainda nao subiu
            # nesse ambiente) -- nada que o usuario final possa corrigir.
            log.error(
                "403 em %s %s (rota fora do escopo da bot key?): %s",
                method,
                path,
                response.text[:300],
            )
            raise ApiUnavailableError(GENERIC_SERVER_MESSAGE)

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
