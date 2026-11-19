"""Corpos dos PUT /works que o /manage manda.

O PUT do backend e parcial: campo ausente (ou null) nao muda nada. Por isso cada
funcao aqui devolve so o que mudou -- mandar a obra inteira arriscaria desfazer uma
edicao feita no site enquanto a mensagem do bot estava aberta.
"""

from __future__ import annotations

from typing import Any

from myrank.media import MediaType
from myrank.models import ExternalDetails, Work


def edit_payload(
    work: Work,
    *,
    title: str,
    creator: str,
    release_date: str | None,
    time_minutes: int | None,
    image_url: str,
) -> dict[str, Any]:
    """Dados basicos editados no /manage.

    Criador e capa vazios vao como "" e apagam, como no site. A data nao pode ser
    apagada (o backend trata null como "manter"), entao vazio nao manda nada.
    `time_minutes` None = o modal nem perguntou o tempo.
    """
    payload: dict[str, Any] = {}
    if title != work.title:
        payload["title"] = title
    if creator != (work.creator or ""):
        payload["creator"] = creator
    if release_date is not None and release_date != work.release_date:
        payload["releaseDate"] = release_date
    if time_minutes is not None and time_minutes != work.time_minutes:
        payload["timeMinutes"] = time_minutes
    if image_url != (work.image_url or ""):
        payload["imageUrl"] = image_url
    return payload


def custom_fields_payload(work: Work, values: dict[str, Any]) -> dict[str, Any]:
    """Campos proprios: `details` e substituido inteiro, entao vai a ficha atual com
    `fields` trocado. Valor None apaga aquele campo na obra."""
    details = dict(work.details)
    details["fields"] = values
    return {"details": details}


def change_template_payload(work: Work, template: str) -> dict[str, Any]:
    """Trocar o tipo numa tabela mista, como o site: a ligacao com a busca antiga
    (`externalId`, `provider`) sai, porque era de outro catalogo, e os campos
    proprios saem tambem, porque o backend so os aceita em Personalizado."""
    details = {
        key: value for key, value in work.details.items()
        if key not in ("externalId", "provider", "fields", "legacyClassificationRequired")
    }
    return {"template": template, "details": details}


def refresh_payload(
    work: Work, media: MediaType, fetched: ExternalDetails
) -> dict[str, Any]:
    """Botao "Atualizar dados", igual ao do site: so o que muda com o tempo
    (episodios, situacao, generos...). Capa e data so entram se estiverem vazias;
    titulo, nota, tempo e criador nunca mudam."""
    details = {**work.details, **fetched.details}
    details["externalId"] = fetched.external_id
    details["provider"] = media.provider
    payload: dict[str, Any] = {"details": details}
    if not work.image_url and fetched.image_url:
        payload["imageUrl"] = fetched.image_url
    if not work.release_date and fetched.release_date:
        payload["releaseDate"] = fetched.release_date
    return payload
