"""/add e /add-manual -- as duas formas de cadastrar uma obra, como no site.

/add: busca externa nas 8 midias, escolha da tabela (pelo tipo) e da subcategoria, e
nota. A obra e gravada como o site grava: com template e ficha.
/add-manual: obra digitada, para o que nao existe em nenhuma API (ou tabela
Personalizado).
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from myrank.media import CUSTOM_LABEL, CUSTOM_TEMPLATE, MEDIA_TYPES, by_template, template_label
from ui import embeds
from ui.errors import guarded
from ui.views import ManualFlow, MediaResultView

log = logging.getLogger(__name__)

MEDIA_CHOICES = [
    app_commands.Choice(name=media.label, value=media.template) for media in MEDIA_TYPES
]
TEMPLATE_CHOICES = [*MEDIA_CHOICES, app_commands.Choice(name=CUSTOM_LABEL, value=CUSTOM_TEMPLATE)]


class AddCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="add", description="Adiciona uma obra avaliada ao seu MyRank."
    )
    @app_commands.describe(midia="Tipo de midia.", busca="Titulo ou parte do titulo.")
    @app_commands.choices(midia=MEDIA_CHOICES)
    @guarded()
    async def add(self, interaction: discord.Interaction, midia: str, busca: str) -> None:
        media_type = by_template(midia)
        api = self.bot.api  # type: ignore[attr-defined]
        results = await api.external_search(interaction.user.id, media_type.endpoint, busca)

        if not results:
            await interaction.followup.send(
                f"Nenhum resultado para **{busca}**. Tente outro termo, ou cadastre "
                "a obra a mao com `/add-manual`."
            )
            return

        view = MediaResultView(api, interaction.user.id, media_type, results)
        view.message = await interaction.followup.send(
            f"Encontrei {len(results)} resultado(s) para **{busca}**. Qual e o certo?",
            embed=view.embed(), view=view, wait=True,
        )

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="add-manual", description="Cadastra uma obra digitando os dados (sem busca)."
    )
    @app_commands.describe(
        tabela="Em qual tabela a obra entra (autocompletar).",
        tipo="So precisa se a tabela aceitar mais de um tipo.",
    )
    @app_commands.choices(tipo=TEMPLATE_CHOICES)
    @guarded()
    async def add_manual(
        self, interaction: discord.Interaction, tabela: int, tipo: str | None = None
    ) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        categories = await api.get_categories(interaction.user.id)
        table = next((c for c in categories if c.id == tabela), None)
        if table is None:
            await interaction.followup.send(
                embed=embeds.error("Essa tabela nao existe mais -- rode o comando de novo.")
            )
            return
        if not table.templates:
            await interaction.followup.send(
                embed=embeds.error("Essa tabela nao tem nenhum tipo definido.")
            )
            return

        if tipo is not None and tipo not in table.templates:
            aceitos = ", ".join(template_label(t) for t in table.templates)
            await interaction.followup.send(
                embed=embeds.error(f"**{table.name}** so aceita: {aceitos}.")
            )
            return
        template = tipo or (table.templates[0] if len(table.templates) == 1 else None)

        embed, view = ManualFlow(api, interaction.user.id, table, template).first_step()
        await interaction.followup.send(embed=embed, view=view)

    @add_manual.autocomplete("tabela")
    async def add_manual_tabela_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        try:
            categories = await self.bot.api.get_categories(interaction.user.id)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar tabelas para autocomplete de /add-manual")
            return []
        current_norm = current.casefold()
        return [
            app_commands.Choice(name=category.name[:100], value=category.id)
            for category in categories
            if current_norm in category.name.casefold()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AddCog(bot))
