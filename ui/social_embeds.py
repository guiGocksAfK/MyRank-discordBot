"""Embeds da area social: perfis, listas de pessoas, feed, takes e comentarios."""

from __future__ import annotations

import discord

from myrank.social import (
    REACTIONS,
    FeedItem,
    SocialProfile,
    SocialSummary,
    SocialUser,
    TakeComment,
)
from ui.embeds import base

# Chaves de `breakdown` e `WorkMini.type` (TableTemplate.type() no backend).
TYPE_LABELS = {
    "filme": "Filmes", "serie": "Séries", "jogo": "Jogos", "livro": "Livros",
    "anime": "Animes", "musica": "Músicas", "album": "Álbuns", "manga": "Mangás",
    "outro": "Outros",
}

FEED_EMPTY = "Nada por aqui ainda. Siga pessoas ou escreva um take com `/take`."


def _avatar(embed: discord.Embed, url: str | None) -> None:
    if url and url.startswith("https://"):
        embed.set_thumbnail(url=url)


def _br_date(iso: str | None) -> str:
    if not iso or len(iso) < 10:
        return ""
    year, month, day = iso[:10].split("-")
    return f"{day}/{month}/{year}"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summary_fields(embed: discord.Embed, summary: SocialSummary) -> discord.Embed:
    embed.add_field(name="Seguidores", value=str(summary.followers))
    embed.add_field(name="Seguindo", value=str(summary.following))
    if summary.pending_follow_requests:
        embed.add_field(
            name="Pedidos para seguir",
            value=f"{summary.pending_follow_requests} -- veja em `/social pedidos`",
        )
    return embed


def follow_label(profile: SocialProfile | SocialUser) -> str:
    """O texto do botao diz o que o clique vai fazer, como no site."""
    if profile.following:
        return "Deixar de seguir"
    if profile.requested:
        return "Cancelar pedido"
    return "Seguir" if profile.is_public else "Pedir para seguir"


def social_profile(profile: SocialProfile) -> discord.Embed:
    embed = base(profile.username[:256], _clip(profile.bio, 1000) if profile.bio else None)
    _avatar(embed, profile.avatar_url)
    embed.add_field(name="Obras", value=str(profile.works_count))
    embed.add_field(name="Media", value=f"{profile.avg_score:.1f}" if profile.works_count else "-")
    embed.add_field(name="Seguidores", value=str(profile.follower_count))
    embed.add_field(name="Seguindo", value=str(profile.following_count))
    status = []
    if profile.follows_you:
        status.append("Segue voce")
    if profile.requested:
        status.append("Pedido enviado")
    if status:
        embed.add_field(name="Status", value=" · ".join(status))

    if profile.locked:
        embed.add_field(
            name="\U0001f512 Perfil privado",
            value="Peca para seguir para ver obras, conquistas e takes.",
            inline=False,
        )
        return embed

    if profile.top:
        lines = [
            f"{i}. {_clip(w.title, 60)}" + (f" -- {w.score:.1f}" if w.score is not None else "")
            for i, w in enumerate(profile.top[:10], start=1)
        ]
        embed.add_field(name="Top", value="\n".join(lines)[:1024], inline=False)
    if profile.breakdown:
        text = " · ".join(f"{TYPE_LABELS.get(k, k)} {v}" for k, v in profile.breakdown)
        embed.add_field(name="Por tipo", value=text[:1024], inline=False)
    if profile.badges:
        text = " ".join(f"{b.icon or ''} {b.name}".strip() for b in profile.badges[:12])
        embed.add_field(name="Conquistas", value=text[:1024], inline=False)
    return embed


def profile_works(profile: SocialProfile, start: int, page: int, total: int) -> discord.Embed:
    embed = base(f"Obras de {profile.username}"[:256])
    works = profile.works[start:start + 15]
    lines = [
        f"{start + i}. {_clip(w.title, 70)}" + (f" -- {w.score:.1f}" if w.score is not None else "")
        for i, w in enumerate(works, start=1)
    ]
    embed.description = "\n".join(lines) or "Nenhuma obra."
    embed.set_footer(text=f"Pagina {page}/{total}")
    return embed


