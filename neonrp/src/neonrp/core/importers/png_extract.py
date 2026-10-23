"""PNG chunk reader for extracting embedded character card data.

Extracts Base64-encoded JSON from the ``tEXt`` chunk with keyword ``chara``.
This is the format used by SillyTavern PNG character cards.

No Pillow or other image library dependencies required.
"""

import base64
import json
import struct
from pathlib import Path
from typing import Any

# PNG magic bytes
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PNGExtractionError(Exception):
    """Error during PNG character card extraction."""

    pass


def extract_chara_from_png(file_path: Path | str) -> dict[str, Any]:
    """Extract character card JSON from a SillyTavern PNG file.

    The PNG file must contain a ``tEXt`` chunk with keyword ``chara``
    and a Base64-encoded JSON value.

    Args:
        file_path: Path to the PNG file.

    Returns:
        Parsed JSON dict from the ``chara`` tEXt chunk.

    Raises:
        PNGExtractionError: If the file is not a valid PNG, has no
            ``chara`` chunk, or the chunk data is not valid Base64/JSON.
    """
    file_path = Path(file_path)

    with open(file_path, "rb") as f:
        # Verify PNG signature
        signature = f.read(8)
        if signature != PNG_SIGNATURE:
            raise PNGExtractionError(f"Not a valid PNG file: {file_path}")

        # Read chunks until we find tEXt with keyword 'chara' or hit IEND
        while True:
            # Each chunk: 4 bytes length + 4 bytes type + data + 4 bytes CRC
            header = f.read(8)
            if len(header) < 8:
                break  # EOF

            length = struct.unpack(">I", header[:4])[0]
            chunk_type = header[4:8]

            if chunk_type == b"IEND":
                break

            # Read chunk data
            data = f.read(length)
            if len(data) < length:
                raise PNGExtractionError("Truncated PNG file")

            # Skip CRC
            f.read(4)

            # Check for tEXt chunk
            if chunk_type == b"tEXt":
                # tEXt format: keyword\x00value
                null_idx = data.find(b"\x00")
                if null_idx == -1:
                    continue

                keyword = data[:null_idx].decode("latin-1")
                value = data[null_idx + 1 :]

                if keyword == "chara":
                    # Decode Base64 and parse JSON
                    try:
                        decoded = base64.b64decode(value)
                        return json.loads(decoded.decode("utf-8"))
                    except base64.binascii.Error as e:
                        raise PNGExtractionError(f"Invalid Base64 in 'chara' chunk: {e}")
                    except json.JSONDecodeError as e:
                        raise PNGExtractionError(f"Invalid JSON in 'chara' chunk: {e}")
                    except UnicodeDecodeError as e:
                        raise PNGExtractionError(f"Invalid UTF-8 in 'chara' chunk: {e}")

    raise PNGExtractionError(f"No 'chara' tEXt chunk found in PNG file: {file_path}")


def is_png_file(file_path: Path | str) -> bool:
    """Check if a file is a PNG by reading its magic bytes.

    Args:
        file_path: Path to the file.

    Returns:
        True if the file starts with PNG magic bytes.
    """
    file_path = Path(file_path)
    try:
        with open(file_path, "rb") as f:
            return f.read(8) == PNG_SIGNATURE
    except OSError:
        return False
