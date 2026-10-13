#!/usr/bin/env python3
"""Focused format checks, with optional integration checks on a private ROM."""

from __future__ import annotations

import argparse
import struct
import tempfile
import unittest
from pathlib import Path

import furryred_patch as art
import furryred_v11 as patch


class FormatTests(unittest.TestCase):
    def test_hardlinked_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "base.gba"
            output = Path(directory) / "output.gba"
            source.write_bytes(b"private ROM")
            output.hardlink_to(source)
            with self.assertRaisesRegex(ValueError, "different files"):
                patch.validate_paths(source, output)
            self.assertEqual(source.read_bytes(), b"private ROM")

    def test_wrong_revision_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "clean US FireRed v1.1"):
            patch.patch_rom(bytes(0xC0))

    def test_frame_table_stops_at_next_table(self) -> None:
        rom = bytearray(64)
        for offset in (0, 8, 16):
            struct.pack_into("<IHH", rom, offset, art.ROM_BASE + 32, 128, 0)
        self.assertEqual(patch.frame_count(rom, 0, 16, 128), 2)

    def test_frame_table_stops_at_padding(self) -> None:
        rom = bytearray(64)
        struct.pack_into("<IHH", rom, 0, art.ROM_BASE + 32, 128, 0)
        self.assertEqual(patch.frame_count(rom, 0, 64, 128), 1)

    def test_empty_frame_table_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid NPC image table"):
            patch.frame_count(bytearray(64), 0, 64, 128)


def check_rom(path: Path) -> None:
    source = path.read_bytes()
    result = patch.patch_rom(source)
    assert len(result) == art.MAX_ROM_SIZE
    # The private base ROM must differ only in the two pointer tables.
    restored = bytearray(result[: len(source)])
    for start, length in (
        (patch.TRAINER_TABLE, 148 * 8),
        (patch.OBJECT_TABLE, 153 * 4),
    ):
        restored[start : start + length] = source[start : start + length]
    assert restored == source, "Unexpected change outside graphics pointer tables"
    original = bytearray(source)
    roles = patch.npc_roles()
    for gfx_id in range(patch.OBJECT_COUNT):
        entry = patch.OBJECT_TABLE + gfx_id * 4
        old_ptr, new_ptr = art.u32(original, entry), art.u32(result, entry)
        if gfx_id not in roles:
            assert new_ptr == old_ptr, f"Non-NPC {gfx_id} changed"
            continue
        old_info = original[
            art.rom_off(old_ptr) : art.rom_off(old_ptr) + patch.INFO_SIZE
        ]
        new_info = result[art.rom_off(new_ptr) : art.rom_off(new_ptr) + patch.INFO_SIZE]
        assert new_info[: patch.IMAGES_OFFSET] == old_info[: patch.IMAGES_OFFSET]
        assert (
            new_info[patch.IMAGES_OFFSET + 4 :] == old_info[patch.IMAGES_OFFSET + 4 :]
        )
        size, width, height = struct.unpack_from("<Hhh", new_info, 6)
        images = art.rom_off(art.u32(new_info, patch.IMAGES_OFFSET))
        role = roles[gfx_id]
        for i, direction in enumerate(patch.FRAME_DIRECTIONS[:3]):
            frame = art.rom_off(art.u32(result, images + i * 8))
            expected = art.object_frame(
                size,
                width,
                height,
                role,
                art.role_species(role),
                art.role_build(role),
                direction,
            )
            assert result[frame : frame + size] == expected, (gfx_id, direction)
    for pic_id in range(148):
        entry = patch.TRAINER_TABLE + pic_id * 8
        assert result[entry + 4 : entry + 8] == source[entry + 4 : entry + 8]
        frame = art.rom_off(art.u32(result, entry))
        size = art.u16(original, entry + 4)
        assert result[frame] == 0x10
        assert int.from_bytes(result[frame + 1 : frame + 4], "little") == size
    assert path.read_bytes() == source, "Input ROM changed"
    print(
        "ROM integration checks passed: 148 trainers, 76 NPCs, unchanged gameplay/player/non-NPC data"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner().run(
        unittest.defaultTestLoader.loadTestsFromTestCase(FormatTests)
    )
    if not result.wasSuccessful():
        return 1
    rom_path: Path | None = args.rom
    if rom_path is not None:
        check_rom(rom_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
