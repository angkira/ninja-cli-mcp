"""Tests for the inline half of the ``io.modelcontextprotocol/files`` draft.

Covers the ``FileInput``/``DownloadTarget`` wire models, the ``x-mcp-file``
schema helper, the extension's advertised settings, and the validation
``decode_files`` performs: base64, declared vs decoded size, the inline budget
and the optional SHA-256 digest. Every rejection must be a
``FileArgumentError`` whose message stays free of ``data`` and of the bytes.
"""

from __future__ import annotations

import base64
import hashlib

import pytest
from pydantic import ValidationError

from ninja_common.mcp_ext.files import (
    DEFAULT_MAX_INLINE_BYTES,
    FILE_INPUT_SCHEMA,
    FILES_ENABLE_ENV,
    DownloadTarget,
    FileArgumentError,
    FileDigest,
    FileInput,
    FilesExtension,
    FilesResultMeta,
    decode_files,
    file_download_meta,
    is_enabled,
    sha256_digest,
    x_mcp_file_schema,
)
from ninja_common.mcp_ext.protocol import FILES_EXTENSION_ID


MAX_INLINE = 1024
PAYLOAD = b"the quick brown fox\n"
PAYLOAD_B64 = base64.b64encode(PAYLOAD).decode("ascii")


def inline_file(**overrides: object) -> dict[str, object]:
    """A well-formed inline ``FileInput`` argument, with optional overrides."""
    argument: dict[str, object] = {
        "id": "file-1",
        "name": "note.txt",
        "mimeType": "text/plain",
        "size": len(PAYLOAD),
        "digest": {"algorithm": "sha-256", "value": sha256_digest(PAYLOAD)},
        "data": PAYLOAD_B64,
    }
    argument.update(overrides)
    return argument


# --------------------------------------------------------------------------- #
# Wire models
# --------------------------------------------------------------------------- #


def test_file_input_parses_camel_case() -> None:
    file = FileInput.model_validate(inline_file())

    assert file.id == "file-1"
    assert file.mime_type == "text/plain"
    assert file.size == len(PAYLOAD)
    assert file.digest == FileDigest(algorithm="sha-256", value=sha256_digest(PAYLOAD))


@pytest.mark.parametrize(
    "argument",
    [
        {"id": "", "mimeType": "text/plain", "size": 0},
        {"id": "f", "mimeType": "text/plain", "size": -1},
        {"id": "f", "mimeType": "text/plain"},
        {"id": "f", "size": 0},
        {
            "id": "f",
            "mimeType": "text/plain",
            "size": 0,
            "digest": {"algorithm": "md5", "value": "x"},
        },
    ],
)
def test_file_input_rejects_bad_shapes(argument: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FileInput.model_validate(argument)


def test_download_target_requires_exactly_one_address() -> None:
    with pytest.raises(ValidationError):
        DownloadTarget(mime_type="text/csv", size=1, credentials="omit")

    with pytest.raises(ValidationError):
        DownloadTarget(
            mime_type="text/csv",
            size=1,
            url="https://example.com/a",
            path="/a",
            credentials="omit",
        )

    target = DownloadTarget(
        mime_type="text/csv", size=1, url="https://example.com/a", credentials="omit"
    )
    assert target.credentials == "omit"


# --------------------------------------------------------------------------- #
# Schema helper
# --------------------------------------------------------------------------- #


def test_file_input_schema_matches_the_draft() -> None:
    assert FILE_INPUT_SCHEMA["type"] == "object"
    assert FILE_INPUT_SCHEMA["required"] == ["id", "mimeType", "size"]
    assert FILE_INPUT_SCHEMA["properties"]["size"]["minimum"] == 0
    assert "x-mcp-file" not in FILE_INPUT_SCHEMA


def test_x_mcp_file_schema_annotates_a_fresh_object_schema() -> None:
    schema = x_mcp_file_schema(accept=["application/pdf"], max_size=2048)

    assert schema["x-mcp-file"] == {"accept": ["application/pdf"], "maxSize": 2048}
    assert schema["type"] == "object"
    assert schema["required"] == ["id", "mimeType", "size"]
    # The constant itself is never mutated.
    assert "x-mcp-file" not in FILE_INPUT_SCHEMA
    schema["properties"]["id"]["minLength"] = 9
    assert FILE_INPUT_SCHEMA["properties"]["id"]["minLength"] == 1


def test_x_mcp_file_schema_without_options_is_still_marked() -> None:
    assert x_mcp_file_schema()["x-mcp-file"] == {}


def test_x_mcp_file_schema_rejects_negative_max_size() -> None:
    with pytest.raises(ValueError, match="max_size"):
        x_mcp_file_schema(max_size=-1)


# --------------------------------------------------------------------------- #
# Extension
# --------------------------------------------------------------------------- #


def test_extension_advertises_only_the_inline_budget() -> None:
    extension = FilesExtension()

    assert extension.identifier == FILES_EXTENSION_ID
    assert extension.settings() == {"maxInlineBytes": DEFAULT_MAX_INLINE_BYTES}
    assert extension.methods() == ()
    assert extension.tools() == ()


def test_extension_accepts_a_custom_budget() -> None:
    assert FilesExtension(max_inline_bytes=4096).settings() == {"maxInlineBytes": 4096}
    with pytest.raises(ValueError, match="max_inline_bytes"):
        FilesExtension(max_inline_bytes=-1)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " On "])
