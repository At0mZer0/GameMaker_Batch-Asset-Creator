import os
from dataclasses import dataclass, field

import atlas_packer
import atlas_writer
import character_sources as sources
import room_parser

DEFAULT_OUTPUT_FOLDER = "packed_atlases"

# The three atlases, and the rule for what belongs in each. They are deliberately
# disjoint: no sheet is packed twice, because a sheet in two atlases is a sheet
# loaded twice at runtime.
#
#   actors     the bare body every humanoid is built from (pass one), plus the
#              clothing only a non NPC spawn can wear, plus every creature sheet.
#              A skeleton, a punk, a rando and a zombie all draw from here, and
#              so does the player's body.
#   npcs       the outfits the oSpawnPointAINpc children wear, and optionally the
#              body layers they need so the atlas stands alone on an NPC map.
#   equipment  everything an item puts on screen: the clothing an equipped
#              Clothing item resolves to, the headgear stack, the held weapon
#              layers and swing sprites, and optionally the inventory icons.
KIND_ACTORS = "actors"
KIND_NPCS = "npcs"
KIND_EQUIPMENT = "equipment"

KIND_LABELS = {
    KIND_ACTORS: "Actors and Creatures",
    KIND_NPCS: "NPCs",
    KIND_EQUIPMENT: "Equipment"
}

DEFAULT_ATLAS_NAMES = {
    KIND_ACTORS: "actors",
    KIND_NPCS: "npcs",
    KIND_EQUIPMENT: "equipment"
}


@dataclass
class CharacterAtlasOptions:
    # Packing options are the room packer's; these are the choices that only make
    # sense for character art.
    kind: str = KIND_ACTORS
    # Restrict the NPC atlas to the spawn points actually placed in one room.
    # Every NPC child packed together is 3.3 pages; one map's worth is under two.
    roomName: str = ""
    # Give the NPC atlas its own copy of the body layers its spawns need, so a
    # map that loads only this atlas still draws a body under the clothes.
    npcIncludeBodyLayers: bool = True
    # Pack the inventory and loot icons with the equipment. They never reach the
    # actor surface, so a gameplay only atlas can leave them out.
    includeItemIcons: bool = False
    # wrists is resolved by the outfit code and never drawn. Off unless a
    # drawPart(wrists) call is added to the LPC composite.
    includeWrists: bool = False
    # A creature sheet no profile could be reconstructed from - the families that
    # declare their own anims block - is still art the game ships.
    includeUnattributedCreatures: bool = True
    # One page per draw pass. Off packs everything in draw order without forcing
    # the boundary, which is denser but makes a pass bind two pages.
    pageBreakPerPass: bool = True
    # Break on every slot as well, not just every pass. Costs pages, but then a
    # single layer is one bind even inside a pass.
    pageBreakPerSlot: bool = False


def defaultOutputDir(projectRoot, atlasName):
    return os.path.join(projectRoot, DEFAULT_OUTPUT_FOLDER, atlasName)


class CharacterAtlasBuilder:
    # Packs character art layer major instead of room major. Nothing here reads a
    # room layout: the sheet list comes from the customization options, the item
    # table, the spawn templates and the creature profiles, so the result is the
    # same whichever map is open.

    def __init__(self, projectRoot, packOptions = None, characterOptions = None, logCallback = None):
        self.projectRoot = projectRoot
        self.packOptions = packOptions or atlas_packer.PackOptions()
        self.characterOptions = characterOptions or CharacterAtlasOptions()
        self.logCallback = logCallback
        self.sources = sources.CharacterSources(projectRoot)

    def log(self, message):
        if self.logCallback:
            self.logCallback(message)

