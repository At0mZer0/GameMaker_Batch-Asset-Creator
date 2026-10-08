import math
from dataclasses import dataclass, field


#region Options and data classes
@dataclass
class PackOptions:
    pageWidth: int = 4096
    pageHeight: int = 4096
    padding: int = 2
    gridSize: int = 256
    allowRotation: bool = False
    oversizePolicy: str = "skip"      # "skip" or "scale"
    includeIgnoredInstances: bool = False
    # Name handed to texturegroup_add. Empty means use the room name.
    groupName: str = ""

    # "depth" follows GameMaker draw order, higher depth first, then position
    # inside each layer. "position" ignores layers and uses the room grid alone.
    orderBy: str = "depth"

    # Second pass discovery
    scanObjectCode: bool = True
    # Object names whose code is not scanned. Accepts wildcards, e.g. "*Ctrl".
    # Controllers reach half the project through their code, which bloats a
    # room atlas with art the room never draws.
    excludeCodeScanObjects: list = field(default_factory = list)
    # Layer names, wildcards allowed, whose contents are left out of the atlas
    # entirely. UI and GUI layers are not part of the map the room draws.
    excludeLayers: list = field(default_factory = list)

    # oBuildingJSON style objects load their contents from an Included File at
    # runtime, so the objects they build are only named in that json. An empty
    # list switches the lookup off.
    buildingJsonObjects: list = field(default_factory = lambda: ["oBuildingJSON"])
    buildingNameProperty: str = "buildingName"
    includeRandomChoiceLists: bool = True
    ignoreTilesets: bool = True
    followSpawnedObjects: bool = True
    followScriptReferences: bool = True
    maxObjectDepth: int = 2
    maxScriptDepth: int = 1
    maxScannedFiles: int = 4000

    # Start a new page whenever the block's pageBreakKey changes. A room atlas
    # leaves this off and lets proximity decide. A character atlas turns it on so
    # a draw pass is guaranteed to own whole pages: if the body pass and the
    # clothing pass shared a page, the pass that binds it would drag the other
    # one's sheets into memory with it.
    breakPagesOnKeyChange: bool = False


@dataclass
class AssetBlock:
    # One sprite and every frame it owns, kept together as a single rectangle
    sprite: object
    roomX: float
    roomY: float
    instanceCount: int
    objectNames: list = field(default_factory = list)
    sources: list = field(default_factory = list)
    layerNames: list = field(default_factory = list)
    discoveredFrom: list = field(default_factory = list)
    hasPosition: bool = True
    drawDepth: int = 0
    # Set by the character atlas so a page never spans two draw passes, see
    # PackOptions.breakPagesOnKeyChange. Empty for a room pack.
    pageBreakKey: str = ""
    cellX: int = 0
    cellY: int = 0
    scale: float = 1.0
    columns: int = 1
    rows: int = 1
    cellWidth: int = 0
    cellHeight: int = 0
    width: int = 0
    height: int = 0

    @property
    def spriteName(self):
        return self.sprite.name


@dataclass
class FramePlacement:
    spriteName: str
    frameIndex: int
    imagePath: str
    page: int
    x: int
    y: int
    width: int
    height: int
    rotated: bool = False
    scale: float = 1.0


@dataclass
class BlockPlacement:
    block: AssetBlock
    page: int
    x: int
    y: int
    rotated: bool = False
    frames: list = field(default_factory = list)

    @property
    def width(self):
        return self.block.height if self.rotated else self.block.width

    @property
    def height(self):
        return self.block.width if self.rotated else self.block.height


@dataclass
class PackedPage:
    index: int
    blocks: list = field(default_factory = list)

    def framePlacements(self):
        placements = []
        for blockPlacement in self.blocks:
            placements.extend(blockPlacement.frames)
        return placements


@dataclass
class PackResult:
    pages: list = field(default_factory = list)
    skippedBlocks: list = field(default_factory = list)
    warnings: list = field(default_factory = list)
#endregion


