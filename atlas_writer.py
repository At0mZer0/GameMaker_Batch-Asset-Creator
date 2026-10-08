import json
import os

from PIL import Image, ImageDraw


def pageFileName(roomName, pageIndex):
    return roomName + "_page_" + str(pageIndex) + ".png"


def metadataFileName(roomName):
    return roomName + "_atlas.json"


def reportFileName(roomName):
    return roomName + "_pack_report.txt"


#region PNG output
def renderPagesToPng(packResult, options, roomName, outputDir, progressCallback = None):
    # Draws every placed frame onto its texture page and writes one PNG per page
    os.makedirs(outputDir, exist_ok = True)
    writtenFiles = []

    for page in packResult.pages:
        pageImage = Image.new("RGBA", (options.pageWidth, options.pageHeight), (0, 0, 0, 0))

        for blockPlacement in page.blocks:
            for placement in blockPlacement.frames:
                frameImage = loadFrameImage(placement)
                if frameImage is None:
                    continue
                pageImage.paste(frameImage, (placement.x, placement.y))
                frameImage.close()

        outputPath = os.path.join(outputDir, pageFileName(roomName, page.index))
        pageImage.save(outputPath)
        pageImage.close()
        writtenFiles.append(outputPath)

        if progressCallback:
            progressCallback("Wrote " + os.path.basename(outputPath))

    return writtenFiles


def loadFrameImage(placement):
    # Returns the frame image already scaled and rotated to match its placement
    try:
        with Image.open(placement.imagePath) as source:
            image = source.convert("RGBA")
    except Exception:
        return None

    if placement.rotated:
        targetWidth, targetHeight = placement.height, placement.width
    else:
        targetWidth, targetHeight = placement.width, placement.height

    if image.size != (targetWidth, targetHeight):
        image = image.resize((targetWidth, targetHeight), Image.LANCZOS)

    if placement.rotated:
        # ROTATE_270 in PIL is a 90 degree clockwise turn
        image = image.transpose(Image.ROTATE_270)

    return image


def renderDebugPages(packResult, options, roomName, outputDir):
    # Draws the packed rectangles and sprite names so a page can be eyeballed
    os.makedirs(outputDir, exist_ok = True)
    writtenFiles = []
    outlineColours = [(0, 255, 128, 255), (255, 196, 0, 255), (0, 168, 255, 255), (255, 96, 160, 255)]

    for page in packResult.pages:
        debugImage = Image.new("RGBA", (options.pageWidth, options.pageHeight), (24, 24, 28, 255))
        draw = ImageDraw.Draw(debugImage)

        for blockIndex, blockPlacement in enumerate(page.blocks):
            colour = outlineColours[blockIndex % len(outlineColours)]

            draw.rectangle(
                [blockPlacement.x, blockPlacement.y,
                 blockPlacement.x + blockPlacement.width - 1,
                 blockPlacement.y + blockPlacement.height - 1],
                outline = colour
            )

            for placement in blockPlacement.frames:
                draw.rectangle(
                    [placement.x, placement.y,
                     placement.x + placement.width - 1,
                     placement.y + placement.height - 1],
                    outline = (110, 110, 120, 255)
                )

            label = blockPlacement.block.spriteName
            if blockPlacement.rotated:
                label = label + " (rotated)"
            draw.text((blockPlacement.x + 2, blockPlacement.y + 2), label, fill = colour)

        outputPath = os.path.join(outputDir, roomName + "_page_" + str(page.index) + "_debug.png")
        debugImage.save(outputPath)
        debugImage.close()
        writtenFiles.append(outputPath)

    return writtenFiles
#endregion


#region Metadata output
# texturegroup_add reads sprites.<name>.width / height / frames[].x / y, and
# the optional members below. The reporting keys it does not know about are
# left in place, they are ignored on the GameMaker side.
def resolveGroupName(options, roomName):
    # texturegroup_add fails fatally on a name that already exists in the
    # project, so this never defaults to one of the built in group names
    return (options.groupName or "").strip() or roomName