#region Sheet collection
    def collectSheets(self):
        kind = self.characterOptions.kind

        if kind == KIND_ACTORS:
            return self.collectActorSheets()
        if kind == KIND_NPCS:
            return self.collectNpcSheets()
        if kind == KIND_EQUIPMENT:
            return self.collectEquipmentSheets()

        raise ValueError("Unknown character atlas kind " + str(kind))

    def collectActorSheets(self):
        source = self.sources
        sheets = {}

        bodyStyles = source.bodyStyles()
        self.log("Body styles: " + ", ".join(bodyStyles))

        # Pass one: the naked body, for every body style and every anim group
        merge(sheets, source.composeBodySheets(bodyStyles))
        merge(sheets, source.composeFaceSheets(bodyStyles))
        merge(sheets, source.composeHairSheets(source.hairStyles()))
        self.log("Body pass: " + str(len(sheets)) + " sheets across " +
                 str(len(source.animGroups())) + " anim groups and " +
                 str(len(source.hairStyles())) + " hair styles")

        # Clothing a non NPC spawn wears that no item can equip. vagabond is
        # deliberately left to the equipment atlas: it is ITEM.SHIRT_VAGABOND and
        # friends, so packing it here too would duplicate every sheet.
        itemKeys = set(source.itemOutfitKeys())
        spawnKeys = []
        for spawn in source.actorSpawnPoints():
            if spawn.outfit and spawn.outfit not in itemKeys and spawn.outfit not in spawnKeys:
                spawnKeys.append(spawn.outfit)

        if spawnKeys:
            self.log("Spawn only outfits (not equippable, so not in the equipment atlas): " + ", ".join(spawnKeys))
            merge(sheets, source.composeOutfitSheets(bodyStyles, spawnKeys,
                                                     self.characterOptions.includeWrists))

        creatureSheets, families, unattributed = source.creatureSheets(
            self.characterOptions.includeUnattributedCreatures)
        merge(sheets, creatureSheets)
        self.log("Creatures: " + str(len(creatureSheets)) + " sheets from " +
                 str(len(families)) + " profiles" +
                 (", " + str(len(unattributed)) + " with no profile" if unattributed else ""))

        return sheets

    def collectNpcSheets(self):
        source = self.sources
        spawns = source.npcSpawnPoints()

        roomName = (self.characterOptions.roomName or "").strip()
        if roomName:
            placed = self.objectsPlacedInRoom(roomName)
            filtered = [spawn for spawn in spawns if spawn.objectName in placed]
            if not filtered:
                raise ValueError("No oSpawnPointAINpc children are placed in " + roomName)
            self.log("Restricted to " + roomName + ": " + str(len(filtered)) + " of " +
                     str(len(spawns)) + " NPC spawn points")
            spawns = filtered
        else:
            self.log("Every NPC spawn point in the project: " + str(len(spawns)))

        sheets = {}
        bodyStyles = []
        hairStyles = []
        outfitKeys = []

        for spawn in spawns:
            for bodyStyle in spawn.bodyStyles:
                if bodyStyle not in bodyStyles:
                    bodyStyles.append(bodyStyle)
            for hairStyle in spawn.hairStyles:
                if hairStyle not in hairStyles:
                    hairStyles.append(hairStyle)
            if spawn.outfit and spawn.outfit not in outfitKeys:
                outfitKeys.append(spawn.outfit)

        self.log("NPC body styles: " + ", ".join(bodyStyles))
        self.log("NPC outfits (" + str(len(outfitKeys)) + "): " + ", ".join(sorted(outfitKeys)))

        merge(sheets, source.composeOutfitSheets(bodyStyles, outfitKeys,
                                                 self.characterOptions.includeWrists))

        if self.characterOptions.npcIncludeBodyLayers:
            merge(sheets, source.composeBodySheets(bodyStyles))
            merge(sheets, source.composeFaceSheets(bodyStyles))
            merge(sheets, source.composeHairSheets(hairStyles))
            self.log("Body layers included so this atlas stands alone; they are also in the actors atlas")

        return sheets

    def collectEquipmentSheets(self):
        source = self.sources
        sheets = {}

        bodyStyles = source.bodyStyles()
        itemKeys = source.itemOutfitKeys()
        self.log("Equippable outfits (" + str(len(itemKeys)) + "): " + ", ".join(itemKeys))

        merge(sheets, source.composeOutfitSheets(bodyStyles, itemKeys,
                                                 self.characterOptions.includeWrists))
        merge(sheets, source.composeHeadgearSheets(source.headgearNames()))
        merge(sheets, source.weaponSheets())

        if self.characterOptions.includeItemIcons:
            merge(sheets, source.itemIconSheets())
            self.log("Item icons included")

        return sheets

    def objectsPlacedInRoom(self, roomName):
        rooms = dict(room_parser.parseProjectRooms(self.projectRoot))
        if roomName not in rooms:
            raise ValueError("Room " + str(roomName) + " was not found in the project")

        room = room_parser.parseRoom(rooms[roomName], self.packOptions.includeIgnoredInstances)
        return {instance.objectName for instance in room.instances}
