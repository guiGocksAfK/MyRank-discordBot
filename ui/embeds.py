"""Fabricas de embed no tema do MyRank.

Listagens sempre em embed com fields -- tabela em code block com colunas
alinhadas fica ilegivel no mobile.
"""

from __future__ import annotations

import discord

from myrank.models import UserProfile

ACCENT = discord.Color(0xD4AF37)
DANGER = discord.Color(0xB3261E)

SITE_URL = "https://myrank.duckdns.org"


def base(title: str, description: str | None = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=ACCENT)


def profile(user: UserProfile) -> discord.Embed:
    embed = base(user.username or "Perfil MyRank")
    embed.add_field(name="Obras avaliadas", value=str(user.work_count))
    embed.add_field(
        name="Media geral",
        value=f"{user.average_score:.1f}" if user.average_score is not None else "-",
    )
    if user.avatar_url:
        embed.set_thumbnail(url=user.avatar_url)
    return embed


def error(message: str) -> discord.Embed:
    return discord.Embed(title="Nao deu certo", description=message, color=DANGER)


def not_linked() -> discord.Embed:
    """Unico onboarding do bot: nao existe comando de vinculacao."""
    return discord.Embed(
        title="Conta nao vinculada",
        description=(
            f"Sua conta do Discord ainda nao esta ligada ao MyRank.\n\n"
            f"Entre uma vez em {SITE_URL} usando **Login com Discord** "
            f"e depois volte aqui -- e so isso, uma vez so."
        ),
        color=ACCENT,
    )
