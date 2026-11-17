"""Telas de notificacoes e da IA Insights (embeds e botoes juntos: sao pequenas)."""

from __future__ import annotations

import discord

from myrank.api import MyRankClient
from myrank.insights import Insight, Notification
from ui.embeds import base
from ui.errors import to_embed
from ui.social import TextModal
from ui.views import _check_author, _disable_on_timeout, _truncate

NOTIFICATIONS_PAGE_SIZE = 10
MIN_WORKS_FOR_INSIGHTS = 5  # mesma regra da tela do site
QUESTION_MAX = 500  # o backend corta a pergunta nesse tamanho


def _br_date(iso: str | None) -> str:
    if not iso or len(iso) < 10:
        return ""
    year, month, day = iso[:10].split("-")
    return f"{day}/{month}/{year}"


# ------------------------------------------------------------------ notificacoes

def notifications_embed(items: list[Notification], page: int, unread: int) -> discord.Embed:
    embed = base("Notificacoes")
    if not items:
        embed.description = "Nenhuma notificacao." if page == 0 else "Fim das notificacoes."
        return embed
    lines = []
    for item in items:
        mark = "\U0001f535 " if not item.read else ""
        when = _br_date(item.created_at)
        text = f"{mark}**{item.title}**"
        if item.message:
            text += f" -- {_truncate(item.message, 200)}"
        if when:
            text += f" · {when}"
        lines.append(text)
    embed.description = "\n".join(lines)[:4000]
    footer = f"Pagina {page + 1}"
    if unread:
        footer += f" · {unread} nao lida(s)"
    embed.set_footer(text=footer)
    return embed


class NotificationsView(discord.ui.View):
    message: discord.Message | None = None

    def __init__(
        self, api: MyRankClient, author_id: int, items: list[Notification], *,
        page: int = 0, unread: int = 0,
    ) -> None:
        super().__init__(timeout=300)
        self._api = api
        self._author_id = author_id
        self._items = items
        self._page = page
        self._unread = unread
        self.previous_page.disabled = page == 0
        self.next_page.disabled = len(items) < NOTIFICATIONS_PAGE_SIZE
        self.read_all.disabled = unread == 0

    def embed(self) -> discord.Embed:
        return notifications_embed(self._items, self._page, self._unread)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def on_timeout(self) -> None:
        await _disable_on_timeout(self, self.message)

    async def _load(self, interaction: discord.Interaction, page: int) -> None:
        """A interacao ja foi confirmada; busca a pagina e redesenha a mensagem."""
        try:
            items = await self._api.notifications(
                interaction.user.id, page, NOTIFICATIONS_PAGE_SIZE
            )
            unread = await self._api.unread_notifications(interaction.user.id)
        except Exception as exc:
            await interaction.followup.send(embed=to_embed(exc), ephemeral=True)
            return
        view = NotificationsView(self._api, self._author_id, items, page=page, unread=unread)
        view.message = self.message
        self.stop()
        await interaction.edit_original_response(embed=view.embed(), view=view)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[NotificationsView]
    ) -> None:
        await interaction.response.defer()
        await self._load(interaction, self._page - 1)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[NotificationsView]
    ) -> None:
        await interaction.response.defer()
        await self._load(interaction, self._page + 1)

    @discord.ui.button(label="Marcar todas como lidas", style=discord.ButtonStyle.primary)
    async def read_all(
        self, interaction: discord.Interaction, button: discord.ui.Button[NotificationsView]
    ) -> None:
        await interaction.response.defer()
        try:
            await self._api.read_all_notifications(interaction.user.id)
        except Exception as exc:
            await interaction.followup.send(embed=to_embed(exc), ephemeral=True)
            return
        await self._load(interaction, self._page)


# ------------------------------------------------------------------ IA Insights

def insight_embed(insight: Insight) -> discord.Embed:
    embed = base(_truncate(insight.title, 256), _truncate(insight.summary, 4000) or None)
    for trait in insight.traits[:5]:
        embed.add_field(
            name=_truncate(f"{trait.icon} {trait.label}".strip(), 256),
            value=_truncate(trait.description or "-", 1024), inline=False,
        )
    if insight.contradictions:
        text = "\n".join(f"{icon} {line}".strip() for icon, line in insight.contradictions[:4])
        embed.add_field(name="Contradicoes", value=_truncate(text, 1024), inline=False)
    if insight.taste:
        lines = []
        for piece in insight.taste[:8]:
            if piece.average is not None:
                count = f" · {piece.count} obra(s)" if piece.count else ""
                lines.append(f"{piece.name}: media {piece.average:.1f}{count}")
            elif piece.percent is not None:
                lines.append(f"{piece.name}: {piece.percent}%")
        if lines:
            embed.add_field(name="Perfil de gosto", value=_truncate("\n".join(lines), 1024),
                            inline=False)
    for rec in insight.recommendations[:3]:
        year = f" ({rec.year})" if rec.year else ""
        category = f" · {rec.category}" if rec.category else ""
        embed.add_field(name=_truncate(f"Recomendacao: {rec.title}{year}{category}", 256),
                        value=_truncate(rec.reason or "-", 1024), inline=False)
    poster = next((r.poster_url for r in insight.recommendations
                   if r.poster_url and r.poster_url.startswith("https://")), None)
    if poster:
        embed.set_thumbnail(url=poster)
    embed.set_footer(text=_insight_footer(insight))
    return embed


