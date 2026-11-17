"""Telas da area social: perfil de outra pessoa, listas de pessoas, pedidos para
seguir, feed, take e comentarios.

Toda mudanca (seguir, reagir, comentar) passa pela API e a tela e redesenhada com
o que o backend devolveu. Quem pode ver o que (perfil trancado, take de perfil
privado) e decidido la: o bot so mostra.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable

import discord

from myrank.api import MyRankClient
from myrank.social import REACTIONS, FeedItem, SocialProfile, SocialUser, TakeComment
from ui import social_embeds as se
from ui.errors import to_embed
from ui.views import (
    ChoiceSelect,
    ConfirmView,
    PaginatedView,
    _check_author,
    _disable_on_timeout,
    _truncate,
)

TextAction = Callable[[discord.Interaction, str], Awaitable[None]]

FEED_PAGE_SIZE = 8
PEOPLE_PAGE_SIZE = 8
WORKS_PAGE_SIZE = 15


class TextModal(discord.ui.Modal):
    """Um campo de texto longo (take, comentario). Quem chama decide o que fazer."""

    def __init__(
        self, title: str, label: str, action: TextAction, *,
        default: str | None = None, min_length: int = 1, max_length: int = 500,
    ) -> None:
        super().__init__(title=_truncate(title, 45))
        self._action = action
        self._min_length = min_length
        self.text: discord.ui.TextInput[TextModal] = discord.ui.TextInput(
            label=label, style=discord.TextStyle.paragraph,
            default=default[:max_length] if default else None,
            min_length=min_length, max_length=max_length,
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = self.text.value.strip()
        if len(text) < self._min_length:
            await interaction.response.send_message(
                f"O texto precisa ter pelo menos {self._min_length} caractere(s).", ephemeral=True
            )
            return
        await self._action(interaction, text)


async def _fail(interaction: discord.Interaction, exc: Exception) -> None:
    """Erro depois do defer: avisa so para a pessoa, sem apagar a tela."""
    await interaction.followup.send(embed=to_embed(exc), ephemeral=True)


# ------------------------------------------------------------------ perfil

class ProfileView(discord.ui.View):
    message: discord.Message | None = None

    def __init__(self, api: MyRankClient, author_id: int, profile: SocialProfile) -> None:
        super().__init__(timeout=300)
        self._api = api
        self._author_id = author_id
        self._profile = profile
        self.follow.label = se.follow_label(profile)
        self.follow.style = (
            discord.ButtonStyle.secondary if profile.following or profile.requested
            else discord.ButtonStyle.success
        )
        if profile.locked or not profile.works:
            self.remove_item(self.works)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def on_timeout(self) -> None:
        await _disable_on_timeout(self, self.message)

    @discord.ui.button(label="Seguir", style=discord.ButtonStyle.success)
    async def follow(
        self, interaction: discord.Interaction, button: discord.ui.Button[ProfileView]
    ) -> None:
        await interaction.response.defer()
        try:
            await self._api.toggle_follow(interaction.user.id, self._profile.id)
            profile = await self._api.profile(interaction.user.id, self._profile.id)
        except Exception as exc:
            await _fail(interaction, exc)
            return
        self.stop()
        new_view = ProfileView(self._api, self._author_id, profile)
        new_view.message = self.message
        await interaction.edit_original_response(
            embed=se.social_profile(profile), view=new_view,
        )

    @discord.ui.button(label="Ver obras", style=discord.ButtonStyle.primary)
    async def works(
        self, interaction: discord.Interaction, button: discord.ui.Button[ProfileView]
    ) -> None:
        view = ProfileWorksView(self._profile, self._author_id)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)


class ProfileWorksView(PaginatedView):
    def __init__(self, profile: SocialProfile, author_id: int) -> None:
        super().__init__(len(profile.works), author_id, page_size=WORKS_PAGE_SIZE)
        self._profile = profile

    def embed(self) -> discord.Embed:
        return se.profile_works(self._profile, self.page_start, self.current_page,
                                self.total_pages)


async def open_profile(
    interaction: discord.Interaction, api: MyRankClient, user_id: int, *, ephemeral: bool,
) -> None:
    """Abre o perfil numa mensagem nova. A interacao ainda nao foi respondida."""
    await interaction.response.defer(thinking=True, ephemeral=ephemeral)
    try:
        profile = await api.profile(interaction.user.id, user_id)
    except Exception as exc:
        await interaction.edit_original_response(embed=to_embed(exc))
        return
    await interaction.edit_original_response(
        embed=se.social_profile(profile),
        view=ProfileView(api, interaction.user.id, profile),
    )


# ------------------------------------------------------------------ listas de pessoas

class PeopleView(PaginatedView):
    """Lista paginada com um menu para abrir o perfil de alguem da pagina.

    Em `requests=True` (pedidos para seguir), o menu abre Aprovar/Recusar.
    """

    def __init__(
        self, api: MyRankClient, author_id: int, title: str, users: list[SocialUser],
        *, empty: str, requests: bool = False,
    ) -> None:
        super().__init__(len(users), author_id, page_size=PEOPLE_PAGE_SIZE)
        self._api = api
        self._title = title
        self._users = users
        self._empty = empty
        self._requests = requests
        self._select: ChoiceSelect | None = None
        self._refresh_select()
        if not users:
            self.remove_item(self.previous_page)
            self.remove_item(self.next_page)

    def embed(self) -> discord.Embed:
        return se.people(self._title, self._users[self.page_slice], self.page_start,
                         self.current_page, self.total_pages, self._empty)

    def _refresh_select(self) -> None:
        if self._select is not None:
            self.remove_item(self._select)
            self._select = None
        page = self._users[self.page_slice]
        if not page:
            return
        options = [
            discord.SelectOption(label=_truncate(u.username, 100), value=str(u.id))
            for u in page
        ]
        placeholder = "Responder a um pedido..." if self._requests else "Abrir o perfil de..."
        self._select = ChoiceSelect(options, placeholder, self._on_pick)
        self.add_item(self._select)

    def _update_buttons(self) -> None:
        super()._update_buttons()
        if hasattr(self, "_users"):
            self._refresh_select()

    async def _on_pick(self, interaction: discord.Interaction, value: str) -> None:
        user = next(u for u in self._users if str(u.id) == value)
        if not self._requests:
            await open_profile(interaction, self._api, user.id, ephemeral=True)
            return
        await interaction.response.send_message(
            f"**{user.username}** quer te seguir.",
            view=FollowRequestView(self, user), ephemeral=True,
        )

    async def request_answered(self, user: SocialUser) -> None:
        """Tira a pessoa da lista depois de aprovar ou recusar."""
        self._users = [u for u in self._users if u.id != user.id]
        self._total_items = len(self._users)
        self._page = min(self._page, self.total_pages - 1)
        self._update_buttons()
        if self.message is not None:
            try:
                await self.message.edit(embed=self.embed(), view=self)
            except discord.HTTPException:
                pass


class FollowRequestView(discord.ui.View):
    def __init__(self, people: PeopleView, user: SocialUser) -> None:
        super().__init__(timeout=120)
        self._people = people
        self._user = user

    async def _answer(self, interaction: discord.Interaction, approve: bool) -> None:
        await interaction.response.defer()
        try:
            await self._people._api.answer_follow_request(
                interaction.user.id, self._user.id, approve=approve
            )
        except Exception as exc:
            await interaction.edit_original_response(content=None, embed=to_embed(exc), view=None)
            return
        done = "agora te segue" if approve else "teve o pedido recusado"
        await interaction.edit_original_response(
            content=f"**{self._user.username}** {done}.", view=None
        )
        await self._people.request_answered(self._user)

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.success)
    async def approve(
        self, interaction: discord.Interaction, button: discord.ui.Button[FollowRequestView]
    ) -> None:
        await self._answer(interaction, True)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def reject(
        self, interaction: discord.Interaction, button: discord.ui.Button[FollowRequestView]
    ) -> None:
        await self._answer(interaction, False)


# ------------------------------------------------------------------ feed

class FeedView(discord.ui.View):
    """Uma pagina do feed por vez, pedida ao backend (a ordem e a dele)."""

    message: discord.Message | None = None

    def __init__(
        self, api: MyRankClient, author_id: int, items: list[FeedItem], *,
        page: int = 0, following_only: bool = False,
    ) -> None:
        super().__init__(timeout=600)
        self._api = api
        self._author_id = author_id
        self._items = items
        self._page = page
        self._following_only = following_only
        self.previous_page.disabled = page == 0
        self.next_page.disabled = not items
        takes = [item for item in items if item.is_take][:25]
        if takes:
            options = [
                discord.SelectOption(
                    label=_truncate(f"{t.actor.username}: {t.work.title if t.work else ''}", 100),
                    description=_truncate(t.take_text or "-", 100),
                    value=str(t.id),
                )
                for t in takes
            ]
            self.add_item(ChoiceSelect(options, "Abrir um take...", self._open_take))

    def embed(self) -> discord.Embed:
        return se.feed(self._items, self._page, self._following_only)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def on_timeout(self) -> None:
        await _disable_on_timeout(self, self.message)

    async def _go(self, interaction: discord.Interaction, page: int) -> None:
        await interaction.response.defer()
        try:
            items = await self._api.feed(
                interaction.user.id, page, FEED_PAGE_SIZE, following_only=self._following_only
            )
        except Exception as exc:
            await _fail(interaction, exc)
            return
        view = FeedView(self._api, self._author_id, items, page=page,
                        following_only=self._following_only)
        view.message = self.message
        self.stop()
        await interaction.edit_original_response(embed=view.embed(), view=view)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[FeedView]
    ) -> None:
        await self._go(interaction, self._page - 1)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button[FeedView]
    ) -> None:
        await self._go(interaction, self._page + 1)

    async def _open_take(self, interaction: discord.Interaction, value: str) -> None:
        item = next(i for i in self._items if str(i.id) == value)
        view = TakeView(self._api, self._author_id, item)
        await interaction.response.send_message(embed=se.take(item), view=view, ephemeral=True)


# ------------------------------------------------------------------ take

class TakeView(discord.ui.View):
    def __init__(self, api: MyRankClient, author_id: int, item: FeedItem) -> None:
        super().__init__(timeout=600)
        self._api = api
        self._author_id = author_id
        self.item = item
        for kind, label in REACTIONS:
            self.add_item(ReactionButton(self, kind, label))
        if not item.can_manage:
            self.remove_item(self.edit)
            self.remove_item(self.delete)
        self.comments.label = f"Comentarios ({item.comment_count})"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    def redraw(self, item: FeedItem) -> tuple[discord.Embed, TakeView]:
        self.stop()
        return se.take(item), TakeView(self._api, self._author_id, item)

    async def react(self, interaction: discord.Interaction, kind: str) -> None:
        await interaction.response.defer()
        try:
            reactions = await self._api.react(interaction.user.id, self.item.id, kind)
        except Exception as exc:
            await _fail(interaction, exc)
            return
        embed, view = self.redraw(dataclasses.replace(self.item, reactions=reactions))
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="Comentarios", style=discord.ButtonStyle.primary, row=1)
    async def comments(
        self, interaction: discord.Interaction, button: discord.ui.Button[TakeView]
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            roots = await self._api.comments(interaction.user.id, self._take_id)
        except Exception as exc:
            await interaction.edit_original_response(embed=to_embed(exc))
            return
        await interaction.edit_original_response(
            embed=se.comments(self.item, roots),
            view=CommentsView(self._api, self._author_id, self.item, roots),
        )

    @property
    def _take_id(self) -> int:
        assert self.item.take_id is not None
        return self.item.take_id

    @discord.ui.button(label="Editar", style=discord.ButtonStyle.secondary, row=1)
    async def edit(
        self, interaction: discord.Interaction, button: discord.ui.Button[TakeView]
    ) -> None:
        async def action(inner: discord.Interaction, text: str) -> None:
            await inner.response.defer()
            try:
                item = await self._api.edit_take(inner.user.id, self._take_id, text)
            except Exception as exc:
                await _fail(inner, exc)
                return
            embed, view = self.redraw(item)
            await inner.edit_original_response(embed=embed, view=view)

        await interaction.response.send_modal(TextModal(
            "Editar take", "Take", action, default=self.item.take_text,
            min_length=3, max_length=280,
        ))

    @discord.ui.button(label="Apagar", style=discord.ButtonStyle.danger, row=1)
    async def delete(
        self, interaction: discord.Interaction, button: discord.ui.Button[TakeView]
    ) -> None:
        async def confirmed(inner: discord.Interaction) -> None:
            await inner.response.defer()
            try:
                await self._api.delete_take(inner.user.id, self._take_id)
            except Exception as exc:
                await inner.edit_original_response(content=None, embed=to_embed(exc), view=None)
                return
            await inner.edit_original_response(content="Take apagado.", embed=None, view=None)

        self.stop()
        await interaction.response.edit_message(
            content="Apagar este take? Os comentarios e as reacoes vao junto.",
            view=ConfirmView(self._author_id, confirmed),
        )


class ReactionButton(discord.ui.Button[TakeView]):
    """Destacado quando e a reacao da pessoa; clicar de novo tira (regra do backend)."""

    def __init__(self, take_view: TakeView, kind: str, label: str) -> None:
        mine = take_view.item.reactions.mine == kind
        super().__init__(
            label=f"{label} {take_view.item.reactions.count(kind)}",
            style=discord.ButtonStyle.success if mine else discord.ButtonStyle.secondary,
            row=0,
        )
        self._take_view = take_view
        self.kind = kind

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._take_view.react(interaction, self.kind)


# ------------------------------------------------------------------ comentarios

class CommentsView(discord.ui.View):
    """Comentarios de um take em dois niveis, como no site. As acoes acontecem na
    propria mensagem e ela e redesenhada com a lista nova."""

    def __init__(
        self, api: MyRankClient, author_id: int, item: FeedItem, roots: list[TakeComment],
    ) -> None:
        super().__init__(timeout=600)
        self._api = api
        self._author_id = author_id
        self._item = item
        self._roots = roots
        everyone = [c for root in roots for c in (root, *root.replies)]
        self._editable = [c for c in everyone if c.can_edit]
        self._deletable = [c for c in everyone if c.can_delete]
        if not roots:
            self.remove_item(self.reply)
        if not self._editable:
            self.remove_item(self.edit)
        if not self._deletable:
            self.remove_item(self.delete)

    @property
    def _take_id(self) -> int:
        assert self._item.take_id is not None
        return self._item.take_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _check_author(interaction, self._author_id)

    async def _reload(self, interaction: discord.Interaction) -> None:
        """Busca a lista de novo e redesenha esta mensagem (ja confirmada com defer)."""
        roots = await self._api.comments(interaction.user.id, self._take_id)
        self.stop()
        await interaction.edit_original_response(
            content=None, embed=se.comments(self._item, roots),
            view=CommentsView(self._api, self._author_id, self._item, roots),
        )

    async def _do(
        self, interaction: discord.Interaction, call: Callable[[], Awaitable[object]],
    ) -> None:
        await interaction.response.defer()
        try:
            await call()
            await self._reload(interaction)
        except Exception as exc:
            await _fail(interaction, exc)

    async def _back(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content=None, embed=se.comments(self._item, self._roots),
            view=CommentsView(self._api, self._author_id, self._item, self._roots),
        )

    def _pick(
        self, comments: list[TakeComment], placeholder: str,
        on_pick: Callable[[discord.Interaction, TakeComment], Awaitable[None]],
    ) -> discord.ui.View:
        by_id = {str(c.id): c for c in comments[:25]}
        options = [
            discord.SelectOption(
                label=_truncate(f"{c.author.username}: {c.text}", 100), value=key,
            )
            for key, c in by_id.items()
        ]

        async def picked(interaction: discord.Interaction, value: str) -> None:
            await on_pick(interaction, by_id[value])

        return _CommentPickView(self, ChoiceSelect(options, placeholder, picked))

    @discord.ui.button(label="Comentar", style=discord.ButtonStyle.success)
    async def add(
        self, interaction: discord.Interaction, button: discord.ui.Button[CommentsView]
    ) -> None:
        async def action(inner: discord.Interaction, text: str) -> None:
            await self._do(inner, lambda: self._api.add_comment(inner.user.id, self._take_id, text))

        await interaction.response.send_modal(TextModal("Comentar", "Comentario", action))

    @discord.ui.button(label="Responder", style=discord.ButtonStyle.primary)
    async def reply(
        self, interaction: discord.Interaction, button: discord.ui.Button[CommentsView]
    ) -> None:
        async def on_pick(inner: discord.Interaction, root: TakeComment) -> None:
            async def action(modal_inter: discord.Interaction, text: str) -> None:
                await self._do(modal_inter, lambda: self._api.add_comment(
                    modal_inter.user.id, self._take_id, text, root.id))

            await inner.response.send_modal(
                TextModal(f"Responder {root.author.username}", "Resposta", action)
            )

        await interaction.response.edit_message(
            view=self._pick(self._roots, "Responder a qual comentario?", on_pick)
        )

    @discord.ui.button(label="Editar meu", style=discord.ButtonStyle.secondary)
    async def edit(
        self, interaction: discord.Interaction, button: discord.ui.Button[CommentsView]
    ) -> None:
        async def on_pick(inner: discord.Interaction, comment: TakeComment) -> None:
            async def action(modal_inter: discord.Interaction, text: str) -> None:
                await self._do(modal_inter, lambda: self._api.edit_comment(
                    modal_inter.user.id, comment.id, text))

            await inner.response.send_modal(
                TextModal("Editar comentario", "Comentario", action, default=comment.text)
            )

        await interaction.response.edit_message(
            view=self._pick(self._editable, "Editar qual?", on_pick)
        )

    @discord.ui.button(label="Apagar", style=discord.ButtonStyle.danger)
    async def delete(
        self, interaction: discord.Interaction, button: discord.ui.Button[CommentsView]
    ) -> None:
        async def on_pick(inner: discord.Interaction, comment: TakeComment) -> None:
            async def confirmed(confirm_inter: discord.Interaction) -> None:
                await self._do(confirm_inter, lambda: self._api.delete_comment(
                    confirm_inter.user.id, comment.id))

            await inner.response.edit_message(
                content=("Apagar este comentario?" +
                         (" As respostas dele vao junto." if comment.replies else "")),
                view=ConfirmView(self._author_id, confirmed, on_cancel=self._back),
            )

        await interaction.response.edit_message(
            view=self._pick(self._deletable, "Apagar qual?", on_pick)
        )


class _BackButton(discord.ui.Button["_CommentPickView"]):
    def __init__(self, comments_view: CommentsView) -> None:
        super().__init__(label="Voltar", style=discord.ButtonStyle.secondary, row=1)
        self._comments_view = comments_view

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view is not None:
            self.view.stop()
        await self._comments_view._back(interaction)


class _CommentPickView(discord.ui.View):
    def __init__(self, comments_view: CommentsView, select: ChoiceSelect) -> None:
        super().__init__(timeout=120)
        self._comments_view = comments_view
        self.add_item(select)
        self.back = _BackButton(comments_view)
        self.add_item(self.back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self._comments_view.interaction_check(interaction)
