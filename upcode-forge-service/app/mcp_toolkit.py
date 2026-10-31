"""Explicit MCP tool allowlist backed by the existing application API."""

from dataclasses import dataclass
from functools import cached_property
from typing import Any

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, create_model


@dataclass(frozen=True)
class APITool:
    name: str
    description: str
    scope: str
    method: str
    path: str
    path_fields: dict[str, Any] | None = None
    query_fields: dict[str, Any] | None = None
    payload: type[BaseModel] | None = None

    @cached_property
    def input_model(self):
        fields = {name: (kind, ...) for name, kind in (self.path_fields or {}).items()}
        fields.update(self.query_fields or {})
        if self.payload:
            fields["payload"] = (self.payload, ...)
        return create_model(self.name + "Input", __config__=ConfigDict(extra="forbid"), **fields)

    def definition(self):
        return Tool(
            name=self.name,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
            annotations=ToolAnnotations(
                read_only_hint=self.method == "GET",
                destructive_hint=self.method in {"DELETE", "PUT", "PATCH"} or "merge" in self.name,
                idempotent_hint=self.method == "GET",
                open_world_hint=False,
            ),
        )

    def request(self, arguments):
        validated = self.input_model.model_validate(arguments)
        values = validated.model_dump(mode="json")
        path_values = {key: values[key] for key in (self.path_fields or {})}
        query = {key: values[key] for key in (self.query_fields or {}) if values[key] is not None}
        payload = (
            validated.payload.model_dump(mode="json", exclude_unset=True) if self.payload else None
        )
        return self.path.format(**path_values), query, payload
