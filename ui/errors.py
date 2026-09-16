"""Fronteira de erro do lado do Discord.

Um lugar so traduz excecao em mensagem, e o decorator `guarded` garante que
nenhum comando escape da traducao. Isso vale mais do que try/except em cada cog:
esquecer passa a ser impossivel por construcao, nao por disciplina.

O decorator tambem faz o `defer`, porque toda chamada HTTP estoura o orcamento de
3 segundos do Discord.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate, ParamSpec, TypeVar

import discord

from myrank.errors import (
    ApiError,
    ApiUnavailableError,
    NotLinkedError,
    RateLimitedError,
)
from ui import embeds

log = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

UNEXPECTED_MESSAGE = "Algo quebrou aqui do meu lado. Tente de novo em instantes."


def to_embed(exc: Exception) -> discord.Embed:
    """Excecao -> embed. Nada aqui vaza detalhe interno para o usuario."""
    if isinstance(exc, NotLinkedError):
        return embeds.not_linked()
    if isinstance(exc, RateLimitedError):
        extra = f" Tente de novo em {exc.retry_after:.0f}s." if exc.retry_after else ""
        return embeds.error(f"Voce fez pedidos demais em pouco tempo.{extra}")
    if isinstance(exc, ApiUnavailableError):
        return embeds.error(str(exc))
    if isinstance(exc, ApiError):
        return embeds.error(exc.user_message)
    return embeds.error(UNEXPECTED_MESSAGE)


Callback = Callable[Concatenate[Any, discord.Interaction, P], Coroutine[Any, Any, T]]


def guarded(*, ephemeral: bool = False) -> Callable[[Callback[P, T]], Callback[P, T | None]]:
    """Envolve um callback de slash command com defer + tratamento de erro.

    `ephemeral` vale para a resposta de sucesso; erro e *sempre* ephemeral, porque
    os comandos rodam em canal compartilhado e erro costuma carregar dado de conta.

    Tipado com `Concatenate[Any, Interaction, P]` -- e nao `Callable[..., Awaitable[Any]]`
    -- para casar com `CommandCallback` do discord.py (`self, interaction, *P`). Isso
    ainda nao fecha 100%: mypy nao resolve o `Union` de assinaturas com/sem `self` que
    `app_commands.command` aceita, entao o uso em cog continua precisando de
    `# type: ignore[arg-type]` no ponto de uso -- mas o corpo do decorator agora e
    tipado de verdade, e comandos fora de Cog (sem `self`) fecham sem ignore nenhum.
    """

    def decorator(func: Callback[P, T]) -> Callback[P, T | None]:
        @functools.wraps(func)
        async def wrapper(
            self: Any, interaction: discord.Interaction, /, *args: P.args, **kwargs: P.kwargs
        ) -> T | None:
            await interaction.response.defer(ephemeral=ephemeral)
            try:
                return await func(self, interaction, *args, **kwargs)
            # Captura ampla de proposito: silencio e o pior modo de falha num bot.
            except Exception as exc:
                if not isinstance(exc, (NotLinkedError, RateLimitedError, ApiError)):
                    log.exception("Erro nao tratado em /%s", getattr(func, "__name__", "?"))
                await _reply_error(interaction, to_embed(exc))
                return None

        return wrapper

    return decorator


async def _reply_error(interaction: discord.Interaction, embed: discord.Embed) -> None:
    try:
        await interaction.followup.send(embed=embed, ephemeral=True)
    except discord.HTTPException:
        log.warning("Nao foi possivel entregar a mensagem de erro ao usuario.")
