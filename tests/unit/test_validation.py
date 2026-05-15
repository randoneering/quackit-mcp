from __future__ import annotations

import pytest

from quackit._validation import (
    ValidationError,
    validate_content,
    validate_name,
    validate_query,
    validate_tags,
)


def test_validate_content_ok() -> None:
    assert validate_content("hello") == "hello"


def test_validate_content_empty() -> None:
    with pytest.raises(ValidationError, match="content must not be empty"):
        validate_content("")


def test_validate_content_too_long() -> None:
    with pytest.raises(ValidationError, match="content exceeds"):
        validate_content("x" * 100_001)


def test_validate_query_ok() -> None:
    assert validate_query("search term") == "search term"


def test_validate_query_too_long() -> None:
    with pytest.raises(ValidationError, match="query exceeds"):
        validate_query("x" * 501)


def test_validate_name_ok() -> None:
    assert validate_name("my-project") == "my-project"


def test_validate_name_empty() -> None:
    with pytest.raises(ValidationError, match="name must not be empty"):
        validate_name("")


def test_validate_name_too_long() -> None:
    with pytest.raises(ValidationError, match="name exceeds"):
        validate_name("x" * 201)


def test_validate_tags_ok() -> None:
    assert validate_tags(["a", "b"]) == ["a", "b"]


def test_validate_tags_too_many() -> None:
    with pytest.raises(ValidationError, match="tags exceeds"):
        validate_tags(["x"] * 51)


def test_validate_tag_too_long() -> None:
    with pytest.raises(ValidationError, match="tag exceeds"):
        validate_tags(["x" * 201])
