"""Fabricas de embed no tema do MyRank.

Listagens sempre em embed com fields -- tabela em code block com colunas
alinhadas fica ilegivel no mobile.
"""

from __future__ import annotations

import discord

from myrank.media import CUSTOM_TEMPLATE, MediaType, template_label
from myrank.models import Badge, Category, ExternalDetails, ExternalResult, Work
from myrank.rankings import CreatorRank

ACCENT = discord.Color(0xD4AF37)
DANGER = discord.Color(0xB3261E)

SITE_URL = "https://myrank.duckdns.org"


def _valid_url(url: str | None) -> bool:
    return bool(url and url.startswith(("https://", "http://")))


def base(title: str, description: str | None = None) -> discord.Embed:
    return discord.Embed(title=title[:256], description=description, color=ACCENT)


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
    if _valid_url(avatar_url):
        embed.set_thumbnail(url=avatar_url)
    return embed


SORT_TITLES = {"score": "por nota", "weighted": "por nota ponderada", "time": "por tempo"}


def ranking(
    works: list[Work], start_index: int, page: int, total_pages: int, category_name: str | None,
    sort: str | None = None,
) -> discord.Embed:
    """Uma pagina do ranking, na ordem que o backend devolveu (`/rankings/unified`):
    a posicao e a da lista. `start_index` e a posicao (0-based) do primeiro item da
    pagina. Com `sort`, o valor mostrado e o que ordenou."""
    title = f"Ranking - {category_name}" if category_name else "Ranking geral"
    if sort in SORT_TITLES:
        title += f" ({SORT_TITLES[sort]})"
    embed = base(title)
    if not works:
        embed.description = "Nenhuma obra avaliada ainda."
        return embed

    for offset, work in enumerate(works, start=1):
        rank = start_index + offset
        if sort == "score":
            value = f"Nota: {work.score:.1f}"
        else:
            value = f"Nota final: {work.final_score:.1f}"
        if work.time_minutes:
            value += f" | {work.time_minutes} min"
        if not category_name and work.category_name:
            value += f" | {work.category_name}"
        embed.add_field(name=f"#{rank}. {work.title}"[:256], value=value[:1024], inline=False)

    embed.set_footer(text=f"Pagina {page}/{total_pages}")
    return embed


CREATOR_ORDER_TITLES = {"avg": "por media", "weighted": "ponderado", "works": "por obras"}


def creators(
    items: list[CreatorRank], start_index: int, page: int, total_pages: int,
    order: str, creator_type: str | None,
) -> discord.Embed:
    """Uma pagina do ranking de criadores. Media, nota ponderada e contagem vem prontas
    do backend; aqui so se escreve."""
    title = f"Criadores -- {creator_type}" if creator_type else "Criadores"
    title += f" ({CREATOR_ORDER_TITLES.get(order, order)})"
    embed = base(title)
    if not items:
        embed.description = "Nenhum criador ainda: preencha o criador das suas obras."
        return embed
    for offset, item in enumerate(items, start=1):
        obras = "1 obra" if item.count == 1 else f"{item.count} obras"
        value = f"{item.type} · {obras} · media {item.average:.1f}"
        if order == "weighted":
            value += f" · ponderada {item.score:.1f}"
        if item.works:
            value += "\n" + ", ".join(w.title for w in item.works)
        embed.add_field(name=f"#{start_index + offset}. {item.name}"[:256], value=value[:1024],
                        inline=False)
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
        embed.add_field(
            name=f"{icon} {badge.name}"[:256], value=(value or "-")[:1024], inline=False
        )

    embed.set_footer(text=f"Pagina {page}/{total_pages}")
    return embed


def _progress_bar(ratio: float, length: int = 10) -> str:
    filled = round(ratio * length)
    return "▰" * filled + "▱" * (length - filled)


def pick_table(details: ExternalDetails) -> discord.Embed:
    """Aparece quando mais de uma tabela aceita esse tipo -- o bot pergunta."""
    embed = base(details.title, "Em qual tabela essa obra entra?")
    if _valid_url(details.image_url):
        embed.set_thumbnail(url=details.image_url)
    return embed


def pick_subcategory(title: str, image_url: str | None, table: Category) -> discord.Embed:
    embed = base(title[:256], f"Quer colocar numa subcategoria de **{table.name}**?")
    if _valid_url(image_url):
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


def _work_fields(
    embed: discord.Embed, work: Work, *, show_raw_score: bool, table: Category | None = None,
) -> discord.Embed:
    if show_raw_score:
        embed.add_field(name="Nota", value=f"{work.score:.1f}")
    embed.add_field(name="Nota final", value=f"{work.final_score:.1f}")
    if work.category_name:
        name = work.category_name
        if work.subcategory_name:
            name += f" > {work.subcategory_name}"
        embed.add_field(name="Tabela", value=name[:1024])
    if work.template:
        embed.add_field(name="Tipo", value=template_label(work.template))
    if work.creator:
        embed.add_field(name="Criador / autor", value=work.creator[:1024])
    if work.release_date:
        embed.add_field(name="Lancamento", value=_br_date(work.release_date))
    if work.time_minutes:
        embed.add_field(name="Duracao", value=f"{work.time_minutes} min")
    for key, label in _FICHA_LABELS:
        value = work.details.get(key)
        if value not in (None, "", 0):
            embed.add_field(name=label, value=str(value)[:1024])
    if table is not None:
        values = work.details.get("fields")
        values = values if isinstance(values, dict) else {}
        for field in table.custom_fields:
            value = values.get(field.id)
            if value is not None and value != "":
                embed.add_field(name=field.name[:256], value=_custom_value(value)[:1024])
    if _valid_url(work.image_url):
        embed.set_thumbnail(url=work.image_url)
    return embed


