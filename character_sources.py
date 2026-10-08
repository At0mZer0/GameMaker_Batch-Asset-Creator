import os
import re
from dataclasses import dataclass, field

import room_parser
from sprite_discovery import stripGMLComments

# The character art in this project is not named by any single convention that a
# regex over the sprite folder can recover. A body layer is
# spr_<bodyStyle>_<layer><animGroup>, a clothing layer inserts an outfit key in
# the middle, and a head layer drops the body prefix and the anim group
# entirely. "armor_arms" is an outfit key that contains a layer word, and
# "upper_body" is a layer that contains one.
#
# So this module does the opposite of pattern matching: it reads the same inputs
# the game reads - the customization option lists, the Clothing item table, the
# spawn point templates, the creature profiles - COMPOSES the names the draw code
# would compose, and keeps only the ones that exist as a sprite resource. A name
# nothing can produce is never generated, which is what "only the sprites the
# game could use" means here.

#region Draw model
# The twelve slots ActorSpriteLPC.drawToSurface composites, in the order it
# draws them. Kept as the source order because the metadata reports it, even
# though the pack groups by pass.
SLOT_LOWER_BODY = "lowerBody"
SLOT_FEET = "feet"
SLOT_LEGS = "legs"
SLOT_UPPER_BODY = "upperBody"
SLOT_FACE = "face"
SLOT_SHIRT = "shirt"
SLOT_TORSO = "torso"
SLOT_WAIST = "waist"
SLOT_HAIR = "hair"
SLOT_HEADGEAR = "head"
SLOT_ARMS = "arms"
SLOT_HANDS = "hands"
SLOT_WRISTS = "wrists"
SLOT_WEAPON = "weapon"
SLOT_ICON = "icon"
SLOT_CREATURE = "creature"

DRAW_ORDER = [
    SLOT_LOWER_BODY, SLOT_FEET, SLOT_LEGS, SLOT_UPPER_BODY, SLOT_FACE,
    SLOT_SHIRT, SLOT_TORSO, SLOT_WAIST, SLOT_HAIR, SLOT_HEADGEAR,
    SLOT_ARMS, SLOT_HANDS
]

# The three draw controller passes. Pass one builds the bare body, pass two puts
# the clothing and equipment slots on it, pass three the held weapon.
PASS_BODY = "body"
PASS_CLOTHING = "clothing"
PASS_WEAPON = "weapon"
PASS_CREATURE = "creature"
PASS_ICON = "icon"

PASS_FOR_SLOT = {
    SLOT_LOWER_BODY: PASS_BODY,
    SLOT_UPPER_BODY: PASS_BODY,
    SLOT_FACE: PASS_BODY,
    SLOT_HAIR: PASS_BODY,
    SLOT_ARMS: PASS_BODY,

    SLOT_FEET: PASS_CLOTHING,
    SLOT_LEGS: PASS_CLOTHING,
    SLOT_SHIRT: PASS_CLOTHING,
    SLOT_TORSO: PASS_CLOTHING,
    SLOT_WAIST: PASS_CLOTHING,
    SLOT_HANDS: PASS_CLOTHING,
    SLOT_WRISTS: PASS_CLOTHING,
    SLOT_HEADGEAR: PASS_CLOTHING,

    SLOT_WEAPON: PASS_WEAPON,
    SLOT_CREATURE: PASS_CREATURE,
    SLOT_ICON: PASS_ICON
}

PASS_ORDER = [PASS_BODY, PASS_CLOTHING, PASS_WEAPON, PASS_CREATURE, PASS_ICON]

# Slots whose sheet name carries no outfit key: spr_<bodyStyle>_<slot><animGroup>
BODY_SLOTS = {
    SLOT_LOWER_BODY: "lower_body",
    SLOT_UPPER_BODY: "upper_body",
    SLOT_ARMS: "arms"
}

# Slots whose sheet name carries one: spr_<bodyStyle>_<outfit>_<slot><animGroup>.
# wrists is resolved by setOutfitString and setOutfitStruct but never drawn -
# there is no drawPart(wrists) call anywhere - so it is off by default.
OUTFIT_SLOTS = [SLOT_FEET, SLOT_LEGS, SLOT_SHIRT, SLOT_TORSO, SLOT_WAIST, SLOT_HANDS]
OUTFIT_SLOT_WRISTS = SLOT_WRISTS

