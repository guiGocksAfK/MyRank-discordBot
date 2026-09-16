"""Fabricas de embed no tema do MyRank.

Listagens sempre em embed com fields -- tabela em code block com colunas
alinhadas fica ilegivel no mobile.
"""

from __future__ import annotations

import discord

from myrank.models import UserProfile, Work

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


def ranking(
    works: list[Work], start_index: int, page: int, total_pages: int, category_name: str | None
) -> discord.Embed:
    """Uma pagina do ranking. `start_index` e a posicao (0-based) do primeiro item
    da pagina na lista completa -- so para numerar, a ordem em si e do backend."""
    title = f"Ranking - {category_name}" if category_name else "Ranking geral"
    embed = base(title)
    if not works:
        embed.description = "Nenhuma obra avaliada ainda."
        return embed

    for offset, work in enumerate(works, start=1):
        value = f"Nota final: {work.final_score:.1f}"
        if work.time_minutes:
            value += f" | {work.time_minutes} min"
        embed.add_field(name=f"#{start_index + offset}. {work.title}", value=value, inline=False)

    embed.set_footer(text=f"Pagina {page}/{total_pages}")
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