#region Asset block building and spatial grouping
def buildAssetBlocks(discoveredSprites, assetIndex):
    # Turns the discovery result into one block per sprite. A sprite used many
    # times is still packed once, its instance positions only decide grouping.
    blocks = []
    missingSprites = []

    for spriteName in sorted(discoveredSprites):
        entry = discoveredSprites[spriteName]
        sprite = assetIndex.collectSpriteFrames(spriteName)
        if not sprite:
            missingSprites.append(spriteName)
            continue

        centroidX, centroidY = entry.centroid

        blocks.append(AssetBlock(
            sprite = sprite,
            roomX = centroidX,
            roomY = centroidY,
            instanceCount = len(entry.positions),
            objectNames = sorted(entry.objectNames),
            sources = sorted(entry.sources),
            layerNames = sorted(entry.layerNames),
            discoveredFrom = sorted(entry.discoveredFrom),
            hasPosition = entry.hasPosition,
            drawDepth = entry.drawDepth
        ))

    return blocks, missingSprites


def groupAssetsBySpatialProximity(blocks, gridSize, orderBy = "position"):
    # Drops every positioned block into a coarse grid cell, then orders the
    # cells top left to bottom right so blocks that sit near each other in the
    # room are handed to the packer one after the other. Blocks with no position
    # at all, found only in code, are appended after them and kept together by
    # resource name.
    gridSize = max(1, int(gridSize))

    for block in blocks:
        block.cellX = int(math.floor(block.roomX / gridSize))
        block.cellY = int(math.floor(block.roomY / gridSize))

    if orderBy == "depth":
        # Higher depth is drawn first, so it goes on the earlier page
        return sorted(blocks, key = lambda block: (
            0 if block.hasPosition else 1,
            -block.drawDepth,
            block.cellY, block.cellX, block.roomY, block.roomX, block.spriteName
        ))

    return sorted(blocks, key = lambda block: (
        0 if block.hasPosition else 1,
        block.cellY, block.cellX, block.roomY, block.roomX, block.spriteName
    ))
#endregion