# feet and legs take animGroupLower, everything else in the clothing pass takes
# animGroupUpper. Both come out of the same 21 value set, so the composer walks
# every group for every slot rather than tracking which state used which.

# The anim suffix table makeCreatureProfile builds its sheet names from
CREATURE_ANIM_SUFFIXES = [
    "_idle", "_walk", "_run", "_attack", "_attack2", "_attack3", "_attack4",
    "_walk_attack", "_run_attack", "_ability", "_hurt", "_death"
]
#endregion


#region Small parsing helpers
QUOTED = re.compile(r'"([^"\n]*)"')


def readTextFile(path):
    try:
        with open(path, 'r', encoding = 'utf-8', errors = 'replace') as handle:
            return handle.read()
    except OSError:
        return ""


def readGML(path):
    # Every read in this module goes through the comment stripper. The spawn
    # point Create events all carry a large commented out reference block listing
    # every body style, hair and skin in the game, and taking those literally
    # would pull in the whole wardrobe for a spawn that uses one outfit.
    return stripGMLComments(readTextFile(path))


def quotedStringsIn(text):
    return QUOTED.findall(text)


def arrayLiteralAfter(text, key):
    # Returns the quoted strings inside the first `key : [ ... ]` array found,
    # which is how the customization option lists are written - across several
    # lines, so a single line regex will not do.
    match = re.search(re.escape(key) + r"\s*:\s*\[", text)
    if not match:
        return []

    depth = 0
    start = match.end() - 1
    for index in range(start, len(text)):
        character = text[index]
        if character == '[':
            depth += 1
        elif character == ']':
            depth -= 1
            if depth == 0:
                return quotedStringsIn(text[start:index])
    return []


def splitTopLevelArguments(text):
    # Splits a call's argument text on commas that are not inside brackets,
    # braces, parentheses or a string. new Clothing(...) puts the outfit key
    # last and the description before it, so position matters.
    parts = []
    depth = 0
    current = []
    inString = False
    index = 0

    while index < len(text):
        character = text[index]

        if inString:
            current.append(character)
            if character == '"':
                inString = False
            index += 1
            continue

        if character == '"':
            inString = True
            current.append(character)
        elif character in "([{":
            depth += 1
            current.append(character)
        elif character in ")]}":
            depth -= 1
            current.append(character)
        elif character == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(character)
        index += 1

    parts.append(''.join(current))
    return [part.strip() for part in parts]


def callArgumentsFor(text, functionName):
    # Yields the argument text of every `functionName(` call in text, balanced
    # so a nested call does not end the match early.
    pattern = re.compile(r"\b" + re.escape(functionName) + r"\s*\(")

    for match in pattern.finditer(text):
        depth = 1
        index = match.end()
        while index < len(text) and depth > 0:
            character = text[index]
            if character == '"':
                index += 1
                while index < len(text) and text[index] != '"':
                    index += 1
            elif character == '(':
                depth += 1
            elif character == ')':
                depth -= 1
                if depth == 0:
                    yield text[match.end():index]
                    break
            index += 1
#endregion


@dataclass
class ResolvedSheet:
    # One sprite the game can put on screen, with everything the packer needs to
    # group it and everything the report needs to explain why it is here.
    name: str
    slot: str
    passName: str
    bodyStyle: str = ""
    outfit: str = ""
    animGroup: str = ""
    # Creature sheets only: the profile sprite base, so a family's sheets sort
    # and report together whether or not the anim name was reconstructable
    family: str = ""
    origins: list = field(default_factory = list)

    def addOrigin(self, origin):
        if origin and origin not in self.origins:
            self.origins.append(origin)


@dataclass
class NpcSpawn:
    objectName: str
    bodyStyles: list = field(default_factory = list)
    hairStyles: list = field(default_factory = list)
    outfit: str = ""


