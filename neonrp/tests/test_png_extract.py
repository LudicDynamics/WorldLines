"""Tests for PNG character card extraction."""

import base64
import json
import struct
import pytest
from pathlib import Path

from neonrp.core.importers.png_extract import (
    extract_chara_from_png,
    is_png_file,
    PNGExtractionError,
    PNG_SIGNATURE,
)


def _build_png_with_chara(card_json: dict) -> bytes:
    """Build a minimal valid PNG with a 'chara' tEXt chunk."""
    # Encode card as Base64
    json_bytes = json.dumps(card_json).encode("utf-8")
    base64_bytes = base64.b64encode(json_bytes)

    # Build tEXt chunk: keyword\x00value
    keyword = b"chara"
    text_data = keyword + b"\x00" + base64_bytes

    # Build IHDR chunk (minimal 1x1 image header)
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # width, height, bit depth, color type, etc.
    ihdr_crc = _crc32(b"IHDR" + ihdr_data)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # Build tEXt chunk
    text_crc = _crc32(b"tEXt" + text_data)
    text_chunk = struct.pack(">I", len(text_data)) + b"tEXt" + text_data + struct.pack(">I", text_crc)

    # Build minimal IDAT (empty compressed data)
    idat_data = b"\x08\xd7\x63\x00\x00\x00\x01\x00\x01"  # zlib deflate of single pixel
    idat_crc = _crc32(b"IDAT" + idat_data)
    idat_chunk = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + struct.pack(">I", idat_crc)

    # Build IEND chunk
    iend_crc = _crc32(b"IEND")
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return PNG_SIGNATURE + ihdr_chunk + text_chunk + idat_chunk + iend_chunk


def _crc32(data: bytes) -> int:
    """Compute CRC32 as unsigned int."""
    import zlib

    return zlib.crc32(data) & 0xFFFFFFFF


class TestIsPngFile:
    def test_valid_png(self, tmp_path: Path):
        png_file = tmp_path / "test.png"
        png_file.write_bytes(PNG_SIGNATURE + b"dummy")
        assert is_png_file(png_file) is True

    def test_not_png_json(self, tmp_path: Path):
        json_file = tmp_path / "test.json"
        json_file.write_text('{"name": "Test"}', encoding="utf-8")
        assert is_png_file(json_file) is False

    def test_not_png_empty(self, tmp_path: Path):
        empty_file = tmp_path / "empty.bin"
        empty_file.write_bytes(b"")
        assert is_png_file(empty_file) is False

    def test_missing_file(self, tmp_path: Path):
        missing = tmp_path / "missing.png"
        assert is_png_file(missing) is False


class TestExtractCharaFromPng:
    def test_extract_v2_card(self, tmp_path: Path):
        card = {
            "spec": "chara_card_v2",
            "data": {
                "name": "Test Character",
                "description": "A test character",
                "personality": "Friendly",
                "tags": ["test", "demo"],
            },
        }
        png_bytes = _build_png_with_chara(card)
        png_file = tmp_path / "card.png"
        png_file.write_bytes(png_bytes)

        result = extract_chara_from_png(png_file)
        assert result["data"]["name"] == "Test Character"
        assert result["data"]["personality"] == "Friendly"

    def test_extract_v1_card(self, tmp_path: Path):
        card = {
            "name": "Flat Character",
            "description": "V1 format",
            "tags": [],
        }
        png_bytes = _build_png_with_chara(card)
        png_file = tmp_path / "card_v1.png"
        png_file.write_bytes(png_bytes)

        result = extract_chara_from_png(png_file)
        assert result["name"] == "Flat Character"

    def test_not_png_raises(self, tmp_path: Path):
        json_file = tmp_path / "card.json"
        json_file.write_text('{"name": "Test"}', encoding="utf-8")

        with pytest.raises(PNGExtractionError, match="Not a valid PNG"):
            extract_chara_from_png(json_file)

    def test_no_chara_chunk_raises(self, tmp_path: Path):
        # Build PNG without tEXt chunk
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = _crc32(b"IHDR" + ihdr_data)
        ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        iend_crc = _crc32(b"IEND")
        iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        png_bytes = PNG_SIGNATURE + ihdr_chunk + iend_chunk

        png_file = tmp_path / "no_chara.png"
        png_file.write_bytes(png_bytes)

        with pytest.raises(PNGExtractionError, match="No 'chara' tEXt chunk"):
            extract_chara_from_png(png_file)

    def test_truncated_png_raises(self, tmp_path: Path):
        # Write just the signature and partial header
        png_file = tmp_path / "truncated.png"
        png_file.write_bytes(PNG_SIGNATURE + b"\x00\x00\x00\x0dIHDR")  # Partial IHDR

        with pytest.raises(PNGExtractionError, match="Truncated PNG"):
            extract_chara_from_png(png_file)

    def test_invalid_base64_raises(self, tmp_path: Path):
        # Build PNG with invalid base64 in chara chunk
        keyword = b"chara"
        text_data = keyword + b"\x00" + b"not-valid-base64!!!"

        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = _crc32(b"IHDR" + ihdr_data)
        ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

        text_crc = _crc32(b"tEXt" + text_data)
        text_chunk = struct.pack(">I", len(text_data)) + b"tEXt" + text_data + struct.pack(">I", text_crc)

        iend_crc = _crc32(b"IEND")
        iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

        png_bytes = PNG_SIGNATURE + ihdr_chunk + text_chunk + iend_chunk
        png_file = tmp_path / "bad_base64.png"
        png_file.write_bytes(png_bytes)

        with pytest.raises(PNGExtractionError, match="Invalid Base64"):
            extract_chara_from_png(png_file)

    def test_invalid_json_raises(self, tmp_path: Path):
        # Build PNG with valid base64 but invalid JSON
        keyword = b"chara"
        invalid_json_b64 = base64.b64encode(b"not valid json {{{")
        text_data = keyword + b"\x00" + invalid_json_b64

        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = _crc32(b"IHDR" + ihdr_data)
        ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

        text_crc = _crc32(b"tEXt" + text_data)
        text_chunk = struct.pack(">I", len(text_data)) + b"tEXt" + text_data + struct.pack(">I", text_crc)

        iend_crc = _crc32(b"IEND")
        iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

        png_bytes = PNG_SIGNATURE + ihdr_chunk + text_chunk + iend_chunk
        png_file = tmp_path / "bad_json.png"
        png_file.write_bytes(png_bytes)

        with pytest.raises(PNGExtractionError, match="Invalid JSON"):
            extract_chara_from_png(png_file)
