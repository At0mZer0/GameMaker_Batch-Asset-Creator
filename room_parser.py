import os
import re
from dataclasses import dataclass, field

from PIL import Image

from yy_io import loadYY

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


#region Data classes
@dataclass
class RoomInstance:
    instanceName: str
    objectName: str
    x: float
    y: float
    scaleX: float = 1.0
    scaleY: float = 1.0
    rotation: float = 0.0
    layerName: str = ""
    layerDepth: int = 0
    imageIndex: int = 0
    # Names pulled out of the instance overridden properties, still unvalidated
    propertyNames: list = field(default_factory = list)
    # The same overridden properties keyed by property name
    propertyValues: dict = field(default_factory = dict)


@dataclass
class RoomSpriteGraphic:
    # One sprite placed straight onto an asset layer, no object involved
    spriteName: str
    x: float
    y: float
    layerName: str
    layerDepth: int = 0


@dataclass
class RoomBackground:
    spriteName: str
    layerName: str
    layerDepth: int = 0


@dataclass
class RoomTileLayer:
    tilesetName: str
    layerName: str


@dataclass
class RoomData:
    name: str
    path: str
    width: int
    height: int
    instances: list = field(default_factory = list)
    spriteGraphics: list = field(default_factory = list)
    backgrounds: list = field(default_factory = list)
    tileLayers: list = field(default_factory = list)


@dataclass
class SpriteFrame:
    spriteName: str
    frameIndex: int
    imagePath: str
    width: int
    height: int


@dataclass
class SpriteAsset:
    name: str
    yyPath: str
    width: int
    height: int
    originX: int
    originY: int
    textureGroup: str
    # Carried through so the atlas json can fill in the optional members
    # texturegroup_add accepts: frame_speed, frame_type, bbox_* and bbox_kind
    playbackSpeed: float = 30.0
    playbackSpeedType: int = 0
    bboxLeft: int = 0
    bboxRight: int = 0
    bboxTop: int = 0
    bboxBottom: int = 0
    collisionKind: int = 1
    frames: list = field(default_factory = list)

    @property
    def frameCount(self):
        return len(self.frames)
#endregion


#region Project and room discovery
def findYYPFile(projectRoot):
    # Returns the path of the .yyp in a project root, or None
    if not os.path.isdir(projectRoot):
        return None
    for fileName in sorted(os.listdir(projectRoot)):
        if fileName.endswith('.yyp'):
            return os.path.join(projectRoot, fileName)
    return None


def isLegacyGMXProject(projectRoot):
    # GameMaker 1.4 projects use a .project.gmx file and are not supported here
    if not os.path.isdir(projectRoot):
        return False
    for fileName in os.listdir(projectRoot):
        if fileName.endswith('.project.gmx'):
            return True
    return False


def parseProjectRooms(projectRoot):
    # Returns a list of (roomName, roomYYPath) sorted by room name.
    # Scans the rooms directory rather than the .yyp so a project with thousands
    # of resources does not have to be parsed just to fill the dropdown.
    roomsDir = os.path.join(projectRoot, "rooms")
    rooms = []

    if os.path.isdir(roomsDir):
        for roomName in sorted(os.listdir(roomsDir)):
            roomYYPath = os.path.join(roomsDir, roomName, roomName + ".yy")
            if os.path.isfile(roomYYPath):
                rooms.append((roomName, roomYYPath))

    if rooms:
        return rooms

    # Fallback: read the room resources straight out of the .yyp
    yypFilePath = findYYPFile(projectRoot)
    if not yypFilePath:
        return rooms

    projectData = loadYY(yypFilePath)
    for resource in projectData.get('resources', []):
        resourceId = resource.get('id', {})
        resourcePath = resourceId.get('path', '')
        if resourcePath.startswith('rooms/'):
            fullPath = os.path.join(projectRoot, resourcePath.replace('/', os.sep))
            if os.path.isfile(fullPath):
                rooms.append((resourceId.get('name', ''), fullPath))

    rooms.sort(key = lambda entry: entry[0])
    return rooms
#endregion


#region Room parsing
def instancePropertyNames(instance):
    # Overridden properties on a placed instance can name a sprite directly,
    # either as a resource reference or as a plain string value. Returns the
    # candidate names and the same properties keyed by property name.
    names = []
    values = {}

    for propertyEntry in instance.get('properties', []) or []:
        propertyName = propertyEntry.get('name') or propertyEntry.get('%Name')
        resource = propertyEntry.get('resource') or {}
        resourceName = resource.get('name')
        value = propertyEntry.get('value')

        if propertyName:
            values[propertyName] = resourceName or value

        if resourceName:
            names.append(resourceName)
            continue

        if isinstance(value, str) and value and IDENTIFIER_PATTERN.fullmatch(value):
            names.append(value)

    return names, values