#endregion

#region Ordering
    def orderSheets(self, sheets):
        # Draw order inside a pass, pass order overall. The packer walks this list
        # and starts a page whenever the break key changes, so the page a sheet
        # lands on is decided here rather than by the bin packer.
        passIndex = {name: index for index, name in enumerate(sources.PASS_ORDER)}
        slotIndex = {name: index for index, name in enumerate(sources.DRAW_ORDER)}

        def sortKey(sheet):
            return (
                passIndex.get(sheet.passName, len(passIndex)),
                slotIndex.get(sheet.slot, len(slotIndex)),
                sheet.bodyStyle,
                sheet.outfit,
                # Keeps a creature family's sheets adjacent, so a creature binds
                # one page even though the creature pass spans nine
                sheet.family,
                sheet.name
            )

        return sorted(sheets.values(), key = sortKey)

    def pageBreakKeyFor(self, sheet):
        if self.characterOptions.pageBreakPerSlot:
            return sheet.passName + "/" + sheet.slot
        if self.characterOptions.pageBreakPerPass:
            return sheet.passName
        return ""
#endregion

    def build(self, outputDir = None, writeDebugImages = False):
        options = self.characterOptions
        atlasName = self.atlasName()
        outputDir = outputDir or defaultOutputDir(self.projectRoot, atlasName)

        self.log("Building the " + KIND_LABELS.get(options.kind, options.kind) + " atlas from " + self.projectRoot)

        groupName = atlas_writer.resolveGroupName(self.packOptions, atlasName)
        existingGroups = room_parser.listTextureGroupNames(self.projectRoot)
        groupNameClash = groupName in existingGroups
        if groupNameClash:
            self.log("Warning: texture group " + groupName + " already exists in this project, "
                     "texturegroup_add raises a fatal error on an existing group name")
        else:
            self.log("Texture group name for texturegroup_add: " + groupName)

        sheets = self.collectSheets()
        if not sheets:
            raise ValueError("No character sprites were resolved for the " + options.kind + " atlas")

        self.log("Resolved " + str(len(sheets)) + " sheets the game can actually build a name for")

        orderedSheets = self.orderSheets(sheets)
        assetIndex = room_parser.ProjectAssetIndex(self.projectRoot)

        blocks = []
        missingSprites = []
        for sheet in orderedSheets:
            sprite = assetIndex.collectSpriteFrames(sheet.name)
            if not sprite:
                missingSprites.append(sheet.name)
                continue
            blocks.append(atlas_packer.AssetBlock(
                sprite = sprite,
                roomX = 0.0,
                roomY = 0.0,
                instanceCount = 0,
                objectNames = [],
                sources = [sheet.passName],
                layerNames = [sheet.slot],
                discoveredFrom = list(sheet.origins),
                hasPosition = False,
                drawDepth = 0,
                pageBreakKey = self.pageBreakKeyFor(sheet)
            ))

        if missingSprites:
            self.log("Warning: " + str(len(missingSprites)) + " resolved sheets have no readable .yy")

        packOptions = self.packOptionsForPacking()
        self.log("Packing " + str(len(blocks)) + " sheets into " +
                 str(packOptions.pageWidth) + " x " + str(packOptions.pageHeight) + " pages, " +
                 ("one page per slot" if options.pageBreakPerSlot else
                  "one page per pass" if options.pageBreakPerPass else "packed continuously"))

        packResult = atlas_packer.packGroupsIntoPages(blocks, packOptions)
        self.log("Packed onto " + str(len(packResult.pages)) + " page(s)")

        for warning in packResult.warnings:
            self.log("Warning: " + warning)

        problems = atlas_packer.validatePlacements(packResult, packOptions)
        for problem in problems:
            self.log("Problem: " + problem)

        pageFiles = atlas_writer.renderPagesToPng(packResult, packOptions, atlasName, outputDir, self.log)
        pageNames = [os.path.basename(path) for path in pageFiles]

        sheetByName = {sheet.name: sheet for sheet in orderedSheets}
        extraBySprite = {
            sheet.name: {
                "slot": sheet.slot,
                "pass": sheet.passName,
                "body_style": sheet.bodyStyle,
                "outfit": sheet.outfit,
                "anim_group": sheet.animGroup,
                "family": sheet.family
            }
            for sheet in orderedSheets
        }
        passPages = self.passPageMap(packResult, sheetByName)
        slotPages = self.slotPageMap(packResult, sheetByName)

        extraMeta = {
            "atlas": atlasName,
            "kind": options.kind,
            "source_room": options.roomName or None,
            "draw_order": sources.DRAW_ORDER,
            "pass_order": [name for name in sources.PASS_ORDER if name in passPages],
            "pass_pages": passPages,
            "slot_pages": slotPages,
            "page_per_pass": options.pageBreakPerPass,
            "page_per_slot": options.pageBreakPerSlot
        }

        metadataPath = atlas_writer.emitMetadataJson(
            packResult, packOptions, atlasName, pageNames, outputDir, extraBySprite, extraMeta
        )
        self.log("Wrote " + os.path.basename(metadataPath))

        rotatedNames = atlas_writer.rotatedFrameNames(
            atlas_writer.buildMetadata(packResult, packOptions, atlasName, pageNames)
        )
        if rotatedNames:
            message = (str(len(rotatedNames)) + " sheets were packed rotated, texturegroup_add has no member "
                       "for that. Switch rotation off for this atlas")
            self.log("Warning: " + message)
            packResult.warnings.append(message)

        debugFiles = []
        if writeDebugImages:
            debugFiles = atlas_writer.renderDebugPages(packResult, packOptions, atlasName, outputDir)
            self.log("Wrote " + str(len(debugFiles)) + " debug image(s)")

        reportPath = self.writeReport(packResult, packOptions, atlasName, outputDir, problems,
                                      sheetByName, passPages, slotPages, missingSprites)
        self.log("Wrote " + os.path.basename(reportPath))

        return {
            "atlasName": atlasName,
            "kind": options.kind,
            "packResult": packResult,
            "outputDir": outputDir,
            "pageFiles": pageFiles,
            "metadataPath": metadataPath,
            "reportPath": reportPath,
            "debugFiles": debugFiles,
            "problems": problems,
            "warnings": list(self.sources.warnings) + list(assetIndex.warnings) + list(packResult.warnings) +
                        ([groupName + " is already a texture group in this project, texturegroup_add will fail on it"]
                         if groupNameClash else []),
            "groupName": groupName,
            "groupNameClash": groupNameClash,
            "missingSprites": missingSprites,
            "passPages": passPages,
            "slotPages": slotPages,
            "sheetCount": len(blocks),
            "frameCount": sum(block.sprite.frameCount for block in blocks)
        }

    def atlasName(self):
        base = DEFAULT_ATLAS_NAMES.get(self.characterOptions.kind, self.characterOptions.kind)
        if self.characterOptions.kind == KIND_NPCS and self.characterOptions.roomName:
            return base + "_" + self.characterOptions.roomName
        return base

    def packOptionsForPacking(self):
        # The room packer's grouping options mean nothing here, so the character
        # options overwrite the two that do.
        options = atlas_packer.PackOptions(**vars(self.packOptions))
        options.breakPagesOnKeyChange = (self.characterOptions.pageBreakPerPass or
                                         self.characterOptions.pageBreakPerSlot)
        return options