def test_is_enabled_reads_the_flag(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(FILES_ENABLE_ENV, value)
    assert is_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "enabled"])
def test_is_enabled_defaults_to_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(FILES_ENABLE_ENV, value)
    assert is_enabled() is False


def test_is_enabled_is_off_without_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FILES_ENABLE_ENV, raising=False)
    assert is_enabled() is False


# --------------------------------------------------------------------------- #
# decode_files acceptance
# --------------------------------------------------------------------------- #


def test_valid_inline_file_is_accepted_and_verified() -> None:
    payload, file = decode_files({"file": inline_file()}, max_inline_bytes=MAX_INLINE)

    assert payload == PAYLOAD
    assert file.size == len(PAYLOAD)
    assert file.digest is not None
    assert file.digest.value == sha256_digest(PAYLOAD)


def test_digest_is_optional() -> None:
    argument = inline_file()
    del argument["digest"]

    payload, file = decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)

    assert payload == PAYLOAD
    assert file.digest is None


def test_zero_size_file_needs_no_data() -> None:
    argument = {"id": "empty", "mimeType": "text/plain", "size": 0}

    payload, file = decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)

    assert payload is None
    assert file.size == 0


def test_zero_size_file_accepts_an_empty_data_string() -> None:
    argument = {"id": "empty", "mimeType": "text/plain", "size": 0, "data": ""}

    payload, _ = decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)

    assert payload is None


def test_zero_size_file_still_checks_a_required_digest() -> None:
    argument = {
        "id": "empty",
        "mimeType": "text/plain",
        "size": 0,
        "digest": {"algorithm": "sha-256", "value": sha256_digest(b"")},
    }
    payload, _ = decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)
    assert payload is None

    argument["digest"] = {"algorithm": "sha-256", "value": sha256_digest(b"not empty")}
    with pytest.raises(FileArgumentError, match="digest mismatch"):
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)


def test_custom_field_name_is_honoured() -> None:
    payload, _ = decode_files(
        {"attachment": inline_file()}, max_inline_bytes=MAX_INLINE, field_name="attachment"
    )
    assert payload == PAYLOAD


# --------------------------------------------------------------------------- #
# decode_files rejection, all user-safe
# --------------------------------------------------------------------------- #


def test_missing_file_argument_is_rejected() -> None:
    with pytest.raises(FileArgumentError, match="missing required file argument"):
        decode_files({}, max_inline_bytes=MAX_INLINE)


def test_non_object_file_argument_is_rejected() -> None:
    with pytest.raises(FileArgumentError, match="must be an object"):
        decode_files({"file": "note.txt"}, max_inline_bytes=MAX_INLINE)


