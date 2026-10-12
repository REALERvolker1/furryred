# Pokémon FurryRed

FurryRed is a visual conversion layer for this Radical Red source tree. It replaces human NPC overworld graphics and trainer battle front sprites with original anthropomorphic pixel art while preserving the roles and silhouettes that make trainer classes readable.

## Design rules

The conversion is role-aware rather than random. Species, body type, age, and small visual props are selected from the original character or trainer archetype.

Examples:

- Bug Catcher: ferret, child-sized/light build, bug net.
- Youngster: rabbit, child-sized build.
- Hiker: bear, stocky build, hiking hat.
- Swimmer/Tuber: otter, athletic/child build as appropriate.
- Biker/Cue Ball: doberman, athletic build.
- Fisherman: otter, fishing rod.
- Scientist/Super Nerd: mouse, glasses.
- Bird Keeper: falcon.
- Black Belt: tiger, athletic/stocky build.
- Rocket Grunt: hyena.
- Nurse Joy: rabbit, nurse cap.

Named characters also have explicit mappings instead of falling through to the generic rules. Examples include Misty as an otter, Brock as a goat, Sabrina as a cat, Lance as a dragon, Giovanni as a panther, Professor Oak as an owl, and Blue/the rival as a wolf.

The mapping logic lives in `scripts/furryred_patch.py`. The generated CSV manifests in `build/furryred/` show the selected species and build for every parsed trainer and overworld role.

## How it works

The old Radical Red/CFRU source tree does not contain source PNGs for most vanilla FireRed NPCs. FurryRed therefore runs after the normal engine insertion step:

1. Radical Red builds `test.gba` from the user's own `BPRE0.gba`.
2. `scripts/furryred_patch.py` reads the vanilla FireRed trainer and overworld graphics tables already present in the built ROM.
3. It generates original 4bpp anthropomorphic sprite data, places it in unused high ROM space, and repoints human entries only.
4. Existing palettes, OAM settings, animation metadata, shadows, reflections, and other engine behavior remain in place.
5. The final output is `furryred.gba`.

No base ROM or Nintendo sprite sheets are checked into this repository.

## Build

Put the same `BPRE0.gba` expected by the existing Radical Red build in the repository root, then run:

```sh
python3 scripts/make.py
```

The normal build still produces `test.gba`; the FurryRed post-build stage additionally produces `furryred.gba`.

For ROM-free generator checks:

```sh
python3 scripts/test_furryred_patch.py
```

## Scope

The patcher covers the FireRed/Radical Red trainer front-picture table and the human NPC entries in the base overworld graphics table. Player overworld states are intentionally excluded from the NPC pass, while trainer pictures named as player pictures in the trainer table are still converted like other battle-facing trainer art.

Pokémon, item balls, signs, rocks, and other non-human field objects are not modified.

## Art direction

The current artwork is deliberately generated as a consistent first-pass GBA pixel-art set. It is data-driven, so individual classes or named characters can later be replaced with hand-drawn PNG-derived art without changing the role mapping or ROM-table plumbing.
