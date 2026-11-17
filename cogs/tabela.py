"""/tabela listar | criar | editar -- as tabelas da pessoa, como na tela do site."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ui import embeds
from ui.errors import guarded
from ui.tables import CreateTableView, TablePanel

log = logging.getLogger(__name__)

MAX_NAME = 60  # mesmo limite do backend


class TabelaCog(commands.GroupCog, group_name="tabela", group_description="Suas tabelas."):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(  # type: ignore[arg-type]  # mypy nao resolve Concatenate com self de Cog
        name="listar", description="Mostra suas tabelas, com tipos e subcategorias."
    )
    @guarded()
    async def listar(self, interaction: discord.Interaction) -> None:
        tables = await self.bot.api.get_categories(interaction.user.id)  # type: ignore[attr-defined]
        await interaction.followup.send(embed=embeds.table_list(tables))

    @app_commands.command(  # type: ignore[arg-type]
        name="criar", description="Cria uma tabela nova."
    )
    @app_commands.describe(nome="Nome da tabela (pode ter emoji).")
    @guarded()
    async def criar(self, interaction: discord.Interaction, nome: str) -> None:
        # Sem app_commands.Range: o @guarded troca o modulo em que a anotacao e lida,
        # e ela deixa de ser encontrada. O backend confere o mesmo limite de novo.
        nome = nome.strip()
        if not nome or len(nome) > MAX_NAME:
            await interaction.followup.send(
                embed=embeds.error(f"O nome precisa ter de 1 a {MAX_NAME} caracteres.")
            )
            return
        view = CreateTableView(self.bot.api, interaction.user.id, nome)  # type: ignore[attr-defined]
        view.message = await interaction.followup.send(
            f"Tabela **{nome}**: que tipos de obra entram nela?", view=view, wait=True
        )

    @app_commands.command(  # type: ignore[arg-type]
        name="editar", description="Renomeia, muda tipos, subcategorias e campos, ou exclui."
    )
    @app_commands.describe(tabela="Qual tabela (autocompletar).")
    @guarded()
    async def editar(self, interaction: discord.Interaction, tabela: int) -> None:
        api = self.bot.api  # type: ignore[attr-defined]
        tables = await api.get_categories(interaction.user.id)
        table = next((t for t in tables if t.id == tabela), None)
        if table is None:
            await interaction.followup.send(
                embed=embeds.error("Essa tabela nao existe mais -- rode o comando de novo.")
            )
            return
        works = await api.list_works(interaction.user.id, table.id)
        panel = TablePanel(api, interaction.user.id, table, len(works))
        panel.message = await interaction.followup.send(
            embed=panel.embed(), view=panel, wait=True
        )

    @editar.autocomplete("tabela")
    async def editar_tabela_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        try:
            tables = await self.bot.api.get_categories(interaction.user.id)  # type: ignore[attr-defined]
        except Exception:
            log.exception("Falha ao buscar tabelas para autocomplete de /tabela editar")
            return []
        current_norm = current.casefold()
        return [
            app_commands.Choice(name=table.name[:100], value=table.id)
            for table in tables
            if current_norm in table.name.casefold()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TabelaCog(bot))