def _br_date(iso: str) -> str:
    """2008-01-20 -> 20/01/2008; qualquer outra coisa sai como veio."""
    parts = iso[:10].split("-")
    return "/".join(reversed(parts)) if len(parts) == 3 else iso


def _custom_value(value: object) -> str:
    if value is True:
        return "Sim"
    if value is False:
        return "Nao"
    if isinstance(value, str) and len(value) == 10 and value[4] == "-":
        return _br_date(value)
    return str(value)


def work_added(work: Work) -> discord.Embed:
    return _work_fields(base(f"Adicionado: {work.title}"), work, show_raw_score=False)


def work_updated(work: Work) -> discord.Embed:
    """`/manage` mostra a nota crua (o que o usuario digitou), nao so a final --
    e o unico ponto onde a diferenca entre as duas importa pra quem esta editando."""
    return _work_fields(base(f"Atualizado: {work.title}"), work, show_raw_score=True)


def work_refreshed(work: Work) -> discord.Embed:
    return _work_fields(
        base(f"Dados atualizados: {work.title}", "Ficha buscada de novo na origem."),
        work, show_raw_score=True,
    )


def work_detail(work: Work, table: Category | None = None) -> discord.Embed:
    return _work_fields(base(work.title), work, show_raw_score=True, table=table)


def work_removed(title: str) -> discord.Embed:
    return base(f"Removido: {title}")


def _types(table: Category) -> str:
    return ", ".join(template_label(t) for t in table.templates) or "-"


def table_list(tables: list[Category]) -> discord.Embed:
    embed = base("Suas tabelas")
    if not tables:
        embed.description = "Voce ainda nao tem nenhuma tabela. Crie com `/tabela criar`."
        return embed
    for table in tables[:25]:
        value = f"Tipos: {_types(table)}"
        if table.subcategories:
            value += "\nSubcategorias: " + ", ".join(s.name for s in table.subcategories)
        embed.add_field(name=table.name[:256], value=value[:1024], inline=False)
    return embed


def table_created(table: Category) -> discord.Embed:
    embed = base(f"Tabela criada: {table.name}"[:256], f"Tipos: {_types(table)}")
    embed.set_footer(text="Use /tabela editar para subcategorias e campos proprios.")
    return embed


def table_detail(table: Category, work_count: int) -> discord.Embed:
    embed = base(table.name[:256])
    embed.add_field(name="Tipos", value=_types(table)[:1024], inline=False)
    embed.add_field(name="Obras", value=str(work_count))
    embed.add_field(
        name="Subcategorias",
        value=(", ".join(s.name for s in table.subcategories) or "Nenhuma")[:1024],
        inline=False,
    )
    if CUSTOM_TEMPLATE in table.templates:
        embed.add_field(name="Campos proprios", value=_fields_text(table), inline=False)
    return embed


def custom_fields(table: Category) -> discord.Embed:
    embed = base(f"Campos proprios: {table.name}"[:256], _fields_text(table))
    embed.set_footer(text="Ate 5 campos por tabela.")
    return embed


def _fields_text(table: Category) -> str:
    labels = {"TEXT": "texto", "NUMBER": "numero", "DATE": "data", "BOOLEAN": "sim/nao"}
    lines = [f"{f.name} ({labels.get(f.type, f.type)})" for f in table.custom_fields]
    return ("\n".join(lines) or "Nenhum ainda.")[:1024]


def delete_table_warning(table: Category, work_count: int) -> str:
    obras = "1 obra" if work_count == 1 else f"{work_count} obras"
    return (
        f"Excluir a tabela **{table.name}**? As **{obras}** dela tambem sao apagadas, "
        "com notas e takes. Nao da para desfazer."
    )


def error(message: str) -> discord.Embed:
    return discord.Embed(title="Nao deu certo", description=message, color=DANGER)


def not_linked() -> discord.Embed:
    """Unico onboarding do bot: nao existe comando de vinculacao. O vinculo e feito no
    site, pelo botao "Conectar Discord" das Configuracoes (vale para qualquer conta,
    criada com email, Google ou Discord)."""
    return discord.Embed(
        title="Conta nao vinculada",
        description=(
            f"Sua conta do Discord ainda nao esta ligada ao MyRank.\n\n"
            f"Entre em {SITE_URL}, abra **Configuracoes** e clique em "
            f"**Conectar Discord**. Depois e so voltar aqui -- e uma vez so."
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
    if _valid_url(result.poster_url):
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
    if _valid_url(details.image_url):
        embed.set_image(url=details.image_url)
    return embed
