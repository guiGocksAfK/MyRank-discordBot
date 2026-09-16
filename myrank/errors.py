"""Excecoes do cliente HTTP.

Toda traducao de status HTTP para excecao acontece em `myrank.api`; toda traducao
de excecao para mensagem no Discord acontece em `ui.errors`. Nao ha nada no meio.
"""

from __future__ import annotations


class MyRankError(Exception):
    """Base de tudo que o cliente do MyRank pode levantar."""


class NotLinkedError(MyRankError):
    """A conta do Discord nao esta vinculada a um usuario do MyRank.

    Nao e um bug: e o unico onboarding do bot. O usuario resolve entrando uma vez
    no site com "Login com Discord".
    """


class RateLimitedError(MyRankError):
    """O backend respondeu 429."""

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__("Rate limit atingido.")


class ApiError(MyRankError):
    """Erro de validacao ou de regra vindo do backend (4xx).

    `user_message` e a mensagem do GlobalExceptionHandler do Java, segura para
    exibir ao usuario.
    """

    def __init__(self, status: int, user_message: str) -> None:
        self.status = status
        self.user_message = user_message
        super().__init__(f"HTTP {status}: {user_message}")


class ApiUnavailableError(MyRankError):
    """Backend fora do ar, com timeout ou respondendo 5xx.

    Separado de `ApiError` porque a acao do usuario e diferente: nao ha nada a
    corrigir na entrada dele, so tentar de novo. Cobre o criterio de o bot
    sobreviver a um restart do backend.
    """
