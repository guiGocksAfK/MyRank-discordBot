"""Os tipos de midia do MyRank e como uma obra nova vira o corpo do POST /works.

Cada tipo corresponde a um template do backend (`TableTemplate`). O template, e nao
o nome da tabela, diz onde a obra pode entrar: uma tabela aceita os templates que
foram escolhidos para ela. Por isso o bot nao adivinha tabela pelo nome.

O corpo do POST segue o que o site faz ao escolher um resultado da busca: a ficha
(`details`) vem pronta do backend e o bot so acrescenta de onde ela veio
(`provider` e `externalId`), que e o que o "Atualizar dados" usa depois.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from myrank.models import Category, ExternalDetails


@dataclass(frozen=True, slots=True)
class MediaType:
    template: str  # valor do TableTemplate no backend
    label: str
    endpoint: str  # /external/search/{endpoint} e /external/{endpoint}/{id}
    provider: str  # gravado em details.provider, igual ao site
    # Se o tempo dedicado vira bonus na nota final. Espelha o backend; aqui so
    # decide se vale perguntar o tempo quando a busca nao trouxe.
    time_weighted: bool = True


MOVIE = MediaType("movie", "Filme", "movies", "tmdb")
TV = MediaType("tv", "Série", "tv", "tmdb")
ANIME = MediaType("anime", "Anime", "anime", "myanimelist")
MANGA = MediaType("manga", "Mangá", "manga", "myanimelist", time_weighted=False)
GAME = MediaType("game", "Jogo", "games", "rawg")
BOOK = MediaType("book", "Livro", "books", "google-books")
MUSIC = MediaType("music", "Música", "music", "deezer", time_weighted=False)
ALBUM = MediaType("album", "Álbum", "albums", "deezer", time_weighted=False)

MEDIA_TYPES: tuple[MediaType, ...] = (MOVIE, TV, ANIME, MANGA, GAME, BOOK, MUSIC, ALBUM)
_BY_TEMPLATE = {media.template: media for media in MEDIA_TYPES}

# "Personalizado" nao tem busca: so existe no cadastro a mao.
CUSTOM_TEMPLATE = "custom"
CUSTOM_LABEL = "Personalizado"


def template_label(template: str) -> str:
    media = _BY_TEMPLATE.get(template)
    return media.label if media else CUSTOM_LABEL


def template_time_weighted(template: str) -> bool:
    media = _BY_TEMPLATE.get(template)
    return media.time_weighted if media else True


def manual_work_payload(
    template: str,
    *,
    category_id: int,
    subcategory_id: int | None,
    title: str,
    score: float,
    time_minutes: int,
    creator: str | None,
    release_date: str | None,
) -> dict[str, Any]:
    """Corpo do POST /works para uma obra digitada a mao (sem busca, sem ficha)."""
    return {
        "categoryId": category_id,
        "subcategoryId": subcategory_id,
        "template": template,
        "title": title,
        "score": score,
        "timeMinutes": time_minutes,
        "creator": creator,
        "releaseDate": release_date,
    }


def by_template(template: str) -> MediaType:
    """Resolve o valor vindo do choice do Discord (ou o template de uma obra)."""
    try:
        return _BY_TEMPLATE[template]
    except KeyError as exc:
        raise ValueError(f"Midia desconhecida: {template!r}") from exc


def tables_for(media: MediaType, categories: list[Category]) -> list[Category]:
    """Tabelas da pessoa que aceitam esse tipo, na ordem em que a API devolveu.

    Lista vazia nao e erro: e o sinal de que a pessoa precisa criar a tabela antes.
    """
    return [category for category in categories if media.template in category.templates]


def new_work_payload(
    media: MediaType,
    details: ExternalDetails,
    *,
    category_id: int,
    subcategory_id: int | None,
    score: float,
    time_minutes: int | None = None,
) -> dict[str, Any]:
    """Corpo do POST /works para uma obra que veio da busca externa.

    `time_minutes` so substitui o da busca quando a pessoa informou o tempo porque
    a API nao trouxe.
    """
    ficha = dict(details.details)
    ficha["provider"] = media.provider
    ficha["externalId"] = details.external_id
    return {
        "categoryId": category_id,
        "subcategoryId": subcategory_id,
        "template": media.template,
        "title": details.title,
        "score": score,
        "timeMinutes": details.time_minutes if time_minutes is None else time_minutes,
        "imageUrl": details.image_url,
        "creator": details.creator,
        "releaseDate": details.release_date,
        "details": ficha,
    }
