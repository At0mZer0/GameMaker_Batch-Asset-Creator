# GameMaker_Batch-Asset-Creator

Two tools in one tkinter app for GameMaker Studio 2 (.yyp) projects.

## Batch Assets tab

Adds all sprites and / or objects to a GameMaker project from a folder source.

## Room Atlas Packer tab

Pick a project directory on the Batch Assets tab, choose a room, and press
**Pack Room Atlases**. The tool:

**First pass** collects what the room file itself says is drawn:

1. Placed object instances, walking nested layers, resolved to the sprite each
   object draws by following the parentObjectId chain.
2. Sprites named by overridden instance properties.
3. Sprites placed straight onto asset layers, e.g. `z48_Spr_Cliffs`.
4. Background layer sprites, and the sprite behind each tileset when
   **Ignore tilesets** is switched off.

**Second pass** finds what only the code knows about, starting from every object
placed in the room:

1. Reads each object event .gml plus its parents, and its variable definitions,
   with comments stripped so a commented out name is not counted.
2. Any token that matches a sprite resource name is included. That covers
   `sprite_index = sprTree`, `choose(sprA, sprB)` and variant arrays such as
   `VARIANTS.FOOD_NODE = [[3, 5, spr_resource_food_bush_01, ...]]`.
3. Any token that matches an object is followed, so sprites belonging to objects
   created at runtime with `instance_create_layer` are picked up too.
4. Any token that matches a `#macro` or function is followed into the script that
   declares it, which is how `oResourceFood` reaches the lists in `item_s`.

Then:

3. Sprites are grouped in GameMaker draw order: highest layer depth first, then
   by a coarse room grid (default 256 px cells) within each layer, so sprites
   drawn one after the other land on the same page and the frame binds fewer
   texture pages. Set **Order Pages By** to `position` to ignore layers and use
   the room grid alone. A sprite found only in code takes the position and depth
   of the object that referenced it; anything with no position at all, such as a
   background, is packed last.
4. Packs them into 4096 x 4096 texture pages with a skyline bin packer, in that
   grouped order, so assets that are near each other in the room end up on the
   same page. All frames of an animation stay contiguous and in frame order.
5. Writes the results to `<project>/packed_atlases/<room>/` by default.

### Output

| File | Contents |
| --- | --- |
| `<room>_page_<n>.png` | One texture page per page used |
| `<room>_atlas.json` | Every sprite frame with its page, rectangle and origin |
| `<room>_pack_report.txt` | Sprites listed by where they were found, per page contents, coverage, warnings, validation result |
| `<room>_page_<n>_debug.png` | Optional preview showing block and frame bounds |

### Metadata format

```json
{
  "meta": {
    "room": "rGym_TestRoom",
    "page_size": [4096, 4096],
    "padding": 2,
    "grid_cell_size": 256,
    "rotation_allowed": false,
    "pages": ["rGym_TestRoom_page_0.png"],
    "generator": "GMS2 Object and Sprite Batch Asset Creator"
  },
  "sprites": {
    "anim_chest_med": {
      "frames": [
        { "page": 0, "x": 198, "y": 66, "w": 38, "h": 38, "frame_index": 0, "rotated": false }
      ],
      "origin": [19, 38],
      "frame_count": 5,
      "animation_length": 5,
      "texture_group": "Container",
      "objects": ["oChest"],
      "sources": ["instance"],
      "layer_name": "Instances",
      "discovered_from": ["oPortal (oPortal Create_0.gml)"],
      "room_position": [992.0, 2224.0],
      "instance_count": 1
    }
  }
}
```

`sources` says where a sprite came from: `instance`, `instance_property`,
`sprite_layer`, `background_layer`, `tileset` or `code`. `discovered_from` names
the exact file a code discovered sprite was found in. `atlas_writer.adaptForTextureGroupAdd`
flattens this into a single frame list keyed `<sprite>:<frame>` for a GML loader.

### Keeping the atlas map specific

The code scan cannot tell which branch runs, so it takes every sprite a branch
could reach. Controllers are the problem: they reach menus, loading screens and
UI art the room never draws. Two exclusion lists deal with that, both accepting
wildcards:

- **Exclude From Code Scan** object names, e.g. `*Ctrl, obj_render, *Menu`. An
  excluded object contributes nothing that only code knows about, not even its
  own sprite, and nothing it spawns is followed. If it is actually placed in the
  room its sprite still comes from the first pass, because that is a fact about
  the room.
- **Exclude Layers** layer names, e.g. `UI_*, GUI`. Everything on a matching
  layer is left out entirely, and objects on it are not code scan seeds either.

