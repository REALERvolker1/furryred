#!/usr/bin/env python3
"""
FurryRed post-build sprite replacer.

This intentionally works from the built Radical Red ROM instead of checking
Nintendo graphics into the repository.  It keeps the game's existing palettes,
OAM and animation metadata, but replaces every vanilla human overworld graphic
and every trainer front sprite with role-aware anthropomorphic pixel art.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import struct
from pathlib import Path

ROM_BASE = 0x08000000
MAX_ROM_SIZE = 0x02000000

# US FireRed BPRE0 addresses, also exported by BPRE.ld in this project.
TRAINER_FRONT_PIC_TABLE = 0x823957C - ROM_BASE
OBJECT_GFX_INFO_POINTERS = 0x839FDB0 - ROM_BASE

TRAINER_HEADER = Path("include/constants/trainers.h")
OBJECT_HEADER = Path("include/constants/event_objects.h")

# These overrides take priority over keyword rules. They are deliberately about
# silhouette/character fit, not "random animal = furry".
NAMED_SPECIES = {
    "ARCHIE": "shark", "MAXIE": "fox", "GIOVANNI": "panther",
    "BROCK": "goat", "MISTY": "otter", "LT_SURGE": "shepherd",
    "ERIKA": "deer", "KOGA": "fox", "SABRINA": "cat",
    "BLAINE": "goat", "LORELEI": "seal", "LORLEI": "seal",
    "BRUNO": "tiger", "AGATHA": "raven", "LANCE": "dragon",
    "PROF_OAK": "owl", "OAK": "owl", "BILL": "mouse",
    "BLUE": "wolf", "RIVAL": "wolf", "WALLY": "rabbit",
    "BRENDAN": "fox", "MAY": "cat", "MOM": "collie",
    "ROXANNE": "goat", "BRAWLY": "kangaroo", "WATTSON": "shepherd",
    "FLANNERY": "fox", "NORMAN": "wolf", "WINONA": "falcon",
    "WALLACE": "otter", "GLACIA": "arctic_fox", "DRAKE": "dragon",
    "STEVEN": "silver_fox", "SIDNEY": "hyena", "PHOEBE": "fennec",
    "LIZA_AND_TATE": "fennec", "MATT": "shark", "SHELLY": "otter",
    "TABITHA": "jackal", "COURTNEY": "fox",
    "NURSE_JOY": "rabbit", "NURSE_TEALA": "rabbit",
    "SHIP_CAPTAIN": "sea_lion", "DAISY": "deer", "MR_FUJI": "red_panda",
}

# Order matters: more specific roles go first.
SPECIES_RULES = [
    (("BUG_CATCHER", "BUGCATCHER", "BUG_MANIAC"), "ferret"),
    (("HIKER", "RUIN_MANIAC"), "bear"),
    (("SWIMMER", "TUBER"), "otter"),
    (("SAILOR", "SHIP_CAPTAIN"), "sea_lion"),
    (("FISHERMAN",), "otter"),
    (("BIRD_KEEPER", "BIRDKEEPER"), "falcon"),
    (("BIKER", "CYCLING", "CYCLIST", "CUE_BALL"), "doberman"),
    (("BLACK_BELT", "CRUSH_GIRL", "CRUSH_KIN"), "tiger"),
    (("PSYCHIC", "HEX_MANIAC", "CHANNELLER", "CHANNELER"), "fennec"),
    (("SCIENTIST", "SUPER_NERD"), "mouse"),
    (("ROCKET",), "hyena"),
    (("AQUA",), "shark"),
    (("MAGMA",), "jackal"),
    (("AROMA", "PICNICKER", "PARASOL"), "deer"),
    (("CAMPER",), "coyote"),
    (("YOUNGSTER", "LITTLE_BOY", "SCHOOL_BOY", "NINJA_BOY"), "rabbit"),
    (("LASS", "LITTLE_GIRL", "SCHOOL_GIRL"), "cat"),
    (("TWINS",), "rabbit"),
    (("SIS_AND_BRO",), "otter"),
    (("POKEMANIAC", "POKE_MANIAC", "POKEFAN", "COLLECTOR"), "raccoon"),
    (("GENTLEMAN", "LADY", "BEAUTY", "RICH"), "red_fox"),
    (("BREEDER",), "collie"),
    (("RANGER",), "wolf"),
    (("GUITARIST", "ROCKER"), "coyote"),
    (("BURGLAR",), "raccoon"),
    (("JUGGLER", "PAINTER"), "cat"),
    (("TAMER", "DRAGON_TAMER"), "dragon"),
    (("GAMBLER",), "fox"),
    (("WORKER",), "badger"),
    (("POLICEMAN",), "shepherd"),
    (("CHEF", "MART_CLERK", "DELIVERYMAN"), "dog"),
    (("DOCTOR", "MEDIC"), "collie"),
    (("COOLTRAINER", "EXPERT"), "wolf"),
    (("SWIMMING_TRIATHLETE",), "otter"),
    (("RUNNING_TRIATHLETE",), "cheetah"),
    (("CYCLING_TRIATHLETE",), "greyhound"),
    (("YOUNG_COUPLE", "COOL_COUPLE"), "fox"),
    (("FAT_GUY",), "bear"),
    (("OLD_MAN", "OLD_WOMAN", "MIDDLE_AGED"), "fox"),
]

STOCKY_WORDS = ("HIKER", "FAT_GUY", "BRUNO", "BLACK_BELT", "WORKER", "CRUSH", "NORMAN")
CHILD_WORDS = ("YOUNGSTER", "LITTLE_", "SCHOOL_", "BUG_CATCHER", "BUGCATCHER", "TUBER", "NINJA_BOY")
ATHLETIC_WORDS = ("SWIMMER", "BIKER", "CYCL", "RUNNING", "BLACK_BELT", "RANGER", "CRUSH", "BRAWLY")
ELEGANT_WORDS = ("BEAUTY", "LADY", "GENTLEMAN", "ERIKA", "SABRINA", "WALLACE", "LORELEI", "LORLEI")

POINTY = {"fox","red_fox","silver_fox","arctic_fox","fennec","wolf","coyote","jackal","hyena",
          "dog","collie","shepherd","doberman","cat","panther","tiger","cheetah","raccoon","red_panda","badger"}
ROUND = {"bear","mouse","otter","sea_lion","seal","ferret"}
LONG = {"rabbit"}
ANTLER = {"deer"}
HORN = {"goat"}
AVIAN = {"falcon","raven","owl"}
AQUATIC = {"shark"}
REPTILE = {"dragon"}
MARSUPIAL = {"kangaroo"}

def role_species(name: str) -> str:
    n = name.upper()
    for key, species in NAMED_SPECIES.items():
        if key in n:
            return species
    for words, species in SPECIES_RULES:
        if any(w in n for w in words):
            return species
    return "fox"

def role_build(name: str) -> str:
    n = name.upper()
    if any(w in n for w in CHILD_WORDS):
        return "child"
    if any(w in n for w in STOCKY_WORDS):
        return "stocky"
    if any(w in n for w in ATHLETIC_WORDS):
        return "athletic"
    if any(w in n for w in ELEGANT_WORDS):
        return "elegant"
    return "average"

def parse_trainer_pics(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    text = text.split("//Backsprites", 1)[0]
    out = {}
    pat = re.compile(r"^\s*#define\s+(TRAINER_PIC_[A-Z0-9_]+)\s+(0x[0-9A-Fa-f]+|\d+)\s*$", re.M)
    for name, num in pat.findall(text):
        out[int(num, 0)] = name[len("TRAINER_PIC_"):]
    return out

def parse_overworld_ids(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"enum\s+OverworldNPCSprites\s*\{(.*?)\};", text, re.S)
    if not m:
        raise RuntimeError("Could not find OverworldNPCSprites enum")
    out, value = {}, 0
    for raw in m.group(1).splitlines():
        line = raw.split("//", 1)[0].strip().rstrip(",")
        if not line or not line.startswith("EVENT_OBJ_GFX_"):
            continue
        if "=" in line:
            name, expr = [x.strip() for x in line.split("=", 1)]
            value = int(expr, 0)
        else:
            name = line
        out[value] = name[len("EVENT_OBJ_GFX_"):]
        value += 1
    return out

def u16(data: bytearray, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]

def s16(data: bytearray, off: int) -> int:
    return struct.unpack_from("<h", data, off)[0]

def u32(data: bytearray, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]

def p32(data: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", data, off, value)

def gba_ptr(file_off: int) -> int:
    return ROM_BASE + file_off

def rom_off(ptr: int) -> int:
    if not (ROM_BASE <= ptr < ROM_BASE + MAX_ROM_SIZE):
        raise ValueError(f"not a ROM pointer: {ptr:#x}")
    return ptr - ROM_BASE

def lz77_literal(raw: bytes) -> bytes:
    # Valid GBA BIOS LZ77 stream. Literal-only is larger than optimal but simple,
    # deterministic and still only a few hundred KiB for the whole trainer set.
    out = bytearray((0x10, len(raw) & 0xFF, (len(raw) >> 8) & 0xFF, (len(raw) >> 16) & 0xFF))
    for i in range(0, len(raw), 8):
        out.append(0)
        out.extend(raw[i:i+8])
    while len(out) & 3:
        out.append(0)
    return bytes(out)

def dims_for_frame(size: int, width: int, height: int) -> tuple[int, int]:
    if width > 0 and height > 0 and width % 8 == 0 and height % 8 == 0 and width * height // 2 == size:
        return width, height
    for w, h in ((16,32),(32,32),(16,16),(32,64),(64,64),(64,32),(32,16)):
        if w * h // 2 == size:
            return w, h
    # Last-resort tile strip. It is ugly but safe and exact.
    pixels = size * 2
    w = 8
    h = pixels // w
    if h % 8:
        raise RuntimeError(f"Unsupported object frame size {size:#x}")
    return w, h

def setpx(img, x, y, c):
    if 0 <= y < len(img) and 0 <= x < len(img[0]):
        img[y][x] = c & 0xF

def rect(img, x0, y0, x1, y1, c):
    for y in range(y0, y1):
        for x in range(x0, x1):
            setpx(img, x, y, c)

def line(img, x0, y0, x1, y1, c):
    dx, sx = abs(x1-x0), 1 if x0 < x1 else -1
    dy, sy = -abs(y1-y0), 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        setpx(img, x0, y0, c)
        if x0 == x1 and y0 == y1: break
        e2 = 2 * err
        if e2 >= dy: err += dy; x0 += sx
        if e2 <= dx: err += dx; y0 += sy

def ellipse(img, cx, cy, rx, ry, c):
    if rx <= 0 or ry <= 0: return
    for y in range(cy-ry, cy+ry+1):
        for x in range(cx-rx, cx+rx+1):
            if ((x-cx)*(x-cx))*ry*ry + ((y-cy)*(y-cy))*rx*rx <= rx*rx*ry*ry:
                setpx(img, x, y, c)

def triangle(img, a, b, cpt, color):
    # Small sprites: integer barycentric rasterizer.
    minx, maxx = min(a[0],b[0],cpt[0]), max(a[0],b[0],cpt[0])
    miny, maxy = min(a[1],b[1],cpt[1]), max(a[1],b[1],cpt[1])
    def edge(p, q, r): return (r[0]-p[0])*(q[1]-p[1]) - (r[1]-p[1])*(q[0]-p[0])
    area = edge(a,b,cpt)
    if area == 0: return
    for y in range(miny, maxy+1):
        for x in range(minx, maxx+1):
            p=(x,y); e0=edge(a,b,p); e1=edge(b,cpt,p); e2=edge(cpt,a,p)
            if (area > 0 and e0>=0 and e1>=0 and e2>=0) or (area < 0 and e0<=0 and e1<=0 and e2<=0):
                setpx(img,x,y,color)

def draw_anthro(width: int, height: int, species: str, build: str, direction: str, role: str) -> list[list[int]]:
    img = [[0 for _ in range(width)] for _ in range(height)]
    tiny = width <= 24
    cx = width // 2
    # Proportions are deliberately class-readable: children stay short/small;
    # stocky roles get broad torsos; athletic roles get long limbs.
    if tiny:
        head_y = max(5, height * 7 // 24)
        body_top = head_y + 4
        foot_y = height - 3
        head_rx, head_ry = 3, 3
        torso_half = {"child":2,"stocky":4,"athletic":3,"elegant":2}.get(build,3)
    else:
        head_y = height * 15 // 64
        body_top = height * 24 // 64
        foot_y = height * 58 // 64
        head_rx, head_ry = max(4,width//10), max(4,height//11)
        torso_half = {"child":width//11,"stocky":width//7,"athletic":width//9,"elegant":width//11}.get(build,width//9)
    if build == "child" and not tiny:
        head_y += 3; body_top += 5; foot_y -= 3

    # Tail goes behind the body.
    tail_y = body_top + max(2,(foot_y-body_top)//3)
    if species in {"fox","red_fox","silver_fox","arctic_fox","wolf","coyote","jackal","hyena","raccoon","red_panda","collie","shepherd","doberman","dog","cat","panther","tiger","cheetah","ferret","otter","badger"}:
        side = -1 if direction != "left" else 1
        line(img, cx + side*torso_half, tail_y, cx + side*(torso_half + (5 if tiny else width//7)), tail_y + (4 if tiny else height//10), 1)
        line(img, cx + side*torso_half, tail_y+1, cx + side*(torso_half + (5 if tiny else width//7)), tail_y + 1 + (4 if tiny else height//10), 2)

    # Legs / torso / outfit.
    leg_sep = 2 if tiny else max(2,width//18)
    line(img, cx-leg_sep, body_top+4, cx-leg_sep-1, foot_y, 1)
    line(img, cx+leg_sep, body_top+4, cx+leg_sep+1, foot_y, 1)
    line(img, cx-leg_sep+1, body_top+5, cx-leg_sep, foot_y-1, 4)
    line(img, cx+leg_sep-1, body_top+5, cx+leg_sep, foot_y-1, 4)
    rect(img, cx-torso_half, body_top, cx+torso_half+1, body_top + max(5,(foot_y-body_top)//2), 4)
    rect(img, cx-torso_half+1, body_top+1, cx+torso_half, body_top + max(4,(foot_y-body_top)//2)-1, 5)
    # Arms.
    arm_end_y = body_top + max(4,(foot_y-body_top)//3)
    line(img, cx-torso_half, body_top+1, cx-torso_half-(2 if tiny else width//12), arm_end_y, 1)
    line(img, cx+torso_half, body_top+1, cx+torso_half+(2 if tiny else width//12), arm_end_y, 1)

    # Head, muzzle and outline.
    ellipse(img, cx, head_y, head_rx+1, head_ry+1, 1)
    ellipse(img, cx, head_y, head_rx, head_ry, 2)

    ear_h = 4 if tiny else max(6,height//8)
    ear_w = 2 if tiny else max(3,width//16)
    if species in LONG:
        rect(img, cx-head_rx+1, head_y-head_ry-ear_h, cx-head_rx+1+ear_w, head_y-head_ry+1, 1)
        rect(img, cx+head_rx-ear_w, head_y-head_ry-ear_h, cx+head_rx, head_y-head_ry+1, 1)
        if ear_w > 1:
            rect(img, cx-head_rx+2, head_y-head_ry-ear_h+1, cx-head_rx+ear_w, head_y-head_ry, 3)
            rect(img, cx+head_rx-ear_w+1, head_y-head_ry-ear_h+1, cx+head_rx-1, head_y-head_ry, 3)
    elif species in ANTLER:
        line(img,cx-head_rx,head_y-head_ry,cx-head_rx-2,head_y-head_ry-ear_h,1)
        line(img,cx-head_rx-2,head_y-head_ry-ear_h,cx-head_rx-4,head_y-head_ry-ear_h+2,1)
        line(img,cx+head_rx,head_y-head_ry,cx+head_rx+2,head_y-head_ry-ear_h,1)
        line(img,cx+head_rx+2,head_y-head_ry-ear_h,cx+head_rx+4,head_y-head_ry-ear_h+2,1)
    elif species in HORN or species in REPTILE:
        triangle(img,(cx-head_rx,head_y-head_ry+1),(cx-head_rx,head_y-head_ry-ear_h),(cx-head_rx+ear_w+1,head_y-head_ry),1)
        triangle(img,(cx+head_rx,head_y-head_ry+1),(cx+head_rx,head_y-head_ry-ear_h),(cx+head_rx-ear_w-1,head_y-head_ry),1)
    elif species in AVIAN:
        # Feather tufts instead of mammal ears, plus beak.
        triangle(img,(cx-2,head_y-head_ry),(cx,head_y-head_ry-ear_h//2),(cx+1,head_y-head_ry),3)
        triangle(img,(cx-1,head_y+1),(cx+(4 if not tiny else 2),head_y+2),(cx-1,head_y+3),3)
    elif species in AQUATIC:
        triangle(img,(cx,head_y-head_ry),(cx+ear_w,head_y-head_ry-ear_h//2),(cx+ear_w+1,head_y-head_ry+1),3)
    elif species in ROUND:
        ellipse(img,cx-head_rx,head_y-head_ry+1,ear_w,ear_w,1)
        ellipse(img,cx+head_rx,head_y-head_ry+1,ear_w,ear_w,1)
    elif species in MARSUPIAL:
        triangle(img,(cx-head_rx,head_y-head_ry+1),(cx-head_rx-1,head_y-head_ry-ear_h),(cx-head_rx+ear_w+1,head_y-head_ry),1)
        triangle(img,(cx+head_rx,head_y-head_ry+1),(cx+head_rx+1,head_y-head_ry-ear_h),(cx+head_rx-ear_w-1,head_y-head_ry),1)
    else: # pointed mammal ears
        triangle(img,(cx-head_rx,head_y-head_ry+1),(cx-head_rx+1,head_y-head_ry-ear_h),(cx-head_rx+ear_w+2,head_y-head_ry),1)
        triangle(img,(cx+head_rx,head_y-head_ry+1),(cx+head_rx-1,head_y-head_ry-ear_h),(cx+head_rx-ear_w-2,head_y-head_ry),1)

    # Face direction. Palette index 6 is normally a strong/dark accent.
    eye_y = head_y - 1
    if direction == "up":
        pass
    elif direction == "left":
        setpx(img,cx-head_rx+1,eye_y,6)
        rect(img,cx-head_rx-2,head_y+1,cx-head_rx+1,head_y+3,3)
    elif direction == "right":
        setpx(img,cx+head_rx-1,eye_y,6)
        rect(img,cx+head_rx,head_y+1,cx+head_rx+3,head_y+3,3)
    else:
        setpx(img,cx-max(1,head_rx//2),eye_y,6)
        setpx(img,cx+max(1,head_rx//2),eye_y,6)
        ellipse(img,cx,head_y+max(1,head_ry//2),max(1,head_rx//2),max(1,head_ry//3),3)
        setpx(img,cx,head_y+max(1,head_ry//2),6)

    # Role props are intentionally restrained; they make classes recognizable
    # without turning a small child class into a giant/menacing silhouette.
    r = role.upper()
    if "BUG" in r:
        # tiny bug net hoop behind shoulder
        x = max(1,cx-torso_half-(3 if tiny else width//9))
        line(img,x,body_top,x,head_y,7)
        ellipse(img,x,head_y-2,2 if tiny else 4,2 if tiny else 4,7)
    if "HIKER" in r:
        rect(img,cx-head_rx-1,head_y-head_ry-1,cx+head_rx+2,head_y-head_ry+1,7)
    if "SCIENTIST" in r or "SUPER_NERD" in r:
        setpx(img,cx-1,eye_y,7); setpx(img,cx+1,eye_y,7)
    if "NURSE" in r:
        rect(img,cx-2,head_y-head_ry-2,cx+3,head_y-head_ry,7)
        setpx(img,cx,head_y-head_ry-3,7)
    if "FISHERMAN" in r:
        line(img,cx+torso_half,body_top,cx+torso_half+(4 if tiny else width//6),max(0,head_y-ear_h),7)
    return img

def pack_4bpp(img: list[list[int]]) -> bytes:
    h, w = len(img), len(img[0])
    if w % 8 or h % 8:
        raise ValueError("dimensions must be tile aligned")
    out = bytearray()
    for ty in range(0,h,8):
        for tx in range(0,w,8):
            for y in range(8):
                for x in range(0,8,2):
                    a = img[ty+y][tx+x] & 0xF
                    b = img[ty+y][tx+x+1] & 0xF
                    out.append(a | (b << 4))
    return bytes(out)

class Allocator:
    def __init__(self, rom: bytearray, start=0x01800000):
        if len(rom) < MAX_ROM_SIZE:
            rom.extend(b"\xFF" * (MAX_ROM_SIZE - len(rom)))
        self.rom = rom
        self.pos = (start + 3) & ~3

    def put(self, blob: bytes, align=4) -> int:
        pos = (self.pos + align - 1) & ~(align - 1)
        # Find an untouched FF run. This lets the tool coexist with ROMs that
        # already use part of the high 16 MiB area.
        need = len(blob)
        while pos + need <= MAX_ROM_SIZE:
            if self.rom[pos:pos+need] == b"\xFF" * need:
                self.rom[pos:pos+need] = blob
                self.pos = pos + need
                return pos
            pos = (pos + 0x1000) & ~0xFFF
        raise RuntimeError("No free ROM space for FurryRed art layer")

def trainer_art(role: str, species: str, build: str) -> bytes:
    img = draw_anthro(64,64,species,build,"down",role)
    return pack_4bpp(img)

def object_frame(size: int, width: int, height: int, role: str, species: str, build: str, direction: str) -> bytes:
    w,h = dims_for_frame(size,width,height)
    img = draw_anthro(w,h,species,build,direction,role)
    raw = pack_4bpp(img)
    if len(raw) != size:
        raise AssertionError((role,size,w,h,len(raw)))
    return raw

def patch_trainers(rom: bytearray, alloc: Allocator, roles: dict[int,str]) -> int:
    count = 0
    for pic_id, role in sorted(roles.items()):
        entry = TRAINER_FRONT_PIC_TABLE + pic_id * 8
        if entry + 8 > len(rom):
            continue
        old_ptr = u32(rom, entry)
        if not (ROM_BASE <= old_ptr < ROM_BASE + MAX_ROM_SIZE):
            continue
        species, build = role_species(role), role_build(role)
        raw = trainer_art(role,species,build)
        data_off = alloc.put(lz77_literal(raw))
        p32(rom,entry,gba_ptr(data_off))
        count += 1
    return count

def patch_overworld(rom: bytearray, alloc: Allocator, roles: dict[int,str]) -> int:
    count = 0
    # 0-15 are player/RS player graphics. "NPC sprites" begin at LITTLE_BOY=16.
    for gfx_id, role in sorted(roles.items()):
        if gfx_id < 16:
            continue
        table_entry = OBJECT_GFX_INFO_POINTERS + gfx_id * 4
        if table_entry + 4 > len(rom):
            continue
        old_info_ptr = u32(rom,table_entry)
        if not (ROM_BASE <= old_info_ptr < ROM_BASE + MAX_ROM_SIZE):
            continue
        old_info_off = rom_off(old_info_ptr)
        if old_info_off + 0x24 > len(rom):
            continue
        info = bytearray(rom[old_info_off:old_info_off+0x24])
        frame_size = struct.unpack_from("<H",info,0x06)[0]
        width = struct.unpack_from("<h",info,0x08)[0]
        height = struct.unpack_from("<h",info,0x0A)[0]
        if frame_size == 0 or frame_size > 0x1000:
            continue

        species, build = role_species(role), role_build(role)
        frames = {}
        for d in ("down","up","left","right"):
            frames[d] = alloc.put(object_frame(frame_size,width,height,role,species,build,d), align=4)

        # Most FR human animation tables use frames grouped by facing direction.
        # 32 entries gives headroom for special animation scripts without
        # overwriting Nintendo's original image table.
        directions = []
        for d in ("down","up","left","right"):
            directions += [d]*3
        directions = (directions * 3)[:32]
        image_table = bytearray()
        for d in directions:
            image_table += struct.pack("<IHH",gba_ptr(frames[d]),frame_size,0)
        image_table_off = alloc.put(image_table,align=4)
        struct.pack_into("<I",info,0x1C,gba_ptr(image_table_off))
        new_info_off = alloc.put(info,align=4)
        p32(rom,table_entry,gba_ptr(new_info_off))
        count += 1
    return count

def manifest(roles: dict[int,str]) -> str:
    rows = ["id,name,species,build"]
    for i,name in sorted(roles.items()):
        rows.append(f"{i},{name},{role_species(name)},{role_build(name)}")
    return "\n".join(rows) + "\n"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="test.gba")
    ap.add_argument("--output", default="furryred.gba")
    ap.add_argument("--manifest-dir", default="build/furryred")
    args = ap.parse_args()

    trainer_roles = parse_trainer_pics(TRAINER_HEADER)
    ow_roles = parse_overworld_ids(OBJECT_HEADER)
    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"FurryRed: input ROM not found: {src}")
    rom = bytearray(src.read_bytes())
    alloc = Allocator(rom)

    trainers = patch_trainers(rom,alloc,trainer_roles)
    overworld = patch_overworld(rom,alloc,ow_roles)

    out = Path(args.output)
    out.write_bytes(rom)
    md = Path(args.manifest_dir)
    md.mkdir(parents=True,exist_ok=True)
    (md/"trainer_species.csv").write_text(manifest(trainer_roles),encoding="utf-8")
    (md/"overworld_species.csv").write_text(manifest(ow_roles),encoding="utf-8")
    digest = hashlib.sha256(rom).hexdigest()
    print(f"FurryRed: replaced {trainers} trainer battlers and {overworld} overworld NPC graphics")
    print(f"FurryRed: wrote {out} (sha256 {digest})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
