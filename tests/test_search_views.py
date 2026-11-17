from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrank.errors import ApiUnavailableError
from myrank.media import TV
from myrank.models import Category, ExternalDetails, ExternalResult
from ui.views import CategoryPickView, MediaPreviewView, MediaResultView


def interaction() -> Any:
    value = MagicMock()
    value.user.id = 123
    value.response.defer = AsyncMock()
    value.response.edit_message = AsyncMock()
    value.response.send_modal = AsyncMock()
    value.response.send_message = AsyncMock()
    value.edit_original_response = AsyncMock()
    return value


async def test_covers_and_navigation_include_results_after_25() -> None:
    results = [ExternalResult.from_api({
        "externalId": str(i), "title": f"Obra {i}", "releaseDate": "2008-01-20",
        "posterUrl": f"https://example.com/{i}.jpg",
    }) for i in range(26)]
    view = MediaResultView(MagicMock(), 123, TV, results)
    assert view.embed().image.url == "https://example.com/0.jpg"
    assert view.previous_page.disabled
    for _ in range(25):
        await view.next_page.callback(interaction())
    assert view.embed().title == "Obra 25"
    assert view.next_page.disabled
    await view.previous_page.callback(interaction())
    assert view.embed().title == "Obra 24"
    missing = MediaResultView(MagicMock(), 123, TV, [ExternalResult("1", "Sem capa")])
    assert "Capa nao disponivel" in (missing.embed().description or "")
    assert missing.next_page.disabled


@pytest.mark.parametrize("failed", [False, True])
async def test_details_acknowledged_before_http_and_never_save(failed: bool) -> None:
    i = interaction()
    details = ExternalDetails("", "Breaking Bad", 3472, "https://example.com/bb.jpg",
                              "Vince Gilligan", "2008-01-20")

    async def fetch(*args: Any) -> ExternalDetails:
        i.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)
        if failed:
            raise ApiUnavailableError("Indisponivel")
        return details

    api = MagicMock()
    api.external_details = AsyncMock(side_effect=fetch)
    api.get_categories = AsyncMock(return_value=[Category(1, "Series")])
    view = MediaResultView(api, 123, TV, [ExternalResult("1396", "Breaking Bad")])
    await view.show_details.callback(i)
    api.external_details.assert_awaited_once_with(123, "tv", "1396")
    i.response.send_modal.assert_not_awaited()
    api.create_work.assert_not_called()
    response = i.edit_original_response.call_args.kwargs
    if failed:
        assert response["view"] is None
    else:
        assert isinstance(response["view"], MediaPreviewView)
        assert response["embed"].image.url == details.image_url
        assert any(f.value == "Vince Gilligan" for f in response["embed"].fields)


@pytest.mark.parametrize("categories", [[Category(1, "Series")], [Category(2, "Favoritos")], []])
async def test_confirm_with_matching_custom_or_missing_category(
    categories: list[Category],
) -> None:
    api = MagicMock()
    view = MediaPreviewView(api, 123, TV, ExternalDetails("", "Teste", 120), categories)
    i = interaction()
    await view.confirm.callback(i)
    if categories and categories[0].name == "Series":
        i.response.send_modal.assert_awaited_once()
    else:
        response = i.response.edit_message.call_args.kwargs
        if categories:
            assert isinstance(response["view"], CategoryPickView)
        else:
            assert response["view"] is None
    api.create_work.assert_not_called()


async def test_preview_author_and_cancel() -> None:
    view = MediaPreviewView(MagicMock(), 123, TV, ExternalDetails("", "Teste", 120), [])
    i = interaction()
    i.user.id = 456
    assert not await view.interaction_check(i)
    i.user.id = 123
    assert await view.interaction_check(i)
    await view.cancel.callback(i)
    assert i.response.edit_message.call_args.kwargs["view"] is None
