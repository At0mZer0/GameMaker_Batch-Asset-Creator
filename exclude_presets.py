# Named exclusion presets. A room atlas should hold the art the map draws, so
# the default preset drops the things that only reach art through code: the
# controllers sitting on the Controllers layer, the persistent controllers the
# title screen leaves running, the menus, and anything on a UI layer.
#
# Add a preset here to get another pack type. The names are matched with
# wildcards, so "*Menu" covers a family.

MAP_PRESET_NAME = "Map"
EVERYTHING_PRESET_NAME = "Everything"

# Placed on the Controllers layer in rCity_Forest, none of them draw map art
ROOM_CONTROLLERS = [
    "oCtrl",
    "oGlareCtrl",
    "oCamera",
    "oBuildings",
    "obj_render"
]

# Placed in rTitleScreen. The persistent ones stay alive into every later room,
# which is how title and menu art leaks into a map atlas.
TITLE_SCREEN_OBJECTS = [
    "oGUICtrl",
    "oGameCtrl",
    "oSteam",
    "oUiCtrl",
    "oTitleScreen",
    "oTitleMenuCtrl",
    "oPressStart",
    "oTSDText",
    "oTSDTextSolid"
]

# Persistent objects placed in rMenu
MENU_ROOM_OBJECTS = [
    "oCursor",
    "oLobby"
]

MENU_OBJECTS = [
    "*Menu"
]

UI_LAYERS = [
    "UI_*",
    "GUI"
]


PRESETS = {
    MAP_PRESET_NAME: {
        "description": "Map art only, no controllers, menus or UI",
        "objects": ROOM_CONTROLLERS + TITLE_SCREEN_OBJECTS + MENU_ROOM_OBJECTS + MENU_OBJECTS,
        "layers": list(UI_LAYERS)
    },
    EVERYTHING_PRESET_NAME: {
        "description": "No exclusions, every sprite the room can reach",
        "objects": [],
        "layers": []
    }
}

DEFAULT_PRESET_NAME = MAP_PRESET_NAME


def presetNames():
    return sorted(PRESETS)


def presetObjects(presetName):
    return list(PRESETS.get(presetName, PRESETS[DEFAULT_PRESET_NAME])["objects"])


def presetLayers(presetName):
    return list(PRESETS.get(presetName, PRESETS[DEFAULT_PRESET_NAME])["layers"])


def asCommaText(values):
    return ", ".join(values)


def fromCommaText(text):
    return [name.strip() for name in (text or "").split(",") if name.strip()]
