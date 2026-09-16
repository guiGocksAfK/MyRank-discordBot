"""Configuracao carregada uma unica vez, no boot.

Nenhum `os.getenv` fora deste modulo: variavel faltando derruba o bot na
inicializacao, com mensagem clara, em vez de estourar na primeira interacao.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_API_URL = "http://localhost:8080/api"
DEFAULT_TIMEOUT_SECONDS = 10.0


class MissingSettingError(RuntimeError):
    """Variavel de ambiente obrigatoria ausente ou vazia."""


@dataclass(frozen=True, slots=True, repr=False)
class Settings:
    discord_token: str
    api_url: str
    bot_api_key: str
    guild_id: int | None
    log_level: str
    request_timeout: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def load(cls) -> Settings:
        load_dotenv()
        return cls(
            discord_token=_required("DISCORD_TOKEN"),
            api_url=os.getenv("MYRANK_API_URL", DEFAULT_API_URL).rstrip("/"),
            bot_api_key=_required("MYRANK_BOT_API_KEY"),
            guild_id=_optional_int("DISCORD_GUILD_ID"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )

    def __repr__(self) -> str:
        # Segredos mascarados: este repr aparece em traceback e em log de debug,
        # que e exatamente onde uma chave vaza sem ninguem perceber.
        return (
            f"Settings(api_url={self.api_url!r}, guild_id={self.guild_id!r}, "
            f"log_level={self.log_level!r}, discord_token='***', bot_api_key='***')"
        )


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingSettingError(
            f"{name} nao esta definida. Copie .env.example para .env e preencha."
        )
    return value


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise MissingSettingError(
            f"{name} precisa ser um numero inteiro (recebido: {raw!r})."
        ) from exc
