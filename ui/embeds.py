"""Fabricas de embed no tema do MyRank.

Listagens sempre em embed com fields -- tabela em code block com colunas
alinhadas fica ilegivel no mobile.
"""

from __future__ import annotations

import discord

from myrank.models import Badge, ExternalDetails, UserProfile, Work

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


def badges(items: list[Badge], page: int, total_pages: int) -> discord.Embed:
    """Progresso vem pronto do backend (`Badge.progress_ratio` so evita divisao por
    zero) -- a barra aqui e so desenho, nao calculo."""
    embed = base("Conquistas")
    if not items:
        embed.description = "Nenhuma conquista ainda."
        return embed

    for badge in items:
        icon = badge.icon or ("✅" if badge.unlocked else "\U0001f512")
        if badge.unlocked:
            value = badge.description
        else:
            bar = _progress_bar(badge.progress_ratio)
            value = f"{badge.description}\n{bar} {badge.progress}/{badge.target}"
        embed.add_field(name=f"{icon} {badge.name}", value=value, inline=False)

    embed.set_footer(text=f"Pagina {page}/{total_pages}")
    return embed


def _progress_bar(ratio: float, length: int = 10) -> str:
    filled = round(ratio * length)
    return "▰" * filled + "▱" * (length - filled)


def pick_category(details: ExternalDetails) -> discord.Embed:
    """Aparece so quando `match_category` nao acha uma categoria confiavel --
    o bot pergunta, nunca inventa nem cria categoria."""
    embed = base(
        details.title,
        "Nao encontrei uma categoria sua com match confiavel. Escolha uma abaixo:",
    )
    if details.image_url:
        embed.set_thumbnail(url=details.image_url)
    return embed


def _work_fields(embed: discord.Embed, work: Work, *, show_raw_score: bool) -> discord.Embed:
    if show_raw_score:
        embed.add_field(name="Nota", value=f"{work.score:.1f}")
    embed.add_field(name="Nota final", value=f"{work.final_score:.1f}")
    if work.category_name:
        embed.add_field(name="Categoria", value=work.category_name)
    if work.time_minutes:
        embed.add_field(name="Duracao", value=f"{work.time_minutes} min")
    if work.image_url:
        embed.set_thumbnail(url=work.image_url)
    return embed


def work_added(work: Work) -> discord.Embed:
    return _work_fields(base(f"Adicionado: {work.title}"), work, show_raw_score=False)


def work_updated(work: Work) -> discord.Embed:
    """`/manage` mostra a nota crua (o que o usuario digitou), nao so a final --
    e o unico ponto onde a diferenca entre as duas importa pra quem esta editando."""
    return _work_fields(base(f"Atualizado: {work.title}"), work, show_raw_score=True)


def work_detail(work: Work) -> discord.Embed:
    return _work_fields(base(work.title), work, show_raw_score=True)


def work_removed(title: str) -> discord.Embed:
    return base(f"Removido: {title}")


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
