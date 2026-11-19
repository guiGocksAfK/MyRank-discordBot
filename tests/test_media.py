from __future__ import annotations

import pytest

from myrank import media
from myrank.models import Category, ExternalDetails

TABELAS = [
    Category(1, "\U0001f3ac Filmes", templates=("movie",)),
    Category(2, "\U0001f4fa Séries & Animes", templates=("tv", "anime")),
    Category(3, "Meus favoritos", templates=("anime",)),
    Category(4, "Coisas", templates=("custom",)),
]


def test_tem_as_8_midias_do_site() -> None:
    assert [m.template for m in media.MEDIA_TYPES] == [
        "movie", "tv", "anime", "manga", "game", "book", "music", "album",
    ]


def test_by_template_resolve_o_choice_do_discord() -> None:
    assert media.by_template("album").endpoint == "albums"
    with pytest.raises(ValueError):
        media.by_template("podcast")


def test_tabelas_pelo_tipo_e_nao_pelo_nome() -> None:
    # "Meus favoritos" nao tem "anime" no nome, mas aceita anime.
    assert media.tables_for(media.ANIME, TABELAS) == [TABELAS[1], TABELAS[2]]
    assert media.tables_for(media.MOVIE, TABELAS) == [TABELAS[0]]


def test_sem_tabela_do_tipo_devolve_vazio() -> None:
    # Sinal de que a pessoa precisa criar a tabela -- o bot nunca cria sozinho.
    assert media.tables_for(media.GAME, TABELAS) == []


def test_payload_grava_template_ficha_e_origem() -> None:
    details = ExternalDetails(
        "1396", "Breaking Bad", 3472, "https://example.com/bb.jpg", "Vince Gilligan",
        "2008-01-20", {"seasons": 5, "genres": ["Drama"]},
    )
    payload = media.new_work_payload(
        media.TV, details, category_id=2, subcategory_id=7, score=9.5
    )
    assert payload == {
        "categoryId": 2,
        "subcategoryId": 7,
        "template": "tv",
        "title": "Breaking Bad",
        "score": 9.5,
        "timeMinutes": 3472,
        "imageUrl": "https://example.com/bb.jpg",
        "creator": "Vince Gilligan",
        "releaseDate": "2008-01-20",
        "details": {
            "seasons": 5, "genres": ["Drama"], "provider": "tmdb", "externalId": "1396",
        },
    }
    # A ficha original nao e alterada.
    assert "provider" not in details.details


def test_tempo_informado_substitui_o_da_busca() -> None:
    details = ExternalDetails("3498", "Elden Ring", 0)
    payload = media.new_work_payload(
        media.GAME, details, category_id=1, subcategory_id=None, score=10, time_minutes=6000
    )
    assert payload["timeMinutes"] == 6000
    assert payload["subcategoryId"] is None