The pack report lists the objects that dragged sprites in through the code scan,
ranked by pixels, so the exclude list is discoverable rather than guesswork.
Attribution moves as you exclude: a sprite reachable from several objects is
credited to whichever one still reaches it.

Measured on `rCity_Forest`:

| Settings | Sprites | Frames | Pages |
| --- | --- | --- | --- |
| no exclusions | 1302 | 2369 | 8 |
| `--exclude-objects "oCtrl,obj_render"` | 1186 | 1818 | 3 |
| the wider list above | 1175 | 1797 | 3 |
| `--no-code-scan` | 1008 | 1582 | 2 |

### Options

- **Texture Group Name** the name passed to `texturegroup_add`, defaults to the
  room name. Checked against the texture groups already in the project, because
  `texturegroup_add` raises a fatal error on a name that already exists
- **Order Pages By** `depth` (default, GameMaker draw order) or `position`
- **Exclude From Code Scan** / **Exclude Layers** see above
- **Second pass into object code** on by default
- **Include random choice lists** on by default. Off means only direct sprite
  assignments are taken from code, so `choose(...)` and variant arrays are dropped
- **Ignore tilesets** on by default
- **Page Size** 1024 / 2048 / 4096 / 8192, default 4096
- **Padding** pixels between sprites, default 2
- **Grid Cell Size** room grid used for the proximity grouping, default 256
- **Oversize Sprites** `skip` a sprite larger than a page, or `scale` it down
- **Allow 90 degree rotation** lets a block be turned to save space, off by default
- **Include instances flagged as ignored** off by default
- **Write debug preview images** off by default

Runs are deterministic: the same room and options produce the same atlas layout.

### Command line

```
python room_atlas_builder.py "<project root>"                 # list rooms
python room_atlas_builder.py "<project root>" rGym_TestRoom   # pack a room
python room_atlas_builder.py "<project root>" rGym_TestRoom --page-size 2048 --padding 4 --debug-images
python room_atlas_builder.py "<project root>" rCity_Forest --no-code-scan
python room_atlas_builder.py "<project root>" rCity_Forest --no-random-lists --include-tilesets
python room_atlas_builder.py "<project root>" rCity_Forest \
    --group-name tg_City_Forest --order-by depth \
    --exclude-objects "*Ctrl,obj_render,*Menu" --exclude-layers "UI_*,GUI"
```

### Feeding it to texturegroup_add

The atlas json is already the struct `texturegroup_add` takes. `meta.pages` is
the file array to pass as the second argument, and each frame's `tp` indexes it.

```gml
var _pages = ["rCity_Forest_page_0.png", "rCity_Forest_page_1.png", "rCity_Forest_page_2.png"];

if (!texturegroup_exists("tg_City_Forest"))
{
    texturegroup_add("tg_City_Forest", _pages, _json);
    texturegroup_load("tg_City_Forest");
}
```

Sprite names in the struct override the project's own sprites of the same name,
which is what makes the game draw from this atlas instead of GameMaker's pages.
`texturegroup_delete` restores the originals. The group name must not match a
texture group that already exists or the call fails fatally, which is why the
tool checks it. Rotation has no member in that struct, so leave **Allow 90 degree
rotation** off when packing for this path; the build warns if any frame rotated.

`atlas_writer.minimalTextureGroupStruct` strips the json to only the members
GameMaker reads, if you would rather ship a smaller file.

## Character Atlas Packer tab

Three buttons, no room required: **Pack Actors / Creatures**, **Pack NPCs**,
**Pack Equipment**.

This is a separate tab rather than another exclusion preset because it is the
opposite operation. A room pack starts from what a `.yy` file says is placed and
subtracts; none of the character art is placed anywhere. A body layer is reached
by concatenating a body style, a layer word and an anim group at runtime, so the
only way to find it is to **build the same names the draw code builds and keep
the ones that exist**. A name nothing can produce is never generated, which is
what stops the pack filling up with art the game can never reach.

### Where the names come from

| Input | What it contributes |
| --- | --- |
| `UserSettings.characterOptions` in `settings_s` | body styles, hair styles |
| `defaultActorSpawnData` in `actor_s_util` | the outfit, body and hair a spawn point inherits when it sets none |
| every `animGroup*` string literal in `actorSpriteAnimState_s` | the anim suffix on every body and clothing sheet |
| `new Clothing(...)` in `item_s` | the outfit key an equipped item resolves to, and the `spr_head_<name>` stack for a HEAD item |
| `global.headAttachmentPools` | the extra pipe layer a helmet instance can roll |
| the `Create_0.gml` of every `oSpawnPointAINpc` child | that NPC's body style, hair and outfit strings |
| every other `oSpawnPointAI` child | the punk, rando, zombie and skeleton, which share the actors' art |
| `makeCreatureProfile` / `makePreyProfile` call sites | `spr_crt_<sprite><anim>` for each creature family |
| `spritesheet :` in the skills, and the `*Sprite` assignments in the melee objects | the held weapon and swing layers |