def _insight_footer(insight: Insight) -> str:
    parts = [f"{insight.work_count} obra(s) analisada(s)"]
    when = _br_date(insight.generated_at)
    if when:
        parts.append(f"gerada em {when}")
    if insight.daily_limit:
        parts.append(f"mensagens de IA hoje: {insight.daily_remaining}/{insight.daily_limit}")
    return " · ".join(parts)


def chat_embed(insight: Insight, last: int = 6) -> discord.Embed:
    """As ultimas mensagens da conversa com a IA (o Discord nao comporta todas)."""
    embed = base(_truncate(f"Conversa: {insight.title}", 256))
    messages = insight.chat[-last:]
    if not messages:
        embed.description = "Nenhuma pergunta ainda. Use o botao Perguntar."
    budget = 5500
    for message in messages:
        name = "Voce" if message.is_user else "IA"
        value = _truncate(message.content or "-", min(1024, max(budget, 50)))
        budget -= len(value)
        embed.add_field(name=name, value=value, inline=False)
        if budget <= 0:
            break
    embed.set_footer(text=_insight_footer(insight))
    return embed


class InsightView(discord.ui.View):
    """Botoes da analise. "Gerar de novo" so aparece quando o bot sabe que obras foram
    usadas (veio do /insights gerar); a analise mais recente nao diz isso."""

    def __init__(
        self, api: MyRankClient, author_id: int, insight: Insight,
        work_ids: list[int] | None = None, *, chat: bool = False,
    ) -> None:
        super().__init__(timeout=900)
        self._api = api
        self._author_id = author_id
        self._insight = insight
        self._work_ids = work_ids
        if work_ids is None:
            self.remove_item(self.regenerate)
        no_budget = insight.daily_limit > 0 and insight.daily_remaining <= 0
        self.ask.disabled = no_budget
        self.regenerate.disabled = no_budget
        if chat:
            self.remove_item(self.show_chat)
        else:
            self.remove_item(self.show_analysis)
            if not insight.chat:
                self.remove_item(self.show_chat)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    def _redraw(self, insight: Insight, *, chat: bool) -> tuple[discord.Embed, InsightView]:
        self.stop()
        view = InsightView(self._api, self._author_id, insight, self._work_ids, chat=chat)
        return (chat_embed(insight) if chat else insight_embed(insight)), view

    @discord.ui.button(label="Perguntar", style=discord.ButtonStyle.success)
    async def ask(
        self, interaction: discord.Interaction, button: discord.ui.Button[InsightView]
    ) -> None:
        async def action(inner: discord.Interaction, question: str) -> None:
            await inner.response.defer()
            try:
                insight = await self._api.ask_insight(inner.user.id, self._insight.id, question)
            except Exception as exc:
                await inner.followup.send(embed=to_embed(exc), ephemeral=True)
                return
            embed, view = self._redraw(insight, chat=True)
            await inner.edit_original_response(embed=embed, view=view)

        await interaction.response.send_modal(TextModal(
            "Perguntar a IA", "Sua pergunta sobre a analise", action, max_length=QUESTION_MAX
        ))

    @discord.ui.button(label="Ver conversa", style=discord.ButtonStyle.secondary)
    async def show_chat(
        self, interaction: discord.Interaction, button: discord.ui.Button[InsightView]
    ) -> None:
        embed, view = self._redraw(self._insight, chat=True)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Ver analise", style=discord.ButtonStyle.secondary)
    async def show_analysis(
        self, interaction: discord.Interaction, button: discord.ui.Button[InsightView]
    ) -> None:
        embed, view = self._redraw(self._insight, chat=False)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Gerar de novo", style=discord.ButtonStyle.primary)
    async def regenerate(
        self, interaction: discord.Interaction, button: discord.ui.Button[InsightView]
    ) -> None:
        assert self._work_ids is not None
        await interaction.response.defer()
        try:
            insight = await self._api.generate_insight(
                interaction.user.id, self._work_ids, refresh=True
            )
        except Exception as exc:
            await interaction.followup.send(embed=to_embed(exc), ephemeral=True)
            return
        embed, view = self._redraw(insight, chat=False)
        await interaction.edit_original_response(embed=embed, view=view)