#region Block layout
def computeBlockLayout(block, options):
    # Lays the frames of one sprite out as a contiguous grid, in frame order.
    # A single row is used whenever it fits, which keeps animations adjacent
    # horizontally. Returns True when the resulting block fits on a page.
    frames = block.sprite.frames
    frameCount = len(frames)
    padding = options.padding

    block.cellWidth = max(1, max(scaledSize(frame.width, block.scale) for frame in frames))
    block.cellHeight = max(1, max(scaledSize(frame.height, block.scale) for frame in frames))

    singleRowWidth = frameCount * block.cellWidth + (frameCount - 1) * padding
    if singleRowWidth <= options.pageWidth:
        block.columns = frameCount
    else:
        block.columns = max(1, (options.pageWidth + padding) // (block.cellWidth + padding))

    block.rows = int(math.ceil(frameCount / block.columns))
    block.width = block.columns * block.cellWidth + (block.columns - 1) * padding
    block.height = block.rows * block.cellHeight + (block.rows - 1) * padding

    return block.width <= options.pageWidth and block.height <= options.pageHeight


def scaledSize(size, scale):
    if scale >= 1.0:
        return int(size)
    return max(1, int(round(size * scale)))


def fitBlockToPage(block, options):
    # Tries the block at full size, then shrinks it when the oversize policy
    # allows scaling. Returns True when the block ends up page sized.
    block.scale = 1.0
    if computeBlockLayout(block, options):
        return True

    if options.oversizePolicy != "scale":
        return False

    scale = 1.0
    for _ in range(60):
        scale *= 0.9
        block.scale = scale
        if computeBlockLayout(block, options):
            return True
        if block.cellWidth <= 1 and block.cellHeight <= 1:
            break

    block.scale = 1.0
    computeBlockLayout(block, options)
    return False


def buildFramePlacements(block, blockPlacement, options):
    # Turns the grid layout into one atlas rectangle per frame. When the block
    # was rotated the whole block is treated as turned 90 degrees clockwise.
    padding = options.padding
    placements = []

    for frame in block.sprite.frames:
        column = frame.frameIndex % block.columns
        row = frame.frameIndex // block.columns

        localX = column * (block.cellWidth + padding)
        localY = row * (block.cellHeight + padding)
        frameWidth = scaledSize(frame.width, block.scale)
        frameHeight = scaledSize(frame.height, block.scale)

        if blockPlacement.rotated:
            atlasX = blockPlacement.x + (block.height - (localY + frameHeight))
            atlasY = blockPlacement.y + localX
            placedWidth, placedHeight = frameHeight, frameWidth
        else:
            atlasX = blockPlacement.x + localX
            atlasY = blockPlacement.y + localY
            placedWidth, placedHeight = frameWidth, frameHeight

        placements.append(FramePlacement(
            spriteName = block.spriteName,
            frameIndex = frame.frameIndex,
            imagePath = frame.imagePath,
            page = blockPlacement.page,
            x = int(atlasX),
            y = int(atlasY),
            width = int(placedWidth),
            height = int(placedHeight),
            rotated = blockPlacement.rotated,
            scale = block.scale
        ))

    return placements
#endregion


class SkylinePacker:
    # Bottom left skyline packer. Blocks are inserted in the order they are
    # given so the spatial grouping decides what ends up next to what.

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.nodes = [[0, 0, width]]

    def fit(self, index, width, height):
        # Returns the y the block would sit at if placed at nodes[index].x
        x = self.nodes[index][0]
        if x + width > self.width:
            return None

        y = self.nodes[index][1]
        widthLeft = width
        i = index

        while widthLeft > 0:
            if i >= len(self.nodes):
                return None
            node = self.nodes[i]
            if node[1] > y:
                y = node[1]
            if y + height > self.height:
                return None
            widthLeft -= node[2]
            i += 1

        return y

    def findPosition(self, width, height):
        bestX = None
        bestY = None
        bestIndex = -1

        for index in range(len(self.nodes)):
            y = self.fit(index, width, height)
            if y is None:
                continue
            x = self.nodes[index][0]
            if bestY is None or y < bestY or (y == bestY and x < bestX):
                bestX, bestY, bestIndex = x, y, index

        if bestIndex < 0:
            return None
        return (bestX, bestY, bestIndex)

    def addLevel(self, index, x, y, width, height):
        self.nodes.insert(index, [x, y + height, width])

        i = index + 1
        while i < len(self.nodes):
            node = self.nodes[i]
            previous = self.nodes[i - 1]
            if node[0] >= previous[0] + previous[2]:
                break
            shrink = previous[0] + previous[2] - node[0]
            node[0] += shrink
            node[2] -= shrink
            if node[2] <= 0:
                del self.nodes[i]
                continue
            break

        # Merge neighbouring runs that sit at the same height
        i = 0
        while i < len(self.nodes) - 1:
            if self.nodes[i][1] == self.nodes[i + 1][1]:
                self.nodes[i][2] += self.nodes[i + 1][2]
                del self.nodes[i + 1]
                continue
            i += 1

    def insert(self, width, height, allowRotation = False):
        # Returns (x, y, rotated) or None when the block does not fit
        best = self.findPosition(width, height)
        bestRotated = False
        bestWidth, bestHeight = width, height

        if allowRotation and width != height:
            rotatedBest = self.findPosition(height, width)
            if rotatedBest is not None:
                if best is None or rotatedBest[1] < best[1] or (rotatedBest[1] == best[1] and rotatedBest[0] < best[0]):
                    best = rotatedBest
                    bestRotated = True
                    bestWidth, bestHeight = height, width

        if best is None:
            return None

        x, y, index = best
        self.addLevel(index, x, y, bestWidth, bestHeight)
        return (x, y, bestRotated)


def packGroupsIntoPages(groupedBlocks, options):
    # Walks the grouped list in order and fills one page at a time. A block that
    # does not fit the current page starts a new page, which is what keeps
    # neighbouring room assets on the same texture page.
    result = PackResult()
    padding = options.padding
    currentPage = None
    packer = None
    currentBreakKey = None

    def startNewPage():
        page = PackedPage(index = len(result.pages))
        result.pages.append(page)
        return page, SkylinePacker(options.pageWidth + padding, options.pageHeight + padding)

    for block in groupedBlocks:
        if options.breakPagesOnKeyChange and currentPage is not None and block.pageBreakKey != currentBreakKey:
            currentPage, packer = startNewPage()
        currentBreakKey = block.pageBreakKey

        if not fitBlockToPage(block, options):
            result.skippedBlocks.append(block)
            result.warnings.append(
                "Sprite " + block.spriteName + " does not fit a " +
                str(options.pageWidth) + "x" + str(options.pageHeight) + " page and was skipped"
            )
            continue

        if block.scale < 1.0:
            result.warnings.append(
                "Sprite " + block.spriteName + " was scaled to " +
                str(round(block.scale * 100)) + " percent to fit a page"
            )

        if currentPage is None:
            currentPage, packer = startNewPage()

        placement = packer.insert(block.width + padding, block.height + padding, options.allowRotation)

        if placement is None:
            currentPage, packer = startNewPage()
            placement = packer.insert(block.width + padding, block.height + padding, options.allowRotation)

        if placement is None:
            result.skippedBlocks.append(block)
            result.warnings.append("Sprite " + block.spriteName + " could not be placed on an empty page")
            continue

        x, y, rotated = placement
        blockPlacement = BlockPlacement(
            block = block,
            page = currentPage.index,
            x = x,
            y = y,
            rotated = rotated
        )
        blockPlacement.frames = buildFramePlacements(block, blockPlacement, options)
        currentPage.blocks.append(blockPlacement)

    return result


#region Validation
def validatePlacements(packResult, options):
    # Confirms the packer produced something a texture page can actually hold
    problems = []

    for page in packResult.pages:
        placements = sorted(page.framePlacements(), key = lambda placement: (placement.x, placement.y))

        for placement in placements:
            if placement.x < 0 or placement.y < 0:
                problems.append("Negative coordinate for " + placement.spriteName + " frame " + str(placement.frameIndex))
            if placement.x + placement.width > options.pageWidth:
                problems.append("Frame past the right page edge: " + placement.spriteName + " frame " + str(placement.frameIndex))
            if placement.y + placement.height > options.pageHeight:
                problems.append("Frame past the bottom page edge: " + placement.spriteName + " frame " + str(placement.frameIndex))

        # Sorted by x, so the sweep can stop as soon as a rectangle starts
        # past the right edge of the one being checked
        for firstIndex in range(len(placements)):
            first = placements[firstIndex]
            for secondIndex in range(firstIndex + 1, len(placements)):
                second = placements[secondIndex]
                if second.x >= first.x + first.width:
                    break
                if rectanglesOverlap(first, second):
                    problems.append(
                        "Overlap on page " + str(page.index) + " between " +
                        first.spriteName + " frame " + str(first.frameIndex) + " and " +
                        second.spriteName + " frame " + str(second.frameIndex)
                    )

    problems.extend(validateAnimationContiguity(packResult))
    return problems


def rectanglesOverlap(first, second):
    if first.x + first.width <= second.x or second.x + second.width <= first.x:
        return False
    if first.y + first.height <= second.y or second.y + second.height <= first.y:
        return False
    return True


def validateAnimationContiguity(packResult):
    # Every frame of a sprite has to live on one page, inside one block, and
    # read back in frame order top left to bottom right.
    problems = []

    for page in packResult.pages:
        for blockPlacement in page.blocks:
            frames = blockPlacement.frames
            pages = {frame.page for frame in frames}
            if len(pages) > 1:
                problems.append("Sprite " + blockPlacement.block.spriteName + " is split across pages")

            ordered = sorted(frames, key = lambda frame: frame.frameIndex)
            reading = sorted(frames, key = lambda frame: (-frame.x, frame.y) if frame.rotated else (frame.y, frame.x))
            if [frame.frameIndex for frame in ordered] != [frame.frameIndex for frame in reading]:
                problems.append("Sprite " + blockPlacement.block.spriteName + " frames are out of order in the atlas")

    return problems
#endregion
