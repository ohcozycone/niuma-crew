"""Shared request conventions and paginated response shapes."""

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.values import optional_text

RecordID = Annotated[str, StringConstraints(strict=True, pattern=r"^[1-9][0-9]{11}$")]

NonBlankText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
OptionalText = Annotated[str | None, AfterValidator(optional_text)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def omitted_field() -> Any:
    # A PATCH omission sentinel. Explicit null still fails the non-nullable type.
    # Consumers must read PATCH values with model_dump(exclude_unset=True).
    return Field(default=None, json_schema_extra=lambda schema: schema.pop("default", None))


class Page[Item](BaseModel):
    items: list[Item]
    total: int
    offset: int
    limit: int