def buildMetadata(packResult, options, roomName, pageNames, extraBySprite = None, extraMeta = None):
    # extraBySprite and extraMeta are how the character atlas adds what a draw
    # controller needs - the slot and the pass each sheet belongs to, and which
    # pages a pass has to bind - without a second copy of this function.
    # texturegroup_add ignores members it does not know, so the extra keys ride
    # along harmlessly.
    sprites = {}

    for page in packResult.pages:
        for blockPlacement in page.blocks:
            block = blockPlacement.block
            scaledWidth = block.cellWidth
            scaledHeight = block.cellHeight

            entry = {
                "width": scaledWidth,
                "height": scaledHeight,
                "frames": [
                    {
                        "x": placement.x,
                        "y": placement.y,
                        "w": placement.width,
                        "h": placement.height,
                        "tp": placement.page,
                        "page": placement.page,
                        "frame_index": placement.frameIndex,
                        "rotated": placement.rotated
                    }
                    for placement in sorted(blockPlacement.frames, key = lambda placement: placement.frameIndex)
                ],
                "xoffset": int(round(block.sprite.originX * block.scale)),
                "yoffset": int(round(block.sprite.originY * block.scale)),
                "frame_speed": block.sprite.playbackSpeed,
                "frame_type": block.sprite.playbackSpeedType,
                "bbox_left": int(round(block.sprite.bboxLeft * block.scale)),
                "bbox_right": int(round(block.sprite.bboxRight * block.scale)),
                "bbox_top": int(round(block.sprite.bboxTop * block.scale)),
                "bbox_bottom": int(round(block.sprite.bboxBottom * block.scale)),
                "bbox_kind": block.sprite.collisionKind,
                "origin": [
                    int(round(block.sprite.originX * block.scale)),
                    int(round(block.sprite.originY * block.scale))
                ],
                "frame_count": block.sprite.frameCount,
                "animation_length": block.sprite.frameCount,
                "texture_group": block.sprite.textureGroup,
                "objects": block.objectNames,
                "sources": block.sources,
                "room_position": [round(block.roomX, 2), round(block.roomY, 2)],
                "instance_count": block.instanceCount
            }

            if block.scale != 1.0:
                for frame in entry["frames"]:
                    frame["original_width"] = block.sprite.width
                    frame["original_height"] = block.sprite.height

            if block.layerNames:
                entry["layer_name"] = block.layerNames[0]
                if len(block.layerNames) > 1:
                    entry["layer_names"] = block.layerNames

            if block.discoveredFrom:
                entry["discovered_from"] = block.discoveredFrom

            if not block.hasPosition:
                entry["code_only"] = True

            if block.scale != 1.0:
                entry["scale"] = round(block.scale, 4)

            if extraBySprite:
                entry.update(extraBySprite.get(block.spriteName, {}))

            sprites[block.spriteName] = entry

    meta = {
        "room": roomName,
        "group_name": resolveGroupName(options, roomName),
        "page_size": [options.pageWidth, options.pageHeight],
        "padding": options.padding,
        "grid_cell_size": options.gridSize,
        "rotation_allowed": options.allowRotation,
        "pages": pageNames,
        "generator": "GMS2 Object and Sprite Batch Asset Creator"
    }

    if extraMeta:
        meta.update(extraMeta)

    return {
        "meta": meta,
        "sprites": {name: sprites[name] for name in sorted(sprites)}
    }


def emitMetadataJson(packResult, options, roomName, pageNames, outputDir, extraBySprite = None, extraMeta = None):
    metadata = buildMetadata(packResult, options, roomName, pageNames, extraBySprite, extraMeta)
    outputPath = os.path.join(outputDir, metadataFileName(roomName))

    with open(outputPath, 'w', encoding = 'utf-8') as file:
        json.dump(metadata, file, indent = 2)

    return outputPath


# Members texturegroup_add reads, everything else in the atlas json is ours
TEXTURE_GROUP_SPRITE_MEMBERS = [
    "width", "height", "xoffset", "yoffset", "frame_speed", "frame_type",
    "bbox_left", "bbox_right", "bbox_top", "bbox_bottom", "bbox_kind"
]
TEXTURE_GROUP_FRAME_MEMBERS = [
    "x", "y", "w", "h", "tp", "x_offset", "y_offset",
    "crop_width", "crop_height", "original_width", "original_height"
]


def minimalTextureGroupStruct(metadata):
    # Strips the atlas json down to exactly what texturegroup_add reads, for a
    # loader that just does json_parse and hands the struct straight over.
    # tp is the index into the file array passed as the second argument, which
    # is metadata["meta"]["pages"] in order.
    sprites = {}

    for spriteName in sorted(metadata["sprites"]):
        entry = metadata["sprites"][spriteName]
        sprite = {member: entry[member] for member in TEXTURE_GROUP_SPRITE_MEMBERS if member in entry}
        sprite["frames"] = [
            {member: frame[member] for member in TEXTURE_GROUP_FRAME_MEMBERS if member in frame}
            for frame in entry["frames"]
        ]
        sprites[spriteName] = sprite

    return {"sprites": sprites}


def rotatedFrameNames(metadata):
    # texturegroup_add has no member for a rotated frame, so a rotated pack
    # cannot be described by the struct it takes
    return sorted(name for name, entry in metadata["sprites"].items()
                  if any(frame.get("rotated") for frame in entry["frames"]))
#endregion


