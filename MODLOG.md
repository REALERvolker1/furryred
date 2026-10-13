# FireRed v1.1 sprite patch

The sprite-only entry point is `scripts/furryred_v11.py`. It accepts the clean US
revision 1 ROM with SHA-1 `dd5945db9b930750cb39d00c84da8571feebf417`.
It does not run the CFRU engine insertion scripts.

## Verified ROM layout

Offsets below are file offsets, without the GBA ROM base of `0x08000000`.

| Table | Offset | Layout |
| --- | --- | --- |
| Trainer front pictures | `0x2395EC` | 148 entries, pointer/u16 size/u16 tag |
| Object graphics pointers | `0x39FE20` | 153 u32 pointers |
| Object graphics info | Through object table | 36 bytes; images pointer at +28 |
| Object frame image | Through info.images | pointer/u16 size/u16 reserved |

All 148 trainer entries were checked against their tags. IDs 31, 32, 39, and 48
reserve 4096 bytes, while other entries reserve 2048 bytes. The generated image
fills the declared size for both cases.

Object IDs 0 through 15 are player states and remain untouched. Human NPCs are
IDs 16 through 91. The original CFRU enum ends at Mom, ID 88; the v1.1 path adds
Celio, Teachy TV host, and gym guide, and corrects renamed vanilla role IDs.
IDs 92 through 152 remain untouched.

The original frame tables and metadata were inspected in the supplied ROM.
Frame count is bounded by the next image-table pointer and stops at padding or
non-image data. Vanilla facing indices are 0=south, 1=north, 2=west. East uses
the west frames with a horizontal flip. Walking indices 3/4, 5/6, and 7/8
correspond to south, north, and west respectively.

Source references for the layouts and IDs:

- [pret object graphics pointers](https://github.com/pret/pokefirered/blob/master/src/data/object_events/object_event_graphics_info_pointers.h)
- [pret object animations](https://github.com/pret/pokefirered/blob/master/src/data/object_events/object_event_anims.h)
- [pret object graphics metadata](https://github.com/pret/pokefirered/blob/master/src/data/object_events/object_event_graphics_info.h)
- [pret object frame tables](https://github.com/pret/pokefirered/blob/master/src/data/object_events/object_event_pic_tables.h)

## Validation

The format tests cover rejecting incompatible ROMs and reading bounded frame
tables. Integration checks verify that only the graphics pointer tables change
inside the original ROM, non-NPC/player pointers remain unchanged, object
metadata is preserved, generated facing frames match the declared species, and
compressed trainer sizes match their original allocations.

Five focused tests and the private-ROM integration checks passed. The existing
sprite-generator checks and strict mypy checks for the two new scripts passed.
Two builds with different Python hash seeds produced identical SHA-256
`6903b880addf3b0149751824e3914fb9c0fe4d27851608b22188ee3f9d8aecac`.

mGBA 0.10.5 under Xvfb rendered the patched ROM's opening, Mom's downstairs
sprite, and Oak/rival sprites in the lab. The first rival battle displayed the
replacement wolf trainer front picture at 60 fps, then loaded Bulbasaur and
Charmander with HP bars. Keyboard input drove the GUI opening; a local mGBA
core helper advanced the remaining lab dialogue and saved the battle scene,
which was also loaded and observed in the Xvfb GUI. Screenshots and the input
replay are in `build/verification-v1.1/`.

Runtime checks cover these opening scenes, not every NPC or late-game area.
The full table pass is checked structurally. Existing generated artwork and
its static walking poses are retained; intro portraits are outside this patch.

Local emulator screenshots, saves, logs, and extracted research files stay in
ignored paths. No ROM or extracted Nintendo assets are tracked.
