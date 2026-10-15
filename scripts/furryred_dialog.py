#!/usr/bin/env python3
"""Inject FurryRed's Oak-intro disclaimer into a built ROM."""

from __future__ import annotations
import argparse, struct
from pathlib import Path

ROM_BASE = 0x08000000
MAX_ROM_SIZE = 0x02000000
FREE_SPACE_START = 0x01F00000

ORIGINAL_OAK_TEXT = (
    "For some people, POKéMON are pets.\\n"
    "Others use them for battling.\\p"
    "As for myself…\\p"
    "I study POKéMON as a profession.\\p$"
)

FURRYRED_OAK_TEXT = (
    "For some people, POKéMON are pets.\\n"
    "Others use them for battling.\\p"
    "As for myself…\\p"
    "I study POKéMON as a profession.\\p"
    "One last thing…\\p"
    "Just try not to think too much about\\n"
    "the implications of furries owning\\p"
    "and training POKéMON.\\p"
    "You'll enjoy the journey more that way.\\p$"
)


def encode_gen3_text(text: str) -> bytes:
    """Encode the subset of FireRed's English charmap used by our intro text."""
    out = bytearray()
    punct = {
        " ": 0x00,
        "é": 0x1B,
        "!": 0xAB,
        "?": 0xAC,
        ".": 0xAD,
        "-": 0xAE,
        "…": 0xB0,
        "'": 0xB4,
        ",": 0xB8,
        "/": 0xBA,
        ":": 0xF0,
        "$": 0xFF,
    }
    controls = {r"\l": 0xFA, r"\p": 0xFB, r"\n": 0xFE}
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            token = text[i : i + 2]
            if token not in controls:
                raise ValueError(f"Unsupported text control {token!r}")
            out.append(controls[token])
            i += 2
            continue

        ch = text[i]
        if "A" <= ch <= "Z":
            out.append(0xBB + ord(ch) - ord("A"))
        elif "a" <= ch <= "z":
            out.append(0xD5 + ord(ch) - ord("a"))
        elif "0" <= ch <= "9":
            out.append(0xA1 + ord(ch) - ord("0"))
        elif ch in punct:
            out.append(punct[ch])
        else:
            raise ValueError(f"Unsupported FireRed text character {ch!r}")
        i += 1

    if not out or out[-1] != 0xFF:
        raise ValueError("Gen III strings must end with '$' (0xFF)")
    return bytes(out)


def find_all(haystack: bytes | bytearray, needle: bytes) -> list[int]:
    hits: list[int] = []
    start = 0
    while True:
        pos = haystack.find(needle, start)
        if pos < 0:
            return hits
        hits.append(pos)
        start = pos + 1


def find_free_space(rom: bytearray, size: int, start: int = FREE_SPACE_START) -> int:
    """Find an aligned all-0xFF run near the high end of a 32 MiB ROM."""
    if size <= 0:
        raise ValueError("Allocation size must be positive")

    pos = (start + 3) & ~3
    limit = len(rom) - size
    free_run = b"\xFF" * size
    while pos <= limit:
        if rom[pos : pos + size] == free_run:
            return pos
        pos += 4

    raise RuntimeError(
        f"Could not find {size} bytes of free space at/after 0x{start:X}"
    )


def patch_oak_intro(rom: bytearray) -> tuple[int, list[int]]:
    original = encode_gen3_text(ORIGINAL_OAK_TEXT)
    replacement = encode_gen3_text(FURRYRED_OAK_TEXT)

    text_hits = find_all(rom, original)
    if len(text_hits) != 1:
        raise RuntimeError(
            "Expected exactly one stock Oak 'I study POKéMON' string, "
            f"found {len(text_hits)}. Refusing to guess."
        )

    old_text_offset = text_hits[0]
    old_pointer = struct.pack("<I", ROM_BASE + old_text_offset)

    # ARM/Thumb literal-pool and pointer-table entries are word-aligned.
    pointer_hits = [
        pos for pos in find_all(rom, old_pointer) if pos % 4 == 0
    ]
    if not pointer_hits:
        raise RuntimeError(
            "Found Oak's text but no aligned references to it. Refusing to "
            "patch an unknown ROM layout."
        )

    new_text_offset = find_free_space(rom, len(replacement))
    rom[new_text_offset : new_text_offset + len(replacement)] = replacement
    new_pointer = struct.pack("<I", ROM_BASE + new_text_offset)

    for pos in pointer_hits:
        rom[pos : pos + 4] = new_pointer

    return new_text_offset, pointer_hits


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add FurryRed's disclaimer to Professor Oak's opening speech."
    )
    parser.add_argument(
        "--rom",
        default="furryred.gba",
        help="Built ROM to patch in place (default: furryred.gba)",
    )
    args = parser.parse_args()

    rom_path = Path(args.rom)
    data = bytearray(rom_path.read_bytes())
    if len(data) < MAX_ROM_SIZE:
        data.extend(b"\xFF" * (MAX_ROM_SIZE - len(data)))

    new_text_offset, pointer_hits = patch_oak_intro(data)
    rom_path.write_bytes(data)

    print(
        "Added FurryRed Oak-intro disclaimer at "
        f"0x{ROM_BASE + new_text_offset:08X}; "
        f"repointed {len(pointer_hits)} reference(s)."
    )


if __name__ == "__main__":
    main()