#region Verification report
def codeScanContributors(packResult):
    # Pixels each object dragged in through the code scan alone, so the report
    # can name the objects worth putting on the exclude list
    contributors = {}

    for page in packResult.pages:
        for blockPlacement in page.blocks:
            block = blockPlacement.block
            if block.sources != ["code"]:
                continue

            pixels = sum(frame.width * frame.height for frame in blockPlacement.frames)
            owners = sorted({origin.split(" ")[0] for origin in block.discoveredFrom if origin}) or ["unknown"]

            for owner in owners:
                counts = contributors.setdefault(owner, [0, 0])
                counts[0] += 1
                counts[1] += pixels // len(owners)

    return contributors


def buildReportLines(packResult, options, roomName, problems, extraWarnings, discovery = None, missingSprites = None):
    lines = []
    lines.append("Room atlas pack report")
    lines.append("Room: " + roomName)
    lines.append("Texture group name: " + resolveGroupName(options, roomName))
    lines.append("Page size: " + str(options.pageWidth) + " x " + str(options.pageHeight))
    lines.append("Padding: " + str(options.padding))
    lines.append("Grid cell size: " + str(options.gridSize))
    lines.append("Rotation allowed: " + str(options.allowRotation))
    lines.append("Oversize policy: " + options.oversizePolicy)
    lines.append("Grouping order: " + options.orderBy)
    lines.append("Second pass into object code: " + str(options.scanObjectCode))
    if options.excludeCodeScanObjects:
        lines.append("Code scan excludes: " + ", ".join(options.excludeCodeScanObjects))
    if options.excludeLayers:
        lines.append("Layer excludes: " + ", ".join(options.excludeLayers))
    lines.append("Random choice lists included: " + str(options.includeRandomChoiceLists))
    lines.append("Tilesets ignored: " + str(options.ignoreTilesets))
    lines.append("")

    if discovery is not None:
        lines.append("Sprites found, by where they came from:")
        for source in sorted(discovery.countsBySource()):
            lines.append("    " + source + ": " + str(discovery.countsBySource()[source]))
        lines.append("    objects scanned: " + str(len(discovery.scannedObjects)))
        lines.append("    scripts scanned: " + str(len(discovery.scannedScripts)))
        lines.append("")

        for sourceKind in ["sprite_layer", "code"]:
            names = sorted(name for name, entry in discovery.discovered.items() if sourceKind in entry.sources)
            lines.append(sourceKind + " sprites (" + str(len(names)) + "):")
            for name in names:
                lines.append("    " + name)
            lines.append("")

    contributors = codeScanContributors(packResult)
    if contributors:
        lines.append("Sprites pulled in by the code scan alone, by originating object:")
        ranked = sorted(contributors.items(), key = lambda entry: entry[1][1], reverse = True)
        for owner, counts in ranked[:15]:
            lines.append("    " + owner + ": " + str(counts[0]) + " sprites, " +
                         ("%.2f" % (counts[1] / 1000000.0)) + " Mpixels")
        lines.append("    (put the heavy ones on the code scan exclude list)")
        lines.append("")

    if missingSprites:
        lines.append("Referenced but missing on disk (" + str(len(missingSprites)) + "):")
        for name in missingSprites:
            lines.append("    " + name)
        lines.append("")

    totalFrames = 0
    for page in packResult.pages:
        placements = page.framePlacements()
        totalFrames += len(placements)
        usedPixels = sum(placement.width * placement.height for placement in placements)
        coverage = 100.0 * usedPixels / float(options.pageWidth * options.pageHeight)

        lines.append("Page " + str(page.index) + ": " + str(len(page.blocks)) + " sprites, " +
                     str(len(placements)) + " frames, " + ("%.1f" % coverage) + " percent covered")

        for blockPlacement in page.blocks:
            block = blockPlacement.block
            lines.append("    " + block.spriteName +
                         "  cell(" + str(block.cellX) + "," + str(block.cellY) + ")" +
                         "  room(" + str(int(block.roomX)) + "," + str(int(block.roomY)) + ")" +
                         "  at(" + str(blockPlacement.x) + "," + str(blockPlacement.y) + ")" +
                         "  " + str(blockPlacement.width) + "x" + str(blockPlacement.height) +
                         "  frames " + str(block.sprite.frameCount) +
                         ("  rotated" if blockPlacement.rotated else ""))

    lines.append("")
    lines.append("Total pages: " + str(len(packResult.pages)))
    lines.append("Total frames placed: " + str(totalFrames))

    if packResult.skippedBlocks:
        lines.append("")
        lines.append("Skipped sprites:")
        for block in packResult.skippedBlocks:
            lines.append("    " + block.spriteName)

    warnings = list(extraWarnings) + list(packResult.warnings)
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

    return lines


def writeReport(packResult, options, roomName, outputDir, problems, extraWarnings, discovery = None, missingSprites = None):
    lines = buildReportLines(packResult, options, roomName, problems, extraWarnings, discovery, missingSprites)
    outputPath = os.path.join(outputDir, reportFileName(roomName))

    with open(outputPath, 'w', encoding = 'utf-8') as file:
        file.write("\n".join(lines))

    return outputPath
#endregion
