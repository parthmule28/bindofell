"""Deterministic, attributable text channels kept separate from source metadata."""

import json
from collections.abc import Iterable
from typing import Literal

from bindofell.domain.models import Contract, EstateSnapshot, Evidence, Identifier, Text

Profile = Literal["names", "field_descriptions", "table_context"]
PROFILES: dict[str, tuple[str, ...]] = {
    "names": ("table_name", "field_name"),
    "field_descriptions": ("table_name", "field_name", "field_description", "field_guidance"),
    "table_context": (
        "table_name",
        "field_name",
        "field_description",
        "field_guidance",
        "table_description",
        "table_guidance",
    ),
}
SOURCE_ATTRIBUTES = {
    "table_name": ("name", "cdmTableName"),
    "field_name": ("name", "cdmFieldName"),
    "field_description": ("description",),
    "field_guidance": ("guidance", "userGuidance"),
    "table_description": ("description", "tableDescription"),
    "table_guidance": ("guidance", "userGuidance"),
}


class TextChannel(Contract):
    name: Text
    value: Text
    evidence_ids: tuple[Identifier, ...] = ()


class SearchDocument(Contract):
    field_id: Identifier
    snapshot_id: Identifier
    profile: Profile
    serializer_id: Literal["bindofell.search-document/1.0"] = "bindofell.search-document/1.0"
    channels: tuple[TextChannel, ...]
    omitted_channels: tuple[Text, ...]

    @property
    def text(self) -> str:
        return "\n".join(f"{c.name}: {c.value}" for c in self.channels)


def build_search_documents(
    snapshot: EstateSnapshot, *, profile: Profile
) -> tuple[SearchDocument, ...]:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    tables = {t.table_id: t for t in snapshot.tables}
    result: list[SearchDocument] = []
    for field in snapshot.fields:
        table = tables[field.table_id]
        values: dict[str, tuple[str | None, tuple[Evidence, ...]]] = {
            "table_name": (table.name, table.evidence),
            "field_name": (field.name, field.evidence),
            "field_description": (field.description, field.evidence),
            "field_guidance": (field.guidance, field.evidence),
            "table_description": (table.description, table.evidence),
            "table_guidance": (table.guidance, table.evidence),
        }
        channels: list[TextChannel] = []
        omitted: list[str] = []
        for name in PROFILES[profile]:
            value, evidence = values[name]
            if value is None:
                omitted.append(name)
                continue
            references = tuple(
                sorted(e.evidence_id for e in evidence if e.attribute in SOURCE_ATTRIBUTES[name])
            )
            channels.append(TextChannel(name=name, value=value, evidence_ids=references))
        result.append(
            SearchDocument(
                field_id=field.field_id,
                snapshot_id=snapshot.snapshot_id,
                profile=profile,
                channels=tuple(channels),
                omitted_channels=tuple(omitted),
            )
        )
    return tuple(result)


def documents_to_jsonl(documents: Iterable[SearchDocument]) -> str:
    return "".join(
        json.dumps(
            {**d.model_dump(mode="json"), "text": d.text},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
        for d in sorted(documents, key=lambda d: d.field_id)
    )
