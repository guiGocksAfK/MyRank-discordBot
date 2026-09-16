"""A unica logica que e legitimamente do bot.

Duas coisas: o mapa do choice fechado do `/add` para o endpoint externo, e o
palpite de qual categoria do usuario corresponde a midia escolhida.

O palpite existe porque categorias sao por usuario e texto livre -- nao ha enum
no backend. Por isso o casamento e por pista textual e pode falhar de proposito:
quando falha, o `/add` mostra um select com as categorias reais. O bot nunca
inventa nem cria categoria.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from myrank.models import Category


@dataclass(frozen=True, slots=True)
class MediaType:
    key: str
    label: str
    endpoint: str
    category_hints: tuple[str, ...]


MOVIE = MediaType("movie", "Filme", "movies", ("filme", "filmes", "cinema", "movie"))
TV = MediaType("tv", "Serie", "tv", ("serie", "series", "tv", "show"))
GAME = MediaType("game", "Jogo", "games", ("jogo", "jogos", "game", "games"))
ANIME = MediaType("anime", "Anime", "anime", ("anime", "animes", "serie", "series"))
BOOK = MediaType("book", "Livro", "books", ("livro", "livros", "book", "books", "leitura"))

MEDIA_TYPES: tuple[MediaType, ...] = (MOVIE, TV, GAME, ANIME, BOOK)
_BY_KEY = {media.key: media for media in MEDIA_TYPES}


def by_key(key: str) -> MediaType:
    """Resolve o valor vindo do choice do Discord."""
    try:
        return _BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"Midia desconhecida: {key!r}") from exc


def match_category(media: MediaType, categories: list[Category]) -> Category | None:
    """Melhor palpite de categoria, ou `None` quando nao ha match confiavel.

    `None` nao e erro -- e o sinal de que o `/add` deve perguntar ao usuario.
    """
    for hint in media.category_hints:
        for category in categories:
            if hint in normalize(category.name):
                return category
    return None


def normalize(text: str) -> str:
    """Minusculas, sem acento e sem emoji, para comparar nome de categoria.

    "📺 Series & Animes" e "series & animes" tem que casar.
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        char
        for char in decomposed
        if not unicodedata.combining(char) and (char.isalnum() or char.isspace())
    ).strip()