class CharacterSources:
    # Reads one GameMaker project and answers "what character art can this game
    # actually produce". Everything is lazy and cached, because the UI builds
    # three atlases off one instance.

    def __init__(self, projectRoot):
        self.projectRoot = projectRoot
        self.scriptsRoot = os.path.join(projectRoot, "scripts")
        self.objectsRoot = os.path.join(projectRoot, "objects")
        self.spritesRoot = os.path.join(projectRoot, "sprites")
        self.warnings = []
        self.cache = {}

    def addWarning(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def cached(self, key, producer):
        if key not in self.cache:
            self.cache[key] = producer()
        return self.cache[key]

#region Project files
    def spriteNames(self):
        # The exact resource names, case included. Every composed name is checked
        # against this set and against nothing else, so a sheet whose casing does
        # not match what the draw code builds is reported as missing rather than
        # silently packed - which is the spr_male_lower_body_walkz case.
        def load():
            if not os.path.isdir(self.spritesRoot):
                self.addWarning("No sprites folder in " + self.projectRoot)
                return set()
            return {name for name in os.listdir(self.spritesRoot)
                    if os.path.isfile(os.path.join(self.spritesRoot, name, name + ".yy"))}
        return self.cached("spriteNames", load)

    def spriteNamesLower(self):
        # Only used to explain a miss, never to resolve one
        return self.cached("spriteNamesLower", lambda: {name.lower(): name for name in self.spriteNames()})

    def scriptText(self, scriptName):
        return self.cached("script:" + scriptName,
                           lambda: readGML(os.path.join(self.scriptsRoot, scriptName, scriptName + ".gml")))

    def allScriptText(self):
        def load():
            chunks = []
            if not os.path.isdir(self.scriptsRoot):
                return ""
            for scriptName in sorted(os.listdir(self.scriptsRoot)):
                path = os.path.join(self.scriptsRoot, scriptName, scriptName + ".gml")
                if os.path.isfile(path):
                    chunks.append(readGML(path))
            return "\n".join(chunks)
        return self.cached("allScripts", load)

    def objectParents(self):
        def load():
            parents = {}
            if not os.path.isdir(self.objectsRoot):
                return parents
            for objectName in sorted(os.listdir(self.objectsRoot)):
                yyPath = os.path.join(self.objectsRoot, objectName, objectName + ".yy")
                if not os.path.isfile(yyPath):
                    continue
                match = re.search(r'"parentObjectId"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"',
                                  readTextFile(yyPath))
                parents[objectName] = match.group(1) if match else None
            return parents
        return self.cached("objectParents", load)

    def descendantsOf(self, rootObjectName):
        # Every object whose parentObjectId chain reaches rootObjectName. The
        # spawn point tree is flat today but a grandchild must not be missed.
        parents = self.objectParents()
        found = []

        for objectName in sorted(parents):
            if objectName == rootObjectName:
                continue
            seen = set()
            current = parents.get(objectName)
            while current and current not in seen:
                seen.add(current)
                if current == rootObjectName:
                    found.append(objectName)
                    break
                current = parents.get(current)

        return found

    def objectEventText(self, objectName, eventFileName = "Create_0.gml"):
        return readGML(os.path.join(self.objectsRoot, objectName, eventFileName))
#endregion

#region The name grammar
    def animGroups(self):
        # Every animGroup / animGroupUpper / animGroupLower / animGroupHead string
        # literal in the LPC anim state table. The empty default is included
        # because getHeadGroupSuffix returns "" for any animation without a
        # unique head anim, which is what makes spr_<body>_head resolve.
        def load():
            text = self.scriptText("actorSpriteAnimState_s")
            if not text:
                self.addWarning("actorSpriteAnimState_s not found, falling back to no anim groups")
                return [""]
            groups = set(re.findall(r'animGroup[A-Za-z]*\s*:\s*"([^"]*)"', text))
            # A creature anim group is built at runtime from the profile's sheet
            # name and never appears as a leading underscore literal
            groups = {group for group in groups if group.startswith("_")}
            return [""] + sorted(groups)
        return self.cached("animGroups", load)

    def bodyStyles(self):
        # The customization screen offers male and female; skele reaches the draw
        # through defaultActorSpawnData and the skeleton spawn point.
        def load():
            styles = []
            settings = self.scriptText("settings_s")
            for style in arrayLiteralAfter(settings, "bodyStyles"):
                if style not in styles:
                    styles.append(style)

            for style in self.literalValuesFor("bodyStyle"):
                if style and style not in styles:
                    styles.append(style)

            return styles
        return self.cached("bodyStyles", load)

    def hairStyles(self):
        def load():
            styles = list(arrayLiteralAfter(self.scriptText("settings_s"), "hairs"))

            # A spawn point can name a style the customization list does not
            # offer, and getRandomHairStyle takes a subset array
            for style in self.literalValuesFor("hairStyle"):
                if style and style not in styles:
                    styles.append(style)

            for arguments in callArgumentsFor(self.allObjectCreateText(), "getRandomHairStyle"):
                for style in quotedStringsIn(arguments):
                    if style not in styles:
                        styles.append(style)

            return styles
        return self.cached("hairStyles", load)

    def allObjectCreateText(self):
        def load():
            chunks = []
            if not os.path.isdir(self.objectsRoot):
                return ""
            for objectName in sorted(os.listdir(self.objectsRoot)):
                path = os.path.join(self.objectsRoot, objectName, "Create_0.gml")
                if os.path.isfile(path):
                    chunks.append(readGML(path))
            return "\n".join(chunks)
        return self.cached("allObjectCreate", load)

    def literalValuesFor(self, key):
        # Every `key : "value"` in object Create events and scripts. Comments are
        # already stripped, so the reference blocks in the spawn points do not
        # contribute.
        def load():
            pattern = re.compile(re.escape(key) + r'\s*:\s*"([^"]*)"')
            values = []
            for text in (self.allObjectCreateText(), self.allScriptText()):
                for value in pattern.findall(text):
                    if value not in values:
                        values.append(value)
            return values
        return self.cached("literal:" + key, load)

    def clothingItems(self):
        # (outfitKey, equipSlotName) for every Clothing entry in the item table.
        # The outfit key is the last argument of the constructor.
        def load():
            text = self.scriptText("item_s")
            items = []

            for arguments in callArgumentsFor(text, "new Clothing"):
                parts = splitTopLevelArguments(arguments)
                if len(parts) < 2:
                    continue
                outfitMatch = re.fullmatch(r'"([^"]*)"', parts[-1].strip())
                if not outfitMatch:
                    continue
                slotName = ""
                for part in parts:
                    slotMatch = re.search(r"EQUIP_SLOT\.([A-Z_]+)", part)
                    if slotMatch:
                        slotName = slotMatch.group(1)
                        break
                items.append((outfitMatch.group(1), slotName))

            if not items:
                self.addWarning("No Clothing items found in item_s, the equipment atlas will be empty")
            return items
        return self.cached("clothingItems", load)

    def itemOutfitKeys(self):
        # Outfit keys an equipped item can put on a body. HEAD items are excluded
        # because a head slot resolves through getHeadLayers to spr_head_<name>
        # instead, with no body prefix and no anim group.
        def load():
            keys = []
            for outfitKey, slotName in self.clothingItems():
                if slotName == "HEAD":
                    continue
                if outfitKey and outfitKey not in keys:
                    keys.append(outfitKey)

            # The OUTFITS table is a per slot outfit struct rather than an item
            for value in arrayLiteralAfter(self.scriptText("item_s"), "OUTFITS") or []:
                if value and value not in keys:
                    keys.append(value)

            match = re.search(r"OUTFITS\[[^\]]*\]\s*=\s*\{(.*?)\}", self.scriptText("item_s"), re.S)
            if match:
                for value in quotedStringsIn(match.group(1)):
                    if value and value not in keys:
                        keys.append(value)

            return keys
        return self.cached("itemOutfitKeys", load)

    def headgearNames(self):
        # A head item's outfit string is a pipe delimited list of headgear names,
        # and a helmet instance can roll one more from HEAD_ATTACHMENT_POOLS. Both
        # halves map to spr_head_<name>.
        def load():
            names = []

            for outfitKey, slotName in self.clothingItems():
                if slotName != "HEAD":
                    continue
                for part in outfitKey.split("|"):
                    part = part.strip()
                    if part and part not in names:
                        names.append(part)

            text = self.scriptText("item_s")
            match = re.search(r"headAttachmentPools\s*=\s*\{(.*?)\n\}", text, re.S)
            if match:
                for name in quotedStringsIn(match.group(1)):
                    if name and name not in names:
                        names.append(name)

            return names
        return self.cached("headgearNames", load)

    def defaultSpawnOutfit(self):
        # defaultActorSpawnData is the fallback every spawn point inherits, and
        # it is what a Punk or a Rando actually wears - neither getTemplate sets
        # an outfit of its own.
        def load():
            text = self.scriptText("actor_s_util")
            match = re.search(r"function\s+defaultActorSpawnData\s*\(\s*\)\s*\{(.*?)\n\}", text, re.S)
            if not match:
                self.addWarning("defaultActorSpawnData not found, spawn points with no outfit of their own "
                                "will contribute no clothing")
                return {}
            block = match.group(1)
            defaults = {}
            for key in ("bodyStyle", "hairStyle", "outfit"):
                keyMatch = re.search(re.escape(key) + r'\s*:\s*"([^"]*)"', block)
                if keyMatch:
                    defaults[key] = keyMatch.group(1)
            return defaults
        return self.cached("defaultSpawnOutfit", load)
#endregion

#region Spawn points
    def spawnTemplate(self, objectName):
        # What one spawn point actually asks for, after its own getTemplate and
        # defaultTemplate, falling back to the inherited defaults. A randomised
        # field yields the whole option list rather than one value, because the
        # atlas has to hold every outcome the roll can produce.
        text = self.objectEventText(objectName)
        defaults = self.defaultSpawnOutfit()

        def literal(key):
            match = re.search(re.escape(key) + r'\s*:\s*"([^"]*)"', text)
            return match.group(1) if match else None

        def randomised(key, randomFunctionName, wholeList):
            match = re.search(re.escape(key) + r"\s*:\s*" + re.escape(randomFunctionName) + r"\s*\(", text)
            if not match:
                return None
            for arguments in callArgumentsFor(text[match.start():], randomFunctionName):
                subset = quotedStringsIn(arguments)
                return subset if subset else list(wholeList)
            return list(wholeList)

        bodyStyle = literal("bodyStyle")
        bodyStyles = [bodyStyle] if bodyStyle else randomised("bodyStyle", "getRandomHumanBodyStyle", ["male", "female"])
        if not bodyStyles:
            bodyStyles = [defaults.get("bodyStyle", "male")]

        hairStyle = literal("hairStyle")
        hairStyles = [hairStyle] if hairStyle else randomised("hairStyle", "getRandomHairStyle", self.hairStyles())
        if not hairStyles:
            hairStyles = [defaults.get("hairStyle", "bald")]

        outfit = literal("outfit")
        if outfit is None:
            outfit = defaults.get("outfit", "")

        return NpcSpawn(objectName, bodyStyles, hairStyles, outfit)

    def npcSpawnPoints(self, rootObjectName = "oSpawnPointAINpc"):
        def load():
            children = self.descendantsOf(rootObjectName)
            if not children:
                self.addWarning("No objects inherit from " + rootObjectName + " in this project")
            return [self.spawnTemplate(name) for name in children]
        return self.cached("npcSpawns:" + rootObjectName, load)

    def actorSpawnPoints(self):
        # Every AI spawn point that is NOT an NPC child: the punk, the rando, the
        # zombie and the skeleton. They share the player's body and vagabond
        # clothing, which is why they pack with the actors and not the NPCs.
        def load():
            npcNames = set(self.descendantsOf("oSpawnPointAINpc"))
            names = [name for name in self.descendantsOf("oSpawnPointAI")
                     if name not in npcNames and name != "oSpawnPointAINpc"]
            return [self.spawnTemplate(name) for name in names]
        return self.cached("actorSpawns", load)
#endregion

#region Name composition
    def composeBodySheets(self, bodyStyles, slots = None):
        # spr_<bodyStyle>_<layer><animGroup> for the slots that carry no outfit,
        # plus the canonical head sheet the face slot draws.
        sheets = {}
        slots = slots or list(BODY_SLOTS)

        for bodyStyle in bodyStyles:
            for slot in slots:
                layerWord = BODY_SLOTS[slot]
                for animGroup in self.animGroups():
                    name = "spr_" + bodyStyle + "_" + layerWord + animGroup
                    self.keepIfReal(sheets, name, slot, bodyStyle = bodyStyle, animGroup = animGroup,
                                    origin = "body " + bodyStyle)
        return sheets

    def composeFaceSheets(self, bodyStyles):
        # getHeadGroupSuffix returns "" unless the animation carries a unique per
        # frame head animation, so this is the canonical sheet plus those.
        sheets = {}
        for bodyStyle in bodyStyles:
            for animGroup in self.animGroups():
                name = "spr_" + bodyStyle + "_head" + animGroup
                self.keepIfReal(sheets, name, SLOT_FACE, bodyStyle = bodyStyle, animGroup = animGroup,
                                origin = "face " + bodyStyle)
        return sheets

    def composeHairSheets(self, hairStyles):
        # spr_hair_<style> plus the per animation head variants. bald has no
        # sheet at all, which is how the draw code says "no hair layer".
        sheets = {}
        for hairStyle in hairStyles:
            for animGroup in self.animGroups():
                name = "spr_hair_" + hairStyle + animGroup
                self.keepIfReal(sheets, name, SLOT_HAIR, animGroup = animGroup,
                                origin = "hair " + hairStyle)
        return sheets

    def composeOutfitSheets(self, bodyStyles, outfitKeys, includeWrists = False):
        # spr_<bodyStyle>_<outfit>_<slot><animGroup>. An outfit key with no art
        # for a slot simply produces nothing, which is the normal case - only
        # vagabond fills all six.
        sheets = {}
        slots = list(OUTFIT_SLOTS) + ([OUTFIT_SLOT_WRISTS] if includeWrists else [])

        for bodyStyle in bodyStyles:
            for outfitKey in outfitKeys:
                if not outfitKey:
                    continue
                for slot in slots:
                    for animGroup in self.animGroups():
                        name = "spr_" + bodyStyle + "_" + outfitKey + "_" + slot + animGroup
                        self.keepIfReal(sheets, name, slot, bodyStyle = bodyStyle, outfit = outfitKey,
                                        animGroup = animGroup, origin = "outfit " + outfitKey)
        return sheets

    def composeHeadgearSheets(self, headgearNames):
        sheets = {}
        for headgearName in headgearNames:
            self.keepIfReal(sheets, "spr_head_" + headgearName, SLOT_HEADGEAR,
                            origin = "headgear " + headgearName)
        return sheets

    def keepIfReal(self, sheets, name, slot, bodyStyle = "", outfit = "", animGroup = "", origin = ""):
        # The whole point of composing rather than matching: a name the draw code
        # can build but the project has no art for is dropped here, silently and
        # by design. Only a casing near miss is worth a warning, because that is
        # art that exists and can never be reached.
        if name in self.spriteNames():
            entry = sheets.get(name)
            if entry is None:
                entry = ResolvedSheet(
                    name = name, slot = slot, passName = PASS_FOR_SLOT[slot],
                    bodyStyle = bodyStyle, outfit = outfit, animGroup = animGroup
                )
                sheets[name] = entry
            entry.addOrigin(origin)
            return True

        realName = self.spriteNamesLower().get(name.lower())
        if realName:
            self.addWarning("Casing mismatch: the draw code builds " + name +
                            " but the project has " + realName + ", so that sheet never resolves")
        return False
#endregion

#region Creatures and weapons
    def creatureSheets(self, includeUnattributed = True):
        # makeCreatureProfile builds every sheet name as crt_<sprite or id> plus a
        # fixed anim suffix. A family that declares its own anims block (the
        # hellbat is one strip per animation with its own names) is not
        # reconstructable that way, so anything left over is picked up by prefix
        # and reported separately.
        def load():
            text = self.scriptText("actorSpriteAnimStateCreature_s") + "\n" + self.allScriptText()
            bases = set()

            for arguments in callArgumentsFor(text, "makeCreatureProfile"):
                for key in ("sprite", "id", "deathSprite"):
                    for value in re.findall(re.escape(key) + r'\s*:\s*"([^"]*)"', arguments):
                        if value:
                            bases.add(value)

            for arguments in callArgumentsFor(text, "makePreyProfile"):
                for key in ("sprite", "id"):
                    for value in re.findall(re.escape(key) + r'\s*:\s*"([^"]*)"', arguments):
                        if value:
                            bases.add(value)

            sheets = {}
            for base in sorted(bases):
                for suffix in CREATURE_ANIM_SUFFIXES:
                    if self.keepIfReal(sheets, "spr_crt_" + base + suffix, SLOT_CREATURE,
                                       origin = "creature " + base):
                        sheets["spr_crt_" + base + suffix].family = base

            # A family that declares its own anims block instead of taking the
            # factory's cols (the hellbat's one strip per animation, the gorilla's
            # picking_up / two_footed_jump set) names sheets the suffix table
            # cannot rebuild. They are still that family's art, so they are
            # attributed by the longest profile base their name starts with and
            # sort with the rest of the family.
            unattributed = []
            if includeUnattributed:
                orderedBases = sorted(bases, key = len, reverse = True)
                for name in sorted(self.spriteNames()):
                    if not name.startswith("spr_crt_") or name in sheets:
                        continue
                    rest = name[len("spr_crt_"):]
                    family = next((base for base in orderedBases if rest.startswith(base + "_")), "")
                    sheets[name] = ResolvedSheet(
                        name = name, slot = SLOT_CREATURE, passName = PASS_CREATURE, family = family,
                        origins = ["creature " + family + " (anim not in the factory table)" if family
                                   else "creature sheet with no profile"]
                    )
                    unattributed.append(name)

            return sheets, sorted(bases), unattributed
        return self.cached("creatureSheets:" + str(includeUnattributed), load)

    def weaponSheets(self):
        # The held weapon layers a skill declares (spritesheet : spr_x, and the
        # male / female ternaries), the block and death layers built from the
        # skill name, and the directional swing sprites the melee attack objects
        # assign. All of it is verified against the sprite folder, so a token
        # that is not a sprite drops out.
        def load():
            sheets = {}
            text = self.allScriptText() + "\n" + self.allObjectCreateText()

            for match in re.finditer(r"spritesheet\s*:\s*([^,\n}]+)", text):
                for token in re.findall(r"\bspr_[A-Za-z0-9_]+", match.group(1)):
                    self.keepIfReal(sheets, token, SLOT_WEAPON, origin = "extra layer")

            # asset_get_index("spr_" + nm + "_death_under") and friends, where nm
            # is the lowercased skill name. Reconstructed from the suffixes rather
            # than the skill list, then verified.
            for suffix in ("_block", "_death_under", "_death_over"):
                for name in sorted(self.spriteNames()):
                    if not name.endswith(suffix):
                        continue
                    if re.match(r"^spr_(male|female|skele)_", name):
                        continue
                    sheets.setdefault(name, ResolvedSheet(
                        name = name, slot = SLOT_WEAPON, passName = PASS_WEAPON,
                        origins = ["skill " + suffix.strip("_") + " layer"]
                    ))

            for match in re.finditer(r"\b[A-Za-z0-9_]*[Ss]prite\s*=\s*(spr_[A-Za-z0-9_]+)", text):
                self.keepIfReal(sheets, match.group(1), SLOT_WEAPON, origin = "swing sprite")

            return sheets
        return self.cached("weaponSheets", load)

    def itemIconSheets(self):
        # The third argument of every item constructor, plus any icon assignment.
        # Icons never reach the actor surface, so they are their own pass and can
        # be left out of a gameplay atlas entirely.
        def load():
            sheets = {}
            text = self.scriptText("item_s") + "\n" + self.scriptText("skill_s")

            for constructor in ("new Clothing", "new Weapon", "new RangedWeapon", "new MeleeWeapon",
                                "new Utility", "new Consumable", "new Resource", "new Item"):
                for arguments in callArgumentsFor(text, constructor):
                    parts = splitTopLevelArguments(arguments)
                    if len(parts) < 3:
                        continue
                    token = parts[2].strip()
                    if re.fullmatch(r"spr_[A-Za-z0-9_]+", token):
                        self.keepIfReal(sheets, token, SLOT_ICON, origin = "item icon")

            for match in re.finditer(r"\bicon\s*=\s*(spr_[A-Za-z0-9_]+)", text):
                self.keepIfReal(sheets, match.group(1), SLOT_ICON, origin = "skill icon")

            return sheets
        return self.cached("itemIconSheets", load)
#endregion
