"""Tela do /config: as configuracoes da conta, como na pagina do site.

Cada mudanca salva na hora (como no site) e a tela e redesenhada com a conta que o
backend devolveu. O modo escuro fica de fora: ele so existe no navegador.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import discord

from myrank.account import (
    DM_POLICIES,
    LANGUAGES,
    NOTIFICATION_GROUPS,
    RANKINGS_VIEWS,
    Account,
    label_of,
    profile_changes,
)
from myrank.api import MyRankClient
from ui.embeds import base
from ui.errors import to_embed
from ui.views import _check_author

PROVIDERS = {"LOCAL": "Email e senha", "GOOGLE": "Google", "DISCORD": "Discord"}


def config_embed(account: Account) -> discord.Embed:
    embed = base("Configuracoes", f"Conta **{account.username}**")
    if account.avatar_url and account.avatar_url.startswith("https://"):
        embed.set_thumbnail(url=account.avatar_url)
    embed.add_field(name="Bio", value=(account.bio or "-")[:1024], inline=False)
    embed.add_field(name="Perfil", value="Publico" if account.is_public else "Privado")
    embed.add_field(name="Idioma", value=label_of(LANGUAGES, account.language))
    embed.add_field(name="Mensagens de", value=label_of(DM_POLICIES, account.dm_policy))
    muted = ", ".join(label_of(NOTIFICATION_GROUPS, g) for g in account.muted_notifications)
    embed.add_field(name="Avisos silenciados", value=muted or "Nenhum", inline=False)
    embed.add_field(name="Nota ponderada", value="Ligada" if account.weighted_by_default
                    else "Desligada")
    embed.add_field(name="Rankings em", value=label_of(RANKINGS_VIEWS, account.rankings_view))
    embed.add_field(name="Como voce entra", value=PROVIDERS.get(account.auth_provider,
                                                                account.auth_provider))
    embed.set_footer(text="Senha, sair dos aparelhos e excluir a conta: so no site.")
    return embed


class _Select(discord.ui.Select["ConfigView"]):
    def __init__(
        self, placeholder: str, options: list[discord.SelectOption], row: int,
        on_pick: Callable[[discord.Interaction, list[str]], Awaitable[None]],
        *, min_values: int = 1, max_values: int = 1,
    ) -> None:
        super().__init__(placeholder=placeholder, options=options, row=row,
                         min_values=min_values, max_values=max_values)
        self._on_pick = on_pick

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._on_pick(interaction, list(self.values))


def _options(choices: tuple[tuple[str, str], ...], current: str) -> list[discord.SelectOption]:
    return [discord.SelectOption(label=label, value=value, default=value == current)
            for value, label in choices]


class ConfigView(discord.ui.View):
    def __init__(self, api: MyRankClient, author_id: int, account: Account) -> None:
        super().__init__(timeout=600)
        self._api = api
        self._author_id = author_id
        self.account = account
        self.weighted.label = "Nota ponderada: " + (
            "ligada" if account.weighted_by_default else "desligada")
        self.view_mode.label = "Rankings em: " + label_of(RANKINGS_VIEWS, account.rankings_view)

        privacy = [("public", "Perfil publico"), ("private", "Perfil privado")]
        self.add_item(_Select(
            "Privacidade", _options(tuple(privacy), "public" if account.is_public else "private"),
            1, lambda i, v: self.save(i, {"isPublic": v[0] == "public"}),
        ))
        self.add_item(_Select(
            "Idioma", _options(LANGUAGES, account.language), 2,
            lambda i, v: self.save(i, {"language": v[0]}),
        ))
        self.add_item(_Select(
            "Quem pode te mandar mensagem", _options(DM_POLICIES, account.dm_policy), 3,
            lambda i, v: self.save(i, {"dmPolicy": v[0]}),
        ))
        muted = [discord.SelectOption(label=label, value=value,
                                      default=value in account.muted_notifications)
                 for value, label in NOTIFICATION_GROUPS]
        self.add_item(_Select(
            "Avisos silenciados (nenhum = recebe tudo)", muted, 4,
            lambda i, v: self.save(i, {"mutedNotifications": v}),
            min_values=0, max_values=len(muted),
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def save(self, interaction: discord.Interaction, changes: dict[str, Any]) -> None:
        """Salva e redesenha esta mensagem com a conta que o backend devolveu."""
        await interaction.response.defer()
        if not changes:
            return
        try:
            account = await self._api.update_me(interaction.user.id, changes)
        except Exception as exc:
            await interaction.followup.send(embed=to_embed(exc), ephemeral=True)
            return
        self.stop()
        await interaction.edit_original_response(
            embed=config_embed(account), view=ConfigView(self._api, self._author_id, account)
        )

    @discord.ui.button(label="Editar perfil", style=discord.ButtonStyle.primary, row=0)
    async def edit_profile(
        self, interaction: discord.Interaction, button: discord.ui.Button[ConfigView]
    ) -> None:
        await interaction.response.send_modal(ProfileModal(self))

    @discord.ui.button(label="Nota ponderada", style=discord.ButtonStyle.secondary, row=0)
    async def weighted(
        self, interaction: discord.Interaction, button: discord.ui.Button[ConfigView]
    ) -> None:
        await self.save(interaction, {"weightedByDefault": not self.account.weighted_by_default})

    @discord.ui.button(label="Rankings em", style=discord.ButtonStyle.secondary, row=0)
    async def view_mode(
        self, interaction: discord.Interaction, button: discord.ui.Button[ConfigView]
    ) -> None:
        other = "GRID" if self.account.rankings_view == "LIST" else "LIST"
        await self.save(interaction, {"rankingsView": other})


class ProfileModal(discord.ui.Modal):
    """Nome de usuario, bio e foto. So o que mudar e enviado; bio e foto vazias apagam."""

    def __init__(self, config: ConfigView) -> None:
        super().__init__(title="Editar perfil")
        self._config = config
        account = config.account
        self.username: discord.ui.TextInput[ProfileModal] = discord.ui.TextInput(
            label="Nome de usuario", default=account.username[:50], min_length=3, max_length=50)
        self.bio: discord.ui.TextInput[ProfileModal] = discord.ui.TextInput(
            label="Bio", default=account.bio[:500] if account.bio else None, required=False,
            max_length=500, style=discord.TextStyle.paragraph)
        self.avatar: discord.ui.TextInput[ProfileModal] = discord.ui.TextInput(
            label="Foto (link https da imagem)",
            default=account.avatar_url[:1000] if account.avatar_url else None, required=False,
            max_length=1000, placeholder="https://...")
        for item in (self.username, self.bio, self.avatar):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        username = self.username.value.strip()
        if len(username) < 3:
            await interaction.response.send_message(
                "O nome de usuario precisa ter de 3 a 50 caracteres.", ephemeral=True)
            return
        avatar = self.avatar.value.strip()
        if avatar and not avatar.startswith("https://"):
            await interaction.response.send_message(
                "A foto precisa ser um link comecando com https://.", ephemeral=True)
            return
        changes = profile_changes(
            self._config.account, username=username,
            bio=self.bio.value.strip(), avatar_url=avatar,
        )
        await self._config.save(interaction, changes)