#region Reporting
    def passPageMap(self, packResult, sheetByName):
        return self.pageMapBy(packResult, sheetByName, lambda sheet: sheet.passName)

    def slotPageMap(self, packResult, sheetByName):
        return self.pageMapBy(packResult, sheetByName, lambda sheet: sheet.slot)

    def pageMapBy(self, packResult, sheetByName, keyOf):
        # Which pages a draw pass has to bind. This is the number the draw
        # controller cares about: one page per pass means one bind per pass.
        pages = {}

        for page in packResult.pages:
            for blockPlacement in page.blocks:
                sheet = sheetByName.get(blockPlacement.block.spriteName)
                if not sheet:
                    continue
                indices = pages.setdefault(keyOf(sheet), [])
                if page.index not in indices:
                    indices.append(page.index)

        return {key: sorted(indices) for key, indices in pages.items()}

    def writeReport(self, packResult, packOptions, atlasName, outputDir, problems,
                    sheetByName, passPages, slotPages, missingSprites):
        lines = []
        lines.append("Character atlas pack report")
        lines.append("Atlas: " + atlasName + "  (" + KIND_LABELS.get(self.characterOptions.kind, "") + ")")
        lines.append("Texture group name: " + atlas_writer.resolveGroupName(packOptions, atlasName))
        lines.append("Page size: " + str(packOptions.pageWidth) + " x " + str(packOptions.pageHeight))
        lines.append("Padding: " + str(packOptions.padding))
        lines.append("Rotation allowed: " + str(packOptions.allowRotation))
        if self.characterOptions.roomName:
            lines.append("Restricted to room: " + self.characterOptions.roomName)
        lines.append("Page break: " + ("per slot" if self.characterOptions.pageBreakPerSlot else
                                       "per pass" if self.characterOptions.pageBreakPerPass else "none"))
        lines.append("")

        lines.append("Pages a draw pass has to bind:")
        for passName in sources.PASS_ORDER:
            if passName not in passPages:
                continue
            indices = passPages[passName]
            lines.append("    " + passName + ": page(s) " + ", ".join(str(index) for index in indices) +
                         ("   ONE BIND" if len(indices) == 1 else "   " + str(len(indices)) + " binds"))
        lines.append("")

        lines.append("Sheets and pixels per draw slot, in draw order:")
        byKey = {}
        for page in packResult.pages:
            for blockPlacement in page.blocks:
                sheet = sheetByName.get(blockPlacement.block.spriteName)
                if not sheet:
                    continue
                counts = byKey.setdefault(sheet.slot, [0, 0])
                counts[0] += 1
                counts[1] += sum(frame.width * frame.height for frame in blockPlacement.frames)

        for slot in sources.DRAW_ORDER + [sources.SLOT_WRISTS, sources.SLOT_WEAPON,
                                          sources.SLOT_CREATURE, sources.SLOT_ICON]:
            if slot not in byKey:
                continue
            counts = byKey[slot]
            lines.append("    " + slot.ljust(12) + str(counts[0]).rjust(5) + " sheets  " +
                         ("%8.2f" % (counts[1] / 1000000.0)) + " Mpx   pages " +
                         ", ".join(str(index) for index in slotPages.get(slot, [])))
        lines.append("")

        familyPages = {}
        for page in packResult.pages:
            for blockPlacement in page.blocks:
                sheet = sheetByName.get(blockPlacement.block.spriteName)
                if not sheet or sheet.slot != sources.SLOT_CREATURE:
                    continue
                entry = familyPages.setdefault(sheet.family or "(no profile)", [0, 0, []])
                entry[0] += 1
                entry[1] += sum(frame.width * frame.height for frame in blockPlacement.frames)
                if page.index not in entry[2]:
                    entry[2].append(page.index)

        if familyPages:
            lines.append("Creature families and the pages they bind (a creature draws one sheet, not a layer stack):")
            for family in sorted(familyPages, key = lambda name: -familyPages[name][1]):
                sheetCount, pixels, indices = familyPages[family]
                lines.append("    " + family.ljust(18) + str(sheetCount).rjust(4) + " sheets  " +
                             ("%7.2f" % (pixels / 1000000.0)) + " Mpx   page(s) " +
                             ", ".join(str(index) for index in sorted(indices)) +
                             ("" if len(indices) == 1 else "   SPANS " + str(len(indices))))
            lines.append("")

        if missingSprites:
            lines.append("Resolved but unreadable (" + str(len(missingSprites)) + "):")
            for name in missingSprites:
                lines.append("    " + name)
            lines.append("")

        totalFrames = 0
        for page in packResult.pages:
            placements = page.framePlacements()
            totalFrames += len(placements)
            usedPixels = sum(placement.width * placement.height for placement in placements)
            coverage = 100.0 * usedPixels / float(packOptions.pageWidth * packOptions.pageHeight)

            passNames = sorted({sheetByName[blockPlacement.block.spriteName].passName
                                for blockPlacement in page.blocks
                                if blockPlacement.block.spriteName in sheetByName})

            lines.append("Page " + str(page.index) + ": " + str(len(page.blocks)) + " sheets, " +
                         ("%.1f" % coverage) + " percent covered, pass " + ", ".join(passNames))

            for blockPlacement in page.blocks:
                block = blockPlacement.block
                sheet = sheetByName.get(block.spriteName)
                lines.append("    " + block.spriteName.ljust(44) +
                             (sheet.slot if sheet else "?").ljust(12) +
                             "at(" + str(blockPlacement.x) + "," + str(blockPlacement.y) + ") " +
                             str(blockPlacement.width) + "x" + str(blockPlacement.height))

        lines.append("")
        lines.append("Total pages: " + str(len(packResult.pages)))
        lines.append("Total sheets placed: " + str(sum(len(page.blocks) for page in packResult.pages)))
        lines.append("Total frames placed: " + str(totalFrames))

        if packResult.skippedBlocks:
            lines.append("")
            lines.append("Skipped sheets:")
            for block in packResult.skippedBlocks:
                lines.append("    " + block.spriteName)

        warnings = list(self.sources.warnings) + list(packResult.warnings)
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in warnings:
                lines.append("    " + warning)

        lines.append("")
        if problems:
            lines.append("Validation FAILED:")
            for problem in problems:
                lines.append("    " + problem)
        else:
            lines.append("Validation passed: no overlaps, all frames in order and inside the page bounds")

        outputPath = os.path.join(outputDir, atlas_writer.reportFileName(atlasName))
        with open(outputPath, 'w', encoding = 'utf-8') as file:
            file.write("\n".join(lines))

        return outputPath
