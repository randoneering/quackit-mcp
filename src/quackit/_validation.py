from __future__ import annotations


class ValidationError(ValueError):
    pass


_MAX_CONTENT = 100_000
_MAX_QUERY = 500
_MAX_NAME = 200
_MAX_TAG = 200
_MAX_TAGS = 50
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000


def validate_content(value: str) -> str:
    if not value:
        raise ValidationError("content must not be empty")
    if len(value) > _MAX_CONTENT:
        raise ValidationError(
            f"content exceeds {_MAX_CONTENT} characters ({len(value)})"
        )
    return value


def validate_query(value: str) -> str:
    if len(value) > _MAX_QUERY:
        raise ValidationError(f"query exceeds {_MAX_QUERY} characters ({len(value)})")
    return value


def validate_name(value: str) -> str:
    if not value:
        raise ValidationError("name must not be empty")
    if len(value) > _MAX_NAME:
        raise ValidationError(f"name exceeds {_MAX_NAME} characters ({len(value)})")
    return value


def validate_tags(value: list[str]) -> list[str]:
    if len(value) > _MAX_TAGS:
        raise ValidationError(f"tags exceeds {_MAX_TAGS} items ({len(value)})")
    for tag in value:
        if len(tag) > _MAX_TAG:
            raise ValidationError(f"tag exceeds {_MAX_TAG} characters ({len(tag)})")
    return value


def validate_limit(
    value: int, *, default: int = _DEFAULT_LIMIT, maximum: int = _MAX_LIMIT
) -> int:
    if value < 1 or value > maximum:
        raise ValidationError(f"limit must be between 1 and {maximum} ({value})")
    return value


DEFAULT_LIMIT = _DEFAULT_LIMIT
MAX_LIMIT = _MAX_LIMIT