def people(title: str, users: list[SocialUser], start: int, page: int, total: int,
           empty: str) -> discord.Embed:
    embed = base(title)
    if not users:
        embed.description = empty
        return embed
    for user in users:
        name = user.username + (" · segue voce" if user.follows_you else "")
        parts = [f"{user.works_count} obras"]
        if user.works_count:
            parts.append(f"media {user.avg_score:.1f}")
        if user.match_pct is not None:
            parts.append(f"gosto {user.match_pct}% parecido")
        elif user.shared_count:
            parts.append(f"{user.shared_count} obras em comum")
        if not user.is_public:
            parts.append("\U0001f512 privado")
        value = " · ".join(parts)
        if user.fight_title and user.fight_mine is not None and user.fight_theirs is not None:
            value += (f"\nBrigam em **{_clip(user.fight_title, 60)}** "
                      f"({user.fight_mine:.1f} x {user.fight_theirs:.1f})")
        if user.bio:
            value += f"\n{_clip(user.bio, 120)}"
        embed.add_field(name=_clip(name, 256), value=value[:1024], inline=False)
    embed.set_footer(text=f"Pagina {page}/{total}")
    return embed


def reactions_text(item: FeedItem) -> str:
    return " · ".join(
        f"{label} {item.reactions.count(kind)}" + (" (voce)" if item.reactions.mine == kind else "")
        for kind, label in REACTIONS
    )


def feed(items: list[FeedItem], page: int, following_only: bool) -> discord.Embed:
    title = "Feed -- so quem eu sigo" if following_only else "Feed"
    embed = base(title)
    if not items:
        embed.description = FEED_EMPTY if page == 0 else "Fim do feed."
        return embed
    shown = items[:20]  # um embed aceita 25 campos; sobra folga para o tamanho total
    for item in shown:
        when = _br_date(item.created_at)
        if item.is_take and item.work is not None:
            score = f" ({item.score:.1f})" if item.score is not None else ""
            name = f"{item.actor.username} sobre {item.work.title}{score}"
            value = (f"“{_clip(item.take_text or '', 280)}”\n"
                     f"{reactions_text(item)} · {item.comment_count} comentario(s)")
        else:
            titles = ", ".join(_clip(w.title, 40) for w in item.works[:4])
            extra = item.work_count - min(len(item.works), 4)
            name = f"{item.actor.username} avaliou {item.work_count} obra(s)"
            value = titles + (f" e mais {extra}" if extra > 0 else "")
        embed.add_field(name=_clip(f"{name} · {when}" if when else name, 256),
                        value=(value or "-")[:1024], inline=False)
    if len(items) > len(shown):
        embed.description = "Alguns itens desta pagina ficaram de fora; veja a proxima."
    embed.set_footer(text=f"Pagina {page + 1} · Abra um take no menu para reagir e comentar")
    return embed


def take(item: FeedItem) -> discord.Embed:
    work = item.work.title if item.work else "?"
    embed = base(_clip(f"{item.actor.username} sobre {work}", 256),
                 _clip(item.take_text or "", 4000))
    if item.score is not None:
        embed.add_field(name="Nota", value=f"{item.score:.1f}")
    embed.add_field(name="Reacoes", value=reactions_text(item), inline=False)
    embed.add_field(name="Comentarios", value=str(item.comment_count))
    if item.work and item.work.image_url:
        embed.set_thumbnail(url=item.work.image_url)
    footer = _br_date(item.created_at) + (" · editado" if item.take_edited else "")
    if footer.strip(" ·"):
        embed.set_footer(text=footer.strip(" ·"))
    return embed


def comments(item: FeedItem, roots: list[TakeComment]) -> discord.Embed:
    work = item.work.title if item.work else "?"
    embed = base(_clip(f"Comentarios: {item.actor.username} sobre {work}", 256))
    if not roots:
        embed.description = "Ninguem comentou ainda."
        return embed
    lines: list[str] = []
    for root in roots:
        lines.append(_comment_line(root, indent=""))
        lines.extend(_comment_line(reply, indent="↳ ") for reply in root.replies)
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "\n…"
    embed.description = text
    return embed


def _comment_line(comment: TakeComment, indent: str) -> str:
    edited = " (editado)" if comment.edited else ""
    return f"{indent}**{comment.author.username}**: {_clip(comment.text, 300)}{edited}"


def take_posted(item: FeedItem) -> discord.Embed:
    embed = take(item)
    embed.title = _clip(f"Take publicado: {item.work.title if item.work else ''}", 256)
    return embed
