#!/usr/bin/env python3
"""ROM-free sanity checks for the FurryRed sprite generator."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name("furryred_patch.py")
spec = importlib.util.spec_from_file_location("furryred_patch", str(SCRIPT))
furryred = importlib.util.module_from_spec(spec)
spec.loader.exec_module(furryred)


def main():
    trainers = furryred.parse_trainer_pics(furryred.TRAINER_HEADER)
    overworld = furryred.parse_overworld_ids(furryred.OBJECT_HEADER)

    assert trainers, "no trainer picture ids parsed"
    assert overworld, "no overworld ids parsed"

    # Regression tests for the role-aware design rules.
    assert furryred.role_species("BUG_CATCHER") == "ferret"
    assert furryred.role_build("BUG_CATCHER") == "child"
    assert furryred.role_species("HIKER") == "bear"
    assert furryred.role_build("HIKER") == "stocky"
    assert furryred.role_species("SWIMMER_M") == "otter"
    assert furryred.role_species("BIKER") == "doberman"
    assert furryred.role_species("SCIENTIST_M") == "mouse"
    assert furryred.role_species("NURSE_JOY") == "rabbit"

    # Every parsed trainer role must produce one exact 64x64 4bpp frame.
    for role in trainers.values():
        raw = furryred.trainer_art(
            role,
            furryred.role_species(role),
            furryred.role_build(role),
        )
        assert len(raw) == 0x800, (role, len(raw))
        packed = furryred.lz77_literal(raw)
        assert packed[0] == 0x10
        assert int.from_bytes(packed[1:4], "little") == 0x800

    # Exercise common FireRed object-event frame shapes in all directions.
    for size, width, height in ((0x100, 16, 32), (0x200, 32, 32), (0x80, 16, 16)):
        for role in overworld.values():
            if role.startswith(("RED_", "LEAF_", "BRENDAN", "MAY")):
                continue
            species = furryred.role_species(role)
            build = furryred.role_build(role)
            for direction in ("down", "up", "left", "right"):
                raw = furryred.object_frame(size, width, height, role, species, build, direction)
                assert len(raw) == size, (role, direction, len(raw), size)

    print("FurryRed generator sanity checks passed")
    print("trainer picture ids:", len(trainers))
    print("overworld ids:", len(overworld))


if __name__ == "__main__":
    main()