Comments are stripped before anything is read, so the large commented out
reference block in each spawn point's Create event does not widen a one outfit
NPC into the whole wardrobe. A randomised field contributes every outcome the
roll can produce: `getRandomHairStyle(["bedhead", "liberty"])` contributes both,
and `getRandomHairStyle()` contributes the whole customization list.

### Which atlas gets what

The three are disjoint, because a sheet in two atlases is a sheet loaded twice.

- **Actors / Creatures** the bare body every humanoid is built from, for every
  body style, anim group and hair style, plus the clothing only a non NPC spawn
  can wear (the zombie outfit), plus every creature sheet. The player, a punk, a
  rando, a zombie and a skeleton all draw their body from here.
- **NPCs** the outfits the `oSpawnPointAINpc` children wear. Pick a map to
  restrict it to the spawn points placed in that map. **NPC atlas carries its own
  body layers** is on by default so the atlas stands alone; switch it off if the
  actors atlas is always loaded alongside.
- **Equipment** everything an item puts on a body: the clothing an equipped
  `Clothing` item resolves to, the headgear stack, the held weapon layers and the
  swing sprites, and optionally the inventory icons.

### Layer major packing

Sheets are ordered by draw pass and then by draw slot, and a new page is started
whenever the pass changes, so **a page never spans two passes**. That is what
lets the draw controller bind once per pass instead of once per actor. Turn on
**One page per draw slot** to go further and give every layer its own page, which
costs pages and buys one bind per layer.

The atlas json carries what the controller needs on top of the normal
`texturegroup_add` members:

```json
"meta": {
  "pass_order": ["body", "clothing", "weapon"],
  "pass_pages": { "body": [0], "clothing": [1, 2] },
  "slot_pages": { "lowerBody": [0], "legs": [1], "torso": [1, 2] },
  "draw_order": ["lowerBody", "feet", "legs", "upperBody", "face",
                 "shirt", "torso", "waist", "hair", "head", "arms", "hands"]
}
```

and every sprite gains `slot`, `pass`, `body_style`, `outfit`, `anim_group` and
`family`. `texturegroup_add` ignores members it does not know, so the extra keys
ride along harmlessly.

The pack report leads with the number that matters:

```
Pages a draw pass has to bind:
    body: page(s) 0   ONE BIND
    clothing: page(s) 1   ONE BIND
    creature: page(s) 2, 3, 4, 5, 6, 7, 8, 9, 10   9 binds
```

Creatures have no layer stack at all - a creature draws one sheet per animation
with `draw_sprite_part_ext` - so they are grouped by family instead, and the
report lists which pages each family binds and flags the ones that span two.

### Sheets are packed whole

Every LPC layer is a **single frame** image that the draw slices with
`draw_sprite_part_ext(sheet, 0, col * frameSize, row * frameSize, ...)`. The
packer places it as one rectangle and records that rectangle, because splitting
it or padding inside it would break the col/row arithmetic at runtime. Rotation
is forced off for the same reason `texturegroup_add` cannot describe it.

### Unreachable art is reported

A name the draw code builds that has no sprite is dropped silently - that is the
normal case, since only `vagabond` fills all six clothing slots. A name that
differs from a real sprite **only by casing** is called out instead, because that
is art that exists and can never be reached:

```
Casing mismatch: the draw code builds spr_male_lower_body_walkZ
but the project has spr_male_lower_body_walkz, so that sheet never resolves
```

### Command line

```
python character_atlas_builder.py "<project root>" actors
python character_atlas_builder.py "<project root>" npcs --room rCity_Forest
python character_atlas_builder.py "<project root>" equipment --include-icons
python character_atlas_builder.py "<project root>" actors --page-per-slot --page-size 2048
```

Other flags: `--no-page-per-pass`, `--no-npc-body-layers`, `--include-wrists`,
`--no-unattributed-creatures`, `--group-name`, `--output`, `--padding`,
`--oversize`, `--debug-images`.

`--include-wrists` exists because `setOutfitString` resolves a `wrists` sheet
that `drawToSurface` never draws. It is off until a `drawPart(wrists, ...)` call
is added to the composite.

## Tests

```
python -m unittest discover -s tests
```

## Requirements

Python 3, `pillow`, `json5`. GameMaker 1.4 `.gmx` projects are not supported.