def test_non_empty_file_without_data_is_rejected() -> None:
    argument = inline_file()
    del argument["data"]

    with pytest.raises(FileArgumentError, match="no inline data"):
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)


def test_declared_size_over_the_budget_is_rejected() -> None:
    argument = inline_file()

    with pytest.raises(FileArgumentError, match="too large"):
        decode_files({"file": argument}, max_inline_bytes=len(PAYLOAD) - 1)


def test_decoded_size_over_the_budget_is_rejected() -> None:
    # The client understates the declared size; the decoded bytes still have to
    # fit the advertised budget.
    argument = inline_file(size=1)

    with pytest.raises(FileArgumentError, match="too large"):
        decode_files({"file": argument}, max_inline_bytes=10)

    # Within budget, the same lie is a plain size mismatch.
    with pytest.raises(FileArgumentError, match="size mismatch"):
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)


def test_size_mismatch_is_rejected() -> None:
    argument = inline_file(size=len(PAYLOAD) + 5)

    with pytest.raises(FileArgumentError, match="size mismatch"):
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)


def test_empty_data_on_a_non_empty_file_is_a_size_mismatch() -> None:
    argument = inline_file(data="")

    with pytest.raises(FileArgumentError, match="size mismatch"):
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)


def test_bad_base64_is_rejected() -> None:
    argument = inline_file(data="not*base64!!")

    with pytest.raises(FileArgumentError, match="invalid base64"):
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)


def test_digest_mismatch_is_rejected() -> None:
    argument = inline_file(digest={"algorithm": "sha-256", "value": sha256_digest(b"other")})

    with pytest.raises(FileArgumentError, match="digest mismatch"):
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)


def test_invalid_metadata_does_not_echo_values() -> None:
    argument = inline_file(size="not-a-number")

    with pytest.raises(FileArgumentError) as excinfo:
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)

    message = str(excinfo.value)
    assert "size (int_parsing)" in message
    assert PAYLOAD_B64 not in message
    assert "not-a-number" not in message


@pytest.mark.parametrize(
    "argument",
    [
        inline_file(size=len(PAYLOAD) + 1),
        inline_file(data="not*base64!!"),
        inline_file(digest={"algorithm": "sha-256", "value": sha256_digest(b"other")}),
        inline_file(size=9999),
    ],
)
def test_error_messages_never_contain_data(argument: dict[str, object]) -> None:
    with pytest.raises(FileArgumentError) as excinfo:
        decode_files({"file": argument}, max_inline_bytes=MAX_INLINE)

    message = str(excinfo.value)
    assert PAYLOAD_B64 not in message
    assert repr(PAYLOAD) not in message


# --------------------------------------------------------------------------- #
# Downloads (defined, intentionally unused)
# --------------------------------------------------------------------------- #


def test_file_download_meta_uses_the_extension_identifier() -> None:
    target = DownloadTarget(
        name="q3-orders.csv",
        mime_type="text/csv",
        size=3,
        digest=FileDigest(value=sha256_digest(b"a,b")),
        url="https://example.com/d/1",
        credentials="omit",
    )

    meta = file_download_meta([target])

    assert meta == {
        "_meta": {
            FILES_EXTENSION_ID: {
                "downloads": [
                    {
                        "name": "q3-orders.csv",
                        "mimeType": "text/csv",
                        "size": 3,
                        "digest": {"algorithm": "sha-256", "value": sha256_digest(b"a,b")},
                        "url": "https://example.com/d/1",
                        "credentials": "omit",
                    }
                ]
            }
        }
    }
    assert FilesResultMeta(downloads=[target]).downloads == [target]


def test_file_download_meta_without_targets_is_empty() -> None:
    assert file_download_meta([]) == {"_meta": {FILES_EXTENSION_ID: {"downloads": []}}}


def test_sha256_digest_is_base64url_without_padding() -> None:
    digest = sha256_digest(PAYLOAD)

    assert "=" not in digest
    assert "+" not in digest and "/" not in digest
    assert digest == base64.urlsafe_b64encode(hashlib.sha256(PAYLOAD).digest()).decode().rstrip("=")
