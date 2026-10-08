import os

import atlas_packer
import atlas_writer
import exclude_presets
import room_parser
import sprite_discovery


DEFAULT_OUTPUT_FOLDER = "packed_atlases"


def defaultOutputDir(projectRoot, roomName):
    return os.path.join(projectRoot, DEFAULT_OUTPUT_FOLDER, roomName)


class RoomAtlasBuilder:
    # Ties the room parser, the spatial grouping, the packer and the writers
    # together. Nothing here touches tkinter so it can also be run headless.

    def __init__(self, projectRoot, options = None, logCallback = None):
        self.projectRoot = projectRoot
        self.options = options or atlas_packer.PackOptions()
        self.logCallback = logCallback

    def log(self, message):
        if self.logCallback:
            self.logCallback(message)

    def listRooms(self):
        return room_parser.parseProjectRooms(self.projectRoot)

    def build(self, roomName, outputDir = None, writeDebugImages = False):
        rooms = dict(self.listRooms())
        if roomName not in rooms:
            raise ValueError("Room " + str(roomName) + " was not found in the project")

        outputDir = outputDir or defaultOutputDir(self.projectRoot, roomName)

        groupName = atlas_writer.resolveGroupName(self.options, roomName)
        existingGroups = room_parser.listTextureGroupNames(self.projectRoot)
        groupNameClash = groupName in existingGroups
        if groupNameClash:
            self.log("Warning: texture group " + groupName + " already exists in this project, "
                     "texturegroup_add raises a fatal error on an existing group name")
        else:
            self.log("Texture group name for texturegroup_add: " + groupName)

        self.log("Parsing room " + roomName)
        room = room_parser.parseRoom(rooms[roomName], self.options.includeIgnoredInstances)
        self.log("Room is " + str(room.width) + " x " + str(room.height) +
                 " with " + str(len(room.instances)) + " placed instances, " +
                 str(len(room.spriteGraphics)) + " sprite layer graphics and " +
                 str(len(room.tileLayers)) + " tile layers")

        assetIndex = room_parser.ProjectAssetIndex(self.projectRoot)
        symbolIndex = sprite_discovery.ProjectSymbolIndex(self.projectRoot)

        discovery = sprite_discovery.RoomSpriteDiscovery(
            self.projectRoot, assetIndex, symbolIndex, self.options, self.log
        )
        discoveredSprites = discovery.discover(room)

        blocks, missingSprites = atlas_packer.buildAssetBlocks(discoveredSprites, assetIndex)
        frameTotal = sum(block.sprite.frameCount for block in blocks)
        self.log("Collected " + str(len(blocks)) + " sprites and " + str(frameTotal) + " frames")

        objectsWithoutSprite = discovery.objectsWithoutSprite
        if objectsWithoutSprite:
            self.log("Skipped " + str(len(objectsWithoutSprite)) + " objects with no sprite assigned")
        if missingSprites:
            self.log("Warning: " + str(len(missingSprites)) + " referenced sprites are missing on disk")

        if not blocks:
            raise ValueError("No sprites were found for the objects placed in " + roomName)

        self.log("Grouping by " + self.options.orderBy + ", grid cell " + str(self.options.gridSize) + " px")
        groupedBlocks = atlas_packer.groupAssetsBySpatialProximity(
            blocks, self.options.gridSize, self.options.orderBy
        )

        self.log("Packing into " + str(self.options.pageWidth) + " x " + str(self.options.pageHeight) + " pages")
        packResult = atlas_packer.packGroupsIntoPages(groupedBlocks, self.options)
        self.log("Packed onto " + str(len(packResult.pages)) + " page(s)")

        for warning in packResult.warnings:
            self.log("Warning: " + warning)

        self.log("Validating placements")
        problems = atlas_packer.validatePlacements(packResult, self.options)
        for problem in problems:
            self.log("Problem: " + problem)

        self.log("Writing texture pages")
        pageFiles = atlas_writer.renderPagesToPng(packResult, self.options, roomName, outputDir, self.log)
        pageNames = [os.path.basename(path) for path in pageFiles]

        metadataPath = atlas_writer.emitMetadataJson(packResult, self.options, roomName, pageNames, outputDir)
        self.log("Wrote " + os.path.basename(metadataPath))

        # texturegroup_add cannot describe a rotated frame, so say so loudly
        rotatedNames = atlas_writer.rotatedFrameNames(
            atlas_writer.buildMetadata(packResult, self.options, roomName, pageNames)
        )
        if rotatedNames:
            message = (str(len(rotatedNames)) + " sprites were packed rotated, texturegroup_add has no member "
                       "for that. Switch rotation off if this atlas is for texturegroup_add")
            self.log("Warning: " + message)
            packResult.warnings.append(message)

        debugFiles = []
        if writeDebugImages:
            debugFiles = atlas_writer.renderDebugPages(packResult, self.options, roomName, outputDir)
            self.log("Wrote " + str(len(debugFiles)) + " debug image(s)")

        reportPath = atlas_writer.writeReport(
            packResult, self.options, roomName, outputDir, problems,
            list(assetIndex.warnings) + list(discovery.warnings), discovery, missingSprites
        )
        self.log("Wrote " + os.path.basename(reportPath))

        return {
            "room": room,
            "packResult": packResult,
            "outputDir": outputDir,
            "pageFiles": pageFiles,
            "metadataPath": metadataPath,
            "reportPath": reportPath,
            "debugFiles": debugFiles,
            "problems": problems,
            "warnings": list(assetIndex.warnings) + list(discovery.warnings) + list(packResult.warnings) +
                        ([groupName + " is already a texture group in this project, texturegroup_add will fail on it"]
                         if groupNameClash else []),
            "groupName": groupName,
            "groupNameClash": groupNameClash,
            "objectsWithoutSprite": objectsWithoutSprite,
            "missingSprites": missingSprites,
            "discovery": discovery,
            "excludedObjects": discovery.excludedObjects,
            "excludedLayers": discovery.excludedLayers,
            "buildingFiles": discovery.buildingFiles,
            "spriteCount": len(blocks),
            "frameCount": frameTotal
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description = "Pack the sprites used by a GameMaker room into texture pages")
    parser.add_argument("project", help = "GameMaker project root directory")
    parser.add_argument("room", nargs = "?", help = "Room name, omit to list the rooms in the project")
    parser.add_argument("--output", default = None, help = "Output directory")
    parser.add_argument("--group-name", default = "", help = "Texture group name for texturegroup_add, defaults to the room name")
    parser.add_argument("--page-size", type = int, default = 4096)
    parser.add_argument("--padding", type = int, default = 2)
    parser.add_argument("--grid-size", type = int, default = 256)
    parser.add_argument("--order-by", choices = ["depth", "position"], default = "depth",
                        help = "depth follows GameMaker draw order, position uses the room grid alone")
    parser.add_argument("--preset", default = exclude_presets.DEFAULT_PRESET_NAME,
                        choices = exclude_presets.presetNames(),
                        help = "named exclusion preset, see exclude_presets.py")
    parser.add_argument("--exclude-objects", default = None,
                        help = "comma separated object names, wildcards allowed, replaces the preset object list")
    parser.add_argument("--exclude-layers", default = None,
                        help = "comma separated layer names, wildcards allowed, replaces the preset layer list")
    parser.add_argument("--no-building-json", action = "store_true",
                        help = "skip the oBuildingJSON Included File lookup")
    parser.add_argument("--allow-rotation", action = "store_true")
    parser.add_argument("--oversize", choices = ["skip", "scale"], default = "skip")
    parser.add_argument("--include-ignored", action = "store_true")
    parser.add_argument("--no-code-scan", action = "store_true", help = "skip the second pass into object code")
    parser.add_argument("--no-random-lists", action = "store_true", help = "only take direct sprite assignments from code")
    parser.add_argument("--include-tilesets", action = "store_true", help = "also pack the sprite behind each tileset")
    parser.add_argument("--debug-images", action = "store_true")
    arguments = parser.parse_args()

    options = atlas_packer.PackOptions(
        pageWidth = arguments.page_size,
        pageHeight = arguments.page_size,
        padding = arguments.padding,
        gridSize = arguments.grid_size,
        allowRotation = arguments.allow_rotation,
        oversizePolicy = arguments.oversize,
        includeIgnoredInstances = arguments.include_ignored,
        groupName = arguments.group_name,
        scanObjectCode = not arguments.no_code_scan,
        includeRandomChoiceLists = not arguments.no_random_lists,
        ignoreTilesets = not arguments.include_tilesets,
        orderBy = arguments.order_by,
        excludeCodeScanObjects = (exclude_presets.fromCommaText(arguments.exclude_objects)
                                  if arguments.exclude_objects is not None
                                  else exclude_presets.presetObjects(arguments.preset)),
        excludeLayers = (exclude_presets.fromCommaText(arguments.exclude_layers)
                         if arguments.exclude_layers is not None
                         else exclude_presets.presetLayers(arguments.preset)),
        buildingJsonObjects = [] if arguments.no_building_json else ["oBuildingJSON"]
    )

    builder = RoomAtlasBuilder(arguments.project, options, print)

    if not arguments.room:
        for roomName, roomPath in builder.listRooms():
            print(roomName)
        return

    result = builder.build(arguments.room, arguments.output, arguments.debug_images)
    print("Done, output in " + result["outputDir"])


if __name__ == "__main__":
    main()
