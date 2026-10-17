"""Versioned domain contracts and canonical physical identities."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Literal, Self
from urllib.parse import quote

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)


def _segment(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("address segments must be nonempty without surrounding whitespace")
    return quote(value, safe="")


def table_id(
    namespace: str, table: str, *, catalog: str | None = None, schema: str | None = None
) -> str:
    """Encode named slots, distinguishing absent catalog from absent schema."""
    cat = "" if catalog is None else _segment(catalog)
    sch = "" if schema is None else _segment(schema)
    return (
        f"urn:bindofell:table:{_segment(namespace)}/catalog={cat}"
        f"/schema={sch}/table={_segment(table)}"
    )


def field_id(
    namespace: str,
    table: str,
    column: str,
    *,
    catalog: str | None = None,
    schema: str | None = None,
) -> str:
    """Preserve case and encode delimiters without guessing optional segments."""
    parent = table_id(namespace, table, catalog=catalog, schema=schema)
    return (
        parent.replace("urn:bindofell:table:", "urn:bindofell:field:", 1)
        + f"/column={_segment(column)}"
    )


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _namespaced(value: str) -> str:
    if ":" not in value or value != value.strip() or not all(value.split(":")):
        raise ValueError("identifier must be nonempty and namespaced")
    return value


Scalar = StrictStr | int | float | StrictBool | None
Text = Annotated[StrictStr, AfterValidator(_nonblank)]
Identifier = Annotated[StrictStr, AfterValidator(_namespaced)]
Digest = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]


def _freeze(value: Mapping[str, Scalar]) -> Mapping[str, Scalar]:
    return MappingProxyType(dict(value))


def _mapping_json(value: Mapping[str, Scalar]) -> dict[str, Scalar]:
    return dict(value)


Attributes = Annotated[
    Mapping[str, Scalar],
    AfterValidator(_freeze),
    PlainSerializer(_mapping_json, return_type=dict[str, Scalar]),
]


class Contract(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        validate_default=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class TableAddress(Contract):
    namespace: Text
    table: Text
    catalog: Text | None = None
    schema_name: Text | None = Field(default=None, alias="schema")

    @field_validator("namespace", "table", "catalog", "schema_name")
    @classmethod
    def address_segment(cls, value: str | None) -> str | None:
        if value is not None:
            _segment(value)
        return value

    @property
    def table_id(self) -> str:
        return table_id(self.namespace, self.table, catalog=self.catalog, schema=self.schema_name)


class FieldAddress(TableAddress):
    column: Text

    @field_validator("column")
    @classmethod
    def column_segment(cls, value: str) -> str:
        _segment(value)
        return value

    @property
    def field_id(self) -> str:
        return field_id(
            self.namespace, self.table, self.column, catalog=self.catalog, schema=self.schema_name
        )


class SourceDigest(Contract):
    path: Text
    sha256: Digest


class Dataset(Contract):
    dataset_id: Identifier
    namespace: Text
    name: Text
    version: Text
    revision: Text
    source_uri: Text
    retrieved_at: AwareDatetime | None = None
    license: Text | None = None


class Evidence(Contract):
    evidence_id: Identifier
    kind: Literal["source", "computation", "model"]
    asset_id: Identifier | None = None
    source_locator: Text | None = None
    source_digest: Digest | None = None
    attribute: Text | None = None
    value: Scalar = None
    computation: Text | None = None
    computation_version: Text | None = None
    input_ids: tuple[Identifier, ...] = ()
    parameters: Attributes = Field(default_factory=dict)
    model_id: Text | None = None
    model_revision: Text | None = None
    output_reference: Text | None = None

    @model_validator(mode="after")
    def attribution(self) -> Self:
        if self.kind == "source" and not all(
            (self.asset_id, self.source_locator, self.source_digest, self.attribute)
        ):
            raise ValueError("source evidence needs asset, locator, digest and attribute")
        if self.kind == "computation" and not all(
            (self.computation, self.computation_version, self.input_ids)
        ):
            raise ValueError("computation evidence needs name, version and input IDs")
        if self.kind == "model" and not all(
            (self.model_id, self.model_revision, self.output_reference)
        ):
            raise ValueError("model evidence needs model revision and output reference")
        return self


class Metadata(Contract):
    description: Text | None = None
    guidance: Text | None = None
    etl_conventions: Text | None = None
    attributes: Attributes = Field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()


class Table(Metadata):
    table_id: Identifier
    address: TableAddress
    name: Text
    required: StrictBool | None = None

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.table_id != self.address.table_id or self.name != self.address.table:
            raise ValueError("table ID and name must match canonical table address")
        return self


class PhysicalField(Metadata):
    field_id: Identifier
    table_id: Identifier
    address: FieldAddress
    name: Text
    data_type: Text | None = None
    required: StrictBool | None = None
    nullable: StrictBool | None = None
    primary_key: StrictBool | None = None
    foreign_key: StrictBool | None = None

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.field_id != self.address.field_id or self.name != self.address.column:
            raise ValueError("field ID and name must match canonical field address")
        if self.table_id != self.address.table_id:
            raise ValueError("field parent must match canonical table address")
        return self


class Relationship(Contract):
    relationship_id: Identifier
    source_field_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    target_field_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    kind: Text
    cardinality: Text | None = None
    evidence: tuple[Evidence, ...] = ()

    @model_validator(mode="after")
    def endpoints(self) -> Self:
        if len(self.source_field_ids) != len(self.target_field_ids):
            raise ValueError("relationship endpoint lists must have equal lengths")
        for ids in (self.source_field_ids, self.target_field_ids):
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate relationship endpoint")
        return self


class EstateSnapshot(Contract):
    schema_version: Literal["1.0"] = "1.0"
    snapshot_id: Identifier
    dataset: Dataset
    source_digests: Annotated[tuple[SourceDigest, ...], Field(min_length=1)]
    tables: tuple[Table, ...]
    fields: tuple[PhysicalField, ...]
    relationships: tuple[Relationship, ...] = ()
    adapter_id: Text | None = None

    @model_validator(mode="after")
    def integrity(self) -> Self:
        for label, ids in (
            ("table", [t.table_id for t in self.tables]),
            ("field", [f.field_id for f in self.fields]),
            ("relationship", [r.relationship_id for r in self.relationships]),
            ("source path", [d.path for d in self.source_digests]),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {label} identity")
        tables = {t.table_id for t in self.tables}
        fields = {f.field_id for f in self.fields}
        for table in self.tables:
            if table.address.namespace != self.dataset.namespace:
                raise ValueError(f"table namespace differs from dataset: {table.table_id}")
        for field in self.fields:
            if field.table_id not in tables:
                raise ValueError(f"unknown table for field {field.field_id}: {field.table_id}")
        for relation in self.relationships:
            for endpoint in (*relation.source_field_ids, *relation.target_field_ids):
                if endpoint not in fields:
                    raise ValueError(
                        f"unknown relationship endpoint {endpoint} in {relation.relationship_id}"
                    )
        for name, ordered in (
            ("tables", sorted(self.tables, key=lambda t: t.table_id)),
            ("fields", sorted(self.fields, key=lambda f: f.field_id)),
            ("relationships", sorted(self.relationships, key=lambda r: r.relationship_id)),
            ("source_digests", sorted(self.source_digests, key=lambda d: d.path)),
        ):
            object.__setattr__(self, name, tuple(ordered))
        return self


class BusinessRequirement(Contract):
    requirement_id: Identifier
    text: Text
    business_context: Text | None = None
    constraints: Attributes = Field(default_factory=dict)
    locale: Text | None = None


class DirectBinding(Contract):
    kind: Literal["direct"] = "direct"
    binding_id: Identifier
    requirement_id: Identifier
    snapshot_id: Identifier
    field_id: Identifier
    evidence: tuple[Evidence, ...] = ()


class DerivedBinding(Contract):
    """Forward-compatible metadata only: no expression interpretation or execution."""

    kind: Literal["derived"] = "derived"
    binding_id: Identifier
    requirement_id: Identifier
    snapshot_id: Identifier
    output_name: Text
    input_field_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    expression_reference: Text
    grain: Text | None = None
    evidence: tuple[Evidence, ...] = ()


SemanticBinding = Annotated[DirectBinding | DerivedBinding, Field(discriminator="kind")]


class BindingCandidate(Contract):
    requirement_id: Identifier
    snapshot_id: Identifier
    field_id: Identifier
    rank: Annotated[int, Field(gt=0, strict=True)]
    raw_score: Annotated[float, Field(strict=True)]
    method_id: Text
    method_config: Attributes = Field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()