def collectFromLayers(layers, room, includeIgnored = False, inheritedDepth = 0):
    # Layers nest, a GMRLayer folder can hold more layers, so walk recursively
    for layer in layers or []:
        layerName = layer.get('name', '')
        # GameMaker draws higher depth first, so depth is the draw order key
        layerDepth = int(layer.get('depth', inheritedDepth))

        for instance in layer.get('instances', []) or []:
            if instance.get('ignore', False) and not includeIgnored:
                continue

            objectId = instance.get('objectId') or {}
            objectName = objectId.get('name')
            if not objectName:
                continue

            propertyNames, propertyValues = instancePropertyNames(instance)

            room.instances.append(RoomInstance(
                instanceName = instance.get('name', ''),
                objectName = objectName,
                x = float(instance.get('x', 0.0)),
                y = float(instance.get('y', 0.0)),
                scaleX = float(instance.get('scaleX', 1.0)),
                scaleY = float(instance.get('scaleY', 1.0)),
                rotation = float(instance.get('rotation', 0.0)),
                layerName = layerName,
                layerDepth = layerDepth,
                imageIndex = int(instance.get('imageIndex', 0)),
                propertyNames = propertyNames,
                propertyValues = propertyValues
            ))

        # Asset layers hold sprites placed without an object behind them
        for asset in layer.get('assets', []) or []:
            if asset.get('resourceType') != 'GMRSpriteGraphic':
                continue
            if asset.get('ignore', False) and not includeIgnored:
                continue

            spriteId = asset.get('spriteId') or {}
            spriteName = spriteId.get('name')
            if not spriteName:
                continue

            room.spriteGraphics.append(RoomSpriteGraphic(
                spriteName = spriteName,
                x = float(asset.get('x', 0.0)),
                y = float(asset.get('y', 0.0)),
                layerName = layerName,
                layerDepth = layerDepth
            ))

        if layer.get('resourceType') == 'GMRBackgroundLayer':
            spriteId = layer.get('spriteId') or {}
            if spriteId.get('name'):
                room.backgrounds.append(RoomBackground(
                    spriteName = spriteId['name'],
                    layerName = layerName,
                    layerDepth = layerDepth
                ))

        if layer.get('resourceType') == 'GMRTileLayer':
            tilesetId = layer.get('tilesetId') or {}
            if tilesetId.get('name'):
                room.tileLayers.append(RoomTileLayer(
                    tilesetName = tilesetId['name'],
                    layerName = layerName
                ))

        collectFromLayers(layer.get('layers', []), room, includeIgnored, layerDepth)

    return room


def parseRoom(roomPath, includeIgnored = False):
    # Reads a room .yy and returns the placed object instances, the sprites
    # placed straight onto asset layers, background layer sprites and the
    # tilesets each tile layer uses.
    roomData = loadYY(roomPath)
    roomSettings = roomData.get('roomSettings', {}) or {}

    room = RoomData(
        name = roomData.get('name', os.path.splitext(os.path.basename(roomPath))[0]),
        path = roomPath,
        width = int(roomSettings.get('Width', 0)),
        height = int(roomSettings.get('Height', 0))
    )

    return collectFromLayers(roomData.get('layers', []), room, includeIgnored)


def includedFilePath(projectRoot, fileName):
    # GameMaker keeps Included Files in the datafiles folder of the project
    return os.path.join(projectRoot, "datafiles", fileName)


def listTextureGroupNames(projectRoot):
    # Every texture group already defined in the project. texturegroup_add
    # raises a fatal error if the group name handed to it is one of these.
    yypFilePath = findYYPFile(projectRoot)
    if not yypFilePath:
        return []

    try:
        projectData = loadYY(yypFilePath)
    except Exception:
        return []

    return sorted(group.get('name', '') for group in projectData.get('TextureGroups', []) if group.get('name'))


def resolveTilesetSprite(projectRoot, tilesetName):
    # A tileset draws from a sprite, this returns that sprite name
    tilesetPath = os.path.join(projectRoot, "tilesets", tilesetName, tilesetName + ".yy")
    if not os.path.isfile(tilesetPath):
        return None

    try:
        tilesetData = loadYY(tilesetPath)
    except Exception:
        return None

    spriteId = tilesetData.get('spriteId') or {}
    return spriteId.get('name')
