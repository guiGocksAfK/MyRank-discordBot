"""Fabricas de embed no tema do MyRank.

Listagens sempre em embed com fields -- tabela em code block com colunas
alinhadas fica ilegivel no mobile.
"""

from __future__ import annotations

import discord

from myrank.media import MediaType, template_label
from myrank.models import Badge, Category, ExternalDetails, ExternalResult, Work

ACCENT = discord.Color(0xD4AF37)
DANGER = discord.Color(0xB3261E)

SITE_URL = "https://myrank.duckdns.org"


def base(title: str, description: str | None = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=ACCENT)


def profile(
    display_name: str,
    avatar_url: str | None,
    work_count: int,
    average_score: float | None,
    badges_unlocked: int,
    badges_total: int,
) -> discord.Embed:
    """`/api/users` esta fora do escopo da bot key -- nao ha como pedir username nem
    avatar ao MyRank, entao quem responde por isso e o proprio Discord (mais
    atualizado de qualquer forma). `average_score` e media aritmetica calculada
    aqui em cima de notas que ja sao finais -- exibicao, nao regra de negocio nova."""
    embed = base(display_name or "Perfil MyRank")
    embed.add_field(name="Obras avaliadas", value=str(work_count))
    embed.add_field(
        name="Media geral",
        value=f"{average_score:.1f}" if average_score is not None else "-",
    )
    embed.add_field(name="Conquistas", value=f"{badges_unlocked}/{badges_total}")
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    return embed


def ranking(
    works: list[Work], start_index: int, page: int, total_pages: int, category_name: str | None
) -> discord.Embed:
    """Uma pagina do ranking. Filtrado por categoria, usa `work.position` (pronto do
    backend); em "geral" (todas as categorias juntas) esse campo repete entre
    categorias diferentes, entao a numeracao cai pra ordem da lista mesmo --
    `start_index` e a posicao (0-based) do primeiro item da pagina nessa lista."""
    title = f"Ranking - {category_name}" if category_name else "Ranking geral"
    embed = base(title)
    if not works:
        embed.description = "Nenhuma obra avaliada ainda."
        return embed

    use_position = category_name is not None
    for offset, work in enumerate(works, start=1):
        rank = (
            work.position
            if (use_position and work.position is not None)
            else start_index + offset
        )
        value = f"Nota final: {work.final_score:.1f}"
        if work.time_minutes:
            value += f" | {work.time_minutes} min"
        embed.add_field(name=f"#{rank}. {work.title}", value=value, inline=False)

    embed.set_footer(text=f"Pagina {page}/{total_pages}")
    return embed


def badges(items: list[Badge], page: int, total_pages: int) -> discord.Embed:
    """Progresso vem pronto do backend (`Badge.progress_ratio` so evita divisao por
    zero) -- a barra aqui e so desenho, nao calculo. `has_progress=False` e uma
    conquista de tudo-ou-nada (sem barra fazendo sentido nenhum)."""
    embed = base("Conquistas")
    if not items:
        embed.description = "Nenhuma conquista ainda."
        return embed

    for badge in items:
        icon = badge.icon or ("✅" if badge.unlocked else "\U0001f512")
        if badge.unlocked or not badge.has_progress:
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


def pick_table(details: ExternalDetails) -> discord.Embed:
    """Aparece quando mais de uma tabela aceita esse tipo -- o bot pergunta."""
    embed = base(details.title, "Em qual tabela essa obra entra?")
    if details.image_url:
        embed.set_thumbnail(url=details.image_url)
    return embed


def pick_subcategory(title: str, image_url: str | None, table: Category) -> discord.Embed:
    embed = base(title[:256], f"Quer colocar numa subcategoria de **{table.name}**?")
    if image_url:
        embed.set_thumbnail(url=image_url)
    return embed


def pick_template(table: Category) -> discord.Embed:
    return base(table.name[:256], "Essa tabela aceita mais de um tipo. Qual e o da obra?")


def manual_ready(table: Category, template: str) -> discord.Embed:
    return base(
        table.name[:256],
        f"Nova obra do tipo **{template_label(template)}**. "
        "Clique abaixo para preencher titulo, nota e o resto.",
    )


def _work_fields(embed: discord.Embed, work: Work, *, show_raw_score: bool) -> discord.Embed:
    if show_raw_score:
        embed.add_field(name="Nota", value=f"{work.score:.1f}")
    embed.add_field(name="Nota final", value=f"{work.final_score:.1f}")
    if work.category_name:
        table = work.category_name
        if work.subcategory_name:
            table += f" > {work.subcategory_name}"
        embed.add_field(name="Tabela", value=table)
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


def search_result(
    result: ExternalResult, media_label: str, page: int, total: int
) -> discord.Embed:
    embed = base(result.title[:256], "Confira a capa e use Ver detalhes antes de cadastrar.")
    embed.add_field(name="Tipo", value=media_label)
    embed.add_field(name="Ano", value=result.year or "Nao informado")
    if result.creator:
        embed.add_field(name="De", value=result.creator[:1024])
    if result.poster_url:
        embed.set_image(url=result.poster_url)
    else:
        embed.description = (embed.description or "") + "\nCapa nao disponivel."
    embed.set_footer(text=f"Resultado {page}/{total} | Use < e > para comparar as obras.")
    return embed


# Ficha mostrada na previa, na ordem do card do site. Generos e status ficam de
# fora: o site tambem nao mostra generos no card, e o status vem cru da API, em ingles.
_FICHA_LABELS: tuple[tuple[str, str], ...] = (
    ("seasons", "Temporadas"),
    ("episodes", "Episodios"),
    ("volumes", "Volumes"),
    ("pages", "Paginas"),
    ("album", "Album"),
    ("trackCount", "Faixas"),
)


def external_preview(details: ExternalDetails, media: MediaType) -> discord.Embed:
    embed = base(details.title[:256], "E esta a obra? Confirme abaixo para informar sua nota.")
    embed.add_field(name="Tipo", value=media.label)
    embed.add_field(name="Lancamento", value=(details.release_date or "Nao informado")[:1024])
    embed.add_field(name="Criador / autor", value=(details.creator or "Nao informado")[:1024])
    if media.time_weighted:
        embed.add_field(
            name="Duracao total",
            value=f"{details.time_minutes} min" if details.time_minutes else "Nao informada",
        )
    for key, label in _FICHA_LABELS:
        value = details.details.get(key)
        if value not in (None, "", 0):
            embed.add_field(name=label, value=str(value)[:1024])
    if details.image_url:
        embed.set_image(url=details.image_url)
    return embed
