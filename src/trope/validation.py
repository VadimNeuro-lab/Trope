"""Schema validation for parser output."""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator

from trope.config import SCHEMA_DIR
from trope.types import ENTITY_TYPES, RELATION_TYPES, Representation, SchemaError

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@functools.lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    path = SCHEMA_DIR / "representation.json"
    return json.loads(path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(schema())


def frame_vocabulary() -> tuple[str, ...]:
    return tuple(schema()["properties"]["frame"]["enum"])


def normalise_name(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(" ", "-")


def extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model response."""
    blob = text.strip()
    fenced = _FENCE.search(blob)
    if fenced:
        blob = fenced.group(1).strip()
    start = blob.find("{")
    if start == -1:
        raise SchemaError("no JSON object found in parser output")
    depth, end, in_str, esc = 0, -1, False, False
    for i, ch in enumerate(blob[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise SchemaError("unterminated JSON object in parser output")
    try:
        data = json.loads(blob[start:end])
    except json.JSONDecodeError as exc:
        raise SchemaError(f"invalid JSON: {exc.msg} at position {exc.pos}") from exc
    if not isinstance(data, dict):
        raise SchemaError("parser output is not a JSON object")
    return data


def canonicalise(data: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise frame and sort spellings before validating."""
    out = json.loads(json.dumps(data))
    if "frame" in out and isinstance(out["frame"], str):
        out["frame"] = normalise_name(out["frame"])
    for entity in out.get("entities") or []:
        if isinstance(entity, dict):
            entity.setdefault("sort", "")
            entity.setdefault("label", "")
            if isinstance(entity.get("type"), str):
                entity["type"] = entity["type"].strip().lower()
    for rel in out.get("relations") or []:
        if isinstance(rel, dict) and isinstance(rel.get("rtype"), str):
            rel["rtype"] = rel["rtype"].strip().lower().replace("-", "_")
    for a in out.get("assumptions") or []:
        if isinstance(a, dict):
            a.setdefault("negated", False)
    out.setdefault("relations", [])
    return out


def schema_errors(data: Mapping[str, Any]) -> list[str]:
    errors = []
    for err in sorted(_validator().iter_errors(data), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"{where}: {err.message}")
    return errors


def semantic_errors(data: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    entities = data.get("entities") or []
    ids = [str(e.get("id")) for e in entities if isinstance(e, dict)]
    if len(set(ids)) != len(ids):
        errors.append("entities: duplicate id")
    known = set(ids)
    for i, rel in enumerate(data.get("relations") or []):
        if not isinstance(rel, dict):
            continue
        for side in ("src", "dst", "aux"):
            value = rel.get(side)
            if side == "aux" and not value:
                continue
            if str(value) not in known:
                errors.append(f"relations/{i}/{side}: {value!r} is not an entity id")
    assumptions = data.get("assumptions") or []
    if assumptions and not any(
        isinstance(a, dict) and a.get("load_bearing") for a in assumptions
    ):
        errors.append(
            "assumptions: at least one assumption must be marked load_bearing"
        )
    return errors


def validate(data: Mapping[str, Any]) -> list[str]:
    canonical = canonicalise(data)
    errors = schema_errors(canonical)
    if errors:
        return errors
    return semantic_errors(canonical)


def parse_representation(text: str, *, source_text: str = "") -> Representation:
    """Model output -> validated Representation, or SchemaError with a message the retry loop can hand back to the model."""
    data = canonicalise(extract_json(text))
    errors = validate(data)
    if errors:
        raise SchemaError("; ".join(errors[:6]))
    return Representation.from_dict(data, source_text=source_text)


def check_vocabularies() -> None:
    """Guard against the schema file and the dataclasses drifting apart."""
    props = schema()["properties"]
    schema_types = tuple(props["entities"]["items"]["properties"]["type"]["enum"])
    if schema_types != ENTITY_TYPES:
        raise SchemaError(
            f"entity type vocabulary differs: schema {schema_types} vs code {ENTITY_TYPES}"
        )
    schema_rels = tuple(props["relations"]["items"]["properties"]["rtype"]["enum"])
    if schema_rels != RELATION_TYPES:
        raise SchemaError(
            f"relation vocabulary differs: schema {schema_rels} vs code {RELATION_TYPES}"
        )