#endregion


class ProjectAssetIndex:
    # Caches object to sprite lookups and sprite frame collection for one project

    def __init__(self, projectRoot):
        self.projectRoot = projectRoot
        self.objectCache = {}
        self.spriteCache = {}
        self.warnings = []

    def addWarning(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def loadObjectData(self, objectName):
        if objectName in self.objectCache:
            return self.objectCache[objectName]

        objectPath = os.path.join(self.projectRoot, "objects", objectName, objectName + ".yy")
        objectData = None
        if os.path.isfile(objectPath):
            try:
                objectData = loadYY(objectPath)
            except Exception as error:
                self.addWarning("Could not read object " + objectName + ": " + str(error))
        else:
            self.addWarning("Object " + objectName + " has no .yy file in the project")

        self.objectCache[objectName] = objectData
        return objectData

    def resolveSpriteForObject(self, objectName):
        # Returns the sprite resource name for an object, walking up the
        # parentObjectId chain when the object itself has no sprite assigned.
        seen = set()
        currentName = objectName

        while currentName and currentName not in seen:
            seen.add(currentName)
            objectData = self.loadObjectData(currentName)
            if not objectData:
                return None

            spriteId = objectData.get('spriteId')
            if spriteId and spriteId.get('name'):
                return spriteId['name']

            parentObjectId = objectData.get('parentObjectId')
            currentName = parentObjectId.get('name') if parentObjectId else None

        return None

    def collectSpriteFrames(self, spriteName):
        # Returns a SpriteAsset with one SpriteFrame per frame, in playback order
        if spriteName in self.spriteCache:
            return self.spriteCache[spriteName]

        spriteDir = os.path.join(self.projectRoot, "sprites", spriteName)
        spriteYYPath = os.path.join(spriteDir, spriteName + ".yy")

        if not os.path.isfile(spriteYYPath):
            self.addWarning("Sprite " + spriteName + " has no .yy file in the project")
            self.spriteCache[spriteName] = None
            return None

        try:
            spriteData = loadYY(spriteYYPath)
        except Exception as error:
            self.addWarning("Could not read sprite " + spriteName + ": " + str(error))
            self.spriteCache[spriteName] = None
            return None

        declaredWidth = int(spriteData.get('width', 0))
        declaredHeight = int(spriteData.get('height', 0))
        sequence = spriteData.get('sequence') or {}
        textureGroupId = spriteData.get('textureGroupId') or {}

        asset = SpriteAsset(
            name = spriteName,
            yyPath = spriteYYPath,
            width = declaredWidth,
            height = declaredHeight,
            originX = int(sequence.get('xorigin', 0)),
            originY = int(sequence.get('yorigin', 0)),
            textureGroup = textureGroupId.get('name', 'Default'),
            playbackSpeed = float(sequence.get('playbackSpeed', 30.0)),
            playbackSpeedType = int(sequence.get('playbackSpeedType', 0)),
            bboxLeft = int(spriteData.get('bbox_left', 0)),
            bboxRight = int(spriteData.get('bbox_right', max(0, declaredWidth - 1))),
            bboxTop = int(spriteData.get('bbox_top', 0)),
            bboxBottom = int(spriteData.get('bbox_bottom', max(0, declaredHeight - 1))),
            collisionKind = int(spriteData.get('collisionKind', 1))
        )

        for frameIndex, frame in enumerate(spriteData.get('frames', []) or []):
            frameName = frame.get('name') or frame.get('%Name')
            if not frameName:
                self.addWarning("Sprite " + spriteName + " frame " + str(frameIndex) + " has no name")
                continue

            imagePath = os.path.join(spriteDir, frameName + ".png")
            if not os.path.isfile(imagePath):
                self.addWarning("Missing frame image for " + spriteName + " frame " + str(frameIndex))
                continue

            try:
                with Image.open(imagePath) as image:
                    frameWidth, frameHeight = image.size
            except Exception as error:
                self.addWarning("Could not read image for " + spriteName + ": " + str(error))
                frameWidth, frameHeight = declaredWidth, declaredHeight

            asset.frames.append(SpriteFrame(
                spriteName = spriteName,
                frameIndex = frameIndex,
                imagePath = imagePath,
                width = frameWidth,
                height = frameHeight
            ))

        if not asset.frames:
            self.addWarning("Sprite " + spriteName + " has no usable frames and was skipped")
            self.spriteCache[spriteName] = None
            return None

        self.spriteCache[spriteName] = asset
        return asset
