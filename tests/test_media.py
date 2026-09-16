from __future__ import annotations

from myrank import media
from myrank.models import Category

PADRAO = [
    Category(1, "\U0001f3ac Filmes", True),
    Category(2, "\U0001f3ae Jogos", True),
    Category(3, "\U0001f4da Livros", True),
    Category(4, "\U0001f4fa Series & Animes", True),
]


def test_normalize_tira_emoji_e_acento() -> None:
    assert media.normalize("\U0001f4fa Séries & Animes") == "series  animes"


def test_casa_filme_com_categoria_padrao() -> None:
    assert media.match_category(media.MOVIE, PADRAO) == PADRAO[0]


def test_anime_cai_na_categoria_de_series_e_animes() -> None:
    assert media.match_category(media.ANIME, PADRAO) == PADRAO[3]


def test_sem_match_confiavel_devolve_none() -> None:
    # Sinal de que o /add deve perguntar ao usuario -- nunca criar categoria.
    assert media.match_category(media.GAME, [Category(9, "Coisas aleatorias")]) is None


def test_categoria_criada_pelo_usuario_tambem_casa() -> None:
    minhas = [Category(10, "Meus filmes favoritos")]
    assert media.match_category(media.MOVIE, minhas) == minhas[0]


def test_by_key_resolve_o_choice_do_discord() -> None:
    assert media.by_key("book").endpoint == "books"
