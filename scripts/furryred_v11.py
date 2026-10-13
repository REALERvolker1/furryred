#!/usr/bin/env python3
"""Apply the FurryRed artwork to a clean US FireRed revision 1 ROM."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

import furryred_patch as art

BASE_SHA1 = "dd5945db9b930750cb39d00c84da8571feebf417"
# Verified against the revision 1 ROM and pret/pokefirered table layouts.
TRAINER_TABLE = 0x2395EC
OBJECT_TABLE = 0x39FE20
OBJECT_COUNT = 153
INFO_SIZE = 0x24
IMAGES_OFFSET = 0x1C
# East animations mirror the west frames, including walking poses.
FRAME_DIRECTIONS = ("down", "up", "left", "down", "down", "up", "up", "left", "left")


def validate_base(rom: bytes) -> None:
    if hashlib.sha1(rom).hexdigest() != BASE_SHA1:
        raise ValueError("Expected a clean US FireRed v1.1 ROM, SHA-1 " + BASE_SHA1)


def validate_paths(source: Path, output: Path) -> None:
    # Resolve symlinks and also reject hardlinks, which could overwrite the base.
    if source.resolve() == output.resolve() or (
        output.exists() and source.samefile(output)
    ):
        raise ValueError("Input and output must be different files")


def npc_roles() -> dict[int, str]:
    roles = art.parse_overworld_ids(art.OBJECT_HEADER)
    # The CFRU header renames several vanilla objects and omits the last NPCs.
    roles.update(
        {
            47: "WORKER_M",
            48: "WORKER_F",
            52: "POKEMANIAC",
            89: "CELIO",
            90: "TEACHY_TV_HOST",
            91: "GYM_GUY",
        }
    )
    return {i: role for i, role in roles.items() if 16 <= i < 92}


def frame_count(rom: bytearray, table: int, limit: int, size: int) -> int:
    count = 0
    for offset in range(table, min(limit, table + 32 * 8), 8):
        ptr, frame_size, reserved = struct.unpack_from("<IHH", rom, offset)
        if (
            not (art.ROM_BASE <= ptr < art.ROM_BASE + len(rom))
            or frame_size != size
            or reserved
        ):
            break
        count += 1
    if count == 0:
        raise ValueError(f"Invalid NPC image table at {table:#x}")
    return count


def patch_trainers(
    rom: bytearray, allocator: art.Allocator, roles: dict[int, str]
) -> None:
    for pic_id, role in sorted(roles.items()):
        entry = TRAINER_TABLE + pic_id * 8
        ptr, size, tag = struct.unpack_from("<IHH", rom, entry)
        if (
            not (art.ROM_BASE <= ptr < art.ROM_BASE + len(rom))
            or tag != pic_id
            or size not in (0x800, 0x1000)
        ):
            raise ValueError(f"Invalid trainer entry {pic_id}")
        raw = art.trainer_art(role, art.role_species(role), art.role_build(role))
        # Duo trainer entries reserve two 64x64 frames. Fill both, retaining size.
        raw *= size // len(raw)
        art.p32(rom, entry, art.gba_ptr(allocator.put(art.lz77_literal(raw))))


def patch_npcs(rom: bytearray, allocator: art.Allocator, roles: dict[int, str]) -> None:
    infos = [
        art.rom_off(art.u32(rom, OBJECT_TABLE + i * 4)) for i in range(OBJECT_COUNT)
    ]
    image_tables = sorted(
        {art.rom_off(art.u32(rom, info + IMAGES_OFFSET)) for info in infos}
    )
    for gfx_id, role in sorted(roles.items()):
        info = bytearray(rom[infos[gfx_id] : infos[gfx_id] + INFO_SIZE])
        size, width, height = struct.unpack_from("<Hhh", info, 6)
        table = art.rom_off(art.u32(info, IMAGES_OFFSET))
        index = image_tables.index(table)
        limit = image_tables[index + 1] if index + 1 < len(image_tables) else len(rom)
        count = frame_count(rom, table, limit, size)
        species, body = art.role_species(role), art.role_build(role)
        frames = {
            direction: allocator.put(
                art.object_frame(size, width, height, role, species, body, direction)
            )
            for direction in ("down", "up", "left")
        }
        # Retain the frame-table length and all OAM/palette/animation metadata.
        images = bytearray()
        for frame in range(count):
            direction = FRAME_DIRECTIONS[frame % len(FRAME_DIRECTIONS)]
            images.extend(struct.pack("<IHH", art.gba_ptr(frames[direction]), size, 0))
        art.p32(info, IMAGES_OFFSET, art.gba_ptr(allocator.put(bytes(images))))
        art.p32(rom, OBJECT_TABLE + gfx_id * 4, art.gba_ptr(allocator.put(bytes(info))))


def patch_rom(source: bytes) -> bytearray:
    validate_base(source)
    rom = bytearray(source)
    allocator = art.Allocator(rom)
    patch_trainers(rom, allocator, art.parse_trainer_pics(art.TRAINER_HEADER))
    patch_npcs(rom, allocator, npc_roles())
    return rom


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("furryred-v1.1.gba"))
    parser.add_argument(
        "--manifest-dir", type=Path, default=Path("build/furryred-v1.1")
    )
    args = parser.parse_args()
    source: Path = args.input
    output: Path = args.output
    manifest_dir: Path = args.manifest_dir
    try:
        validate_paths(source, output)
        rom = patch_rom(source.read_bytes())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    output.write_bytes(rom)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    trainers = art.parse_trainer_pics(art.TRAINER_HEADER)
    (manifest_dir / "trainer_species.csv").write_text(
        art.manifest(trainers), encoding="utf-8"
    )
    (manifest_dir / "overworld_species.csv").write_text(
        art.manifest(npc_roles()), encoding="utf-8"
    )
    print(
        f"FurryRed v1.1: replaced {len(trainers)} trainer pictures and {len(npc_roles())} NPC graphics"
    )
    print(f"Wrote {output}, SHA-256 {hashlib.sha256(rom).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
