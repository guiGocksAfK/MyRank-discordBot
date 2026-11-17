"""/notificacoes e /insights (gerar, ver, perguntar).

As duas coisas respondem so para a pessoa: notificacao diz quem fez o que, e a
analise de IA e sobre o gosto dela (como no site, onde a tela e so dela).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ui import embeds
from ui.errors import guarded
from ui.insights import (
    MIN_WORKS_FOR_INSIGHTS,
    NOTIFICATIONS_PAGE_SIZE,
    QUESTION_MAX,
    InsightView,
    NotificationsView,
    chat_embed,
    insight_embed,
)

log = logging.getLogger(__name__)

NO_INSIGHT = "Voce ainda nao gerou nenhuma analise. Use `/insights gerar`."


class NotificationsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="notificacoes", description="Suas notificacoes do MyRank."
    )
    @guarded(ephemeral=True)
    async def notificacoes(self, interaction: discord.Interaction) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        items = await api.notifications(interaction.user.id, 0, NOTIFICATIONS_PAGE_SIZE)
        unread = await api.unread_notifications(interaction.user.id)
        view = NotificationsView(api, interaction.user.id, items, unread=unread)
        view.message = await interaction.followup.send(
            embed=view.embed(), view=view, ephemeral=True, wait=True
        )


class InsightsCog(commands.GroupCog, group_name="insights",
                  group_description="Analise do seu gosto feita por IA."):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(  # type: ignore[arg-type]
        name="gerar", description="Analisa o seu gosto pelas suas obras (todas ou uma tabela)."
    )
    @app_commands.describe(tabela="So uma tabela (autocompletar). Sem ela, todas as obras.")
    @guarded(ephemeral=True)
    async def gerar(self, interaction: discord.Interaction, tabela: int | None = None) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        works = await api.list_works(interaction.user.id, tabela)
        if len(works) < MIN_WORKS_FOR_INSIGHTS:
            falta = MIN_WORKS_FOR_INSIGHTS - len(works)
            await interaction.followup.send(embed=embeds.error(
                f"A analise precisa de pelo menos {MIN_WORKS_FOR_INSIGHTS} obras. "
                f"Faltam {falta}."
            ), ephemeral=True)
            return
        work_ids = [work.id for work in works[:500]]
        insight = await api.generate_insight(interaction.user.id, work_ids)
        await interaction.followup.send(
            embed=insight_embed(insight),
            view=InsightView(api, interaction.user.id, insight, work_ids), ephemeral=True,
        )

    @gerar.autocomplete("tabela")
    async def gerar_tabela_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        try:
            tables = await self.bot.api.get_categories(interaction.user.id)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar tabelas para autocomplete de /insights gerar")
            return []
        current_norm = current.casefold()
        return [
            app_commands.Choice(name=t.name[:100], value=t.id)
            for t in tables if current_norm in t.name.casefold()
        ][:25]

    @app_commands.command(  # type: ignore[arg-type]
        name="ver", description="Abre a sua analise mais recente."
    )
    @guarded(ephemeral=True)
    async def ver(self, interaction: discord.Interaction) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        insight = await api.latest_insight(interaction.user.id)
        if insight is None:
            await interaction.followup.send(embed=embeds.error(NO_INSIGHT), ephemeral=True)
            return
        await interaction.followup.send(
            embed=insight_embed(insight), view=InsightView(api, interaction.user.id, insight),
            ephemeral=True,
        )

    @app_commands.command(  # type: ignore[arg-type]
        name="perguntar", description="Pergunta algo a IA sobre a sua analise mais recente."
    )
    @app_commands.describe(pergunta="Ate 500 caracteres. Gasta 1 mensagem de IA do dia.")
    @guarded(ephemeral=True)
    async def perguntar(self, interaction: discord.Interaction, pergunta: str) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        pergunta = pergunta.strip()[:QUESTION_MAX]
        if not pergunta:
            await interaction.followup.send(embed=embeds.error("Escreva uma pergunta."),
                                            ephemeral=True)
            return
        latest = await api.latest_insight(interaction.user.id)
        if latest is None:
            await interaction.followup.send(embed=embeds.error(NO_INSIGHT), ephemeral=True)
            return
        insight = await api.ask_insight(interaction.user.id, latest.id, pergunta)
        await interaction.followup.send(
            embed=chat_embed(insight),
            view=InsightView(api, interaction.user.id, insight, chat=True),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NotificationsCog(bot))
    await bot.add_cog(InsightsCog(bot))