#endregion


def merge(target, addition):
    # Same sheet reached two ways keeps both origins, so the report can say a
    # torso came from both the vagabond item and a spawn template.
    for name, sheet in addition.items():
        existing = target.get(name)
        if existing is None:
            target[name] = sheet
            continue
        for origin in sheet.origins:
            existing.addOrigin(origin)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description = "Pack the character art this project can build, layer major, for the actor draw controller")
    parser.add_argument("project", help = "GameMaker project root directory")
    parser.add_argument("kind", choices = [KIND_ACTORS, KIND_NPCS, KIND_EQUIPMENT])
    parser.add_argument("--room", default = "", help = "NPC atlas only: restrict to the spawn points placed in this room")
    parser.add_argument("--output", default = None)
    parser.add_argument("--group-name", default = "")
    parser.add_argument("--page-size", type = int, default = 4096)
    parser.add_argument("--padding", type = int, default = 2)
    parser.add_argument("--oversize", choices = ["skip", "scale"], default = "skip")
    parser.add_argument("--no-page-per-pass", action = "store_true")
    parser.add_argument("--page-per-slot", action = "store_true")
    parser.add_argument("--no-npc-body-layers", action = "store_true")
    parser.add_argument("--include-icons", action = "store_true")
    parser.add_argument("--include-wrists", action = "store_true")
    parser.add_argument("--no-unattributed-creatures", action = "store_true")
    parser.add_argument("--debug-images", action = "store_true")
    arguments = parser.parse_args()

    packOptions = atlas_packer.PackOptions(
        pageWidth = arguments.page_size,
        pageHeight = arguments.page_size,
        padding = arguments.padding,
        oversizePolicy = arguments.oversize,
        groupName = arguments.group_name,
        allowRotation = False
    )

    characterOptions = CharacterAtlasOptions(
        kind = arguments.kind,
        roomName = arguments.room,
        npcIncludeBodyLayers = not arguments.no_npc_body_layers,
        includeItemIcons = arguments.include_icons,
        includeWrists = arguments.include_wrists,
        includeUnattributedCreatures = not arguments.no_unattributed_creatures,
        pageBreakPerPass = not arguments.no_page_per_pass,
        pageBreakPerSlot = arguments.page_per_slot
    )

    builder = CharacterAtlasBuilder(arguments.project, packOptions, characterOptions, print)
    result = builder.build(arguments.output, arguments.debug_images)
    print("Done, output in " + result["outputDir"])


if __name__ == "__main__":
    main()
