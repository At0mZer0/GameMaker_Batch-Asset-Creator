import fnmatch
import json
import os
import re
from dataclasses import dataclass, field

import room_parser

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
MACRO_PATTERN = re.compile(r"#macro\s+([A-Za-z_][A-Za-z0-9_]*)")
FUNCTION_PATTERN = re.compile(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
ASSIGNMENT_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")

# Where a sprite came from, reported per sprite in the metadata and the report
SOURCE_INSTANCE = "instance"
SOURCE_INSTANCE_PROPERTY = "instance_property"
SOURCE_SPRITE_LAYER = "sprite_layer"
SOURCE_BACKGROUND = "background_layer"
SOURCE_TILESET = "tileset"
SOURCE_CODE = "code"
SOURCE_BUILDING_JSON = "building_json"

QUOTE = '"'
BACKSLASH = chr(92)


#region GML text handling
def stripGMLComments(text):
    # Blanks out // and /* */ comments so a commented out sprite name is not
    # treated as a live reference. String literals are left alone.
    out = list(text)
    index = 0
    length = len(text)

    while index < length:
        character = text[index]

        if character == QUOTE:
            index += 1
            while index < length:
                if text[index] == BACKSLASH:
                    index += 2
                    continue
                if text[index] == QUOTE:
                    index += 1
                    break
                index += 1
            continue

        if character == '/' and index + 1 < length:
            following = text[index + 1]

            if following == '/':
                while index < length and text[index] != '\n':
                    out[index] = ' '
                    index += 1
                continue

            if following == '*':
                out[index] = ' '
                out[index + 1] = ' '
                index += 2
                while index < length:
                    if text[index] == '*' and index + 1 < length and text[index + 1] == '/':
                        out[index] = ' '
                        out[index + 1] = ' '
                        index += 2
                        break
                    if text[index] != '\n':
                        out[index] = ' '
                    index += 1
                continue

        index += 1

    return ''.join(out)


def identifiersInCode(text):
    return IDENTIFIER_PATTERN.findall(text)


def assignedIdentifiers(text):
    # Only the right hand side of an assignment whose left hand side looks like
    # a sprite variable. Used when the random choice list option is switched off.
    names = []

    for leftSide, rightSide in ASSIGNMENT_PATTERN.findall(text):
        lowered = leftSide.lower()
        if "sprite" in lowered or lowered.startswith("spr") or lowered.endswith("spr"):
            names.append(rightSide)

    return names
#endregion


def collectObjectTypesFromJson(node, found):
    # Build_XX.json nests rooms inside buildings and contents inside rooms, and
    # every element names the object to create in an objectType member
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "objectType" and isinstance(value, str) and value:
                if value not in found:
                    found.append(value)
            collectObjectTypesFromJson(value, found)
    elif isinstance(node, list):
        for value in node:
            collectObjectTypesFromJson(value, found)

    return found


class ProjectSymbolIndex:
    # Knows which names in this project are sprites, objects, scripts, macros or
    # functions, so a token found in code can be classified without guessing.

    def __init__(self, projectRoot):
        self.projectRoot = projectRoot
        self.spriteNames = self.listResourceNames("sprites")
        self.objectNames = self.listResourceNames("objects")
        self.scriptNames = self.listResourceNames("scripts")
        self.symbolToScript = None

    def listResourceNames(self, folderName):
        folderPath = os.path.join(self.projectRoot, folderName)
        if not os.path.isdir(folderPath):
            return set()
        return {name for name in os.listdir(folderPath)
                if os.path.isfile(os.path.join(folderPath, name, name + ".yy"))}

    def scriptFilePath(self, scriptName):
        return os.path.join(self.projectRoot, "scripts", scriptName, scriptName + ".gml")

    def buildScriptSymbols(self):
        # Maps every #macro and function name to the script that declares it, so
        # a reference such as VARIANTS can be followed into item_s
        if self.symbolToScript is not None:
            return self.symbolToScript

        self.symbolToScript = {}

        for scriptName in sorted(self.scriptNames):
            scriptPath = self.scriptFilePath(scriptName)
            if not os.path.isfile(scriptPath):
                continue

            self.symbolToScript.setdefault(scriptName, scriptPath)

            try:
                with open(scriptPath, 'r', encoding = 'utf-8-sig', errors = 'replace') as file:
                    text = file.read()
            except OSError:
                continue

            for macroName in MACRO_PATTERN.findall(text):
                self.symbolToScript.setdefault(macroName, scriptPath)
            for functionName in FUNCTION_PATTERN.findall(text):
                self.symbolToScript.setdefault(functionName, scriptPath)

        return self.symbolToScript

    def objectEventFiles(self, objectName):
        objectDir = os.path.join(self.projectRoot, "objects", objectName)
        if not os.path.isdir(objectDir):
            return []
        return [os.path.join(objectDir, fileName)
                for fileName in sorted(os.listdir(objectDir)) if fileName.endswith(".gml")]


@dataclass
class DiscoveredSprite:
    name: str
    positions: list = field(default_factory = list)
    sources: list = field(default_factory = list)
    objectNames: list = field(default_factory = list)
    layerNames: list = field(default_factory = list)
    discoveredFrom: list = field(default_factory = list)
    depths: list = field(default_factory = list)

    def addUnique(self, targetList, value):
        if value and value not in targetList:
            targetList.append(value)

    def addSource(self, source):
        self.addUnique(self.sources, source)

    @property
    def hasPosition(self):
        return len(self.positions) > 0

    @property
    def drawDepth(self):
        # A sprite seen on several layers is grouped with the furthest back one,
        # which is where GameMaker draws it first
        return max(self.depths) if self.depths else 0

    @property
    def centroid(self):
        if not self.positions:
            return (0.0, 0.0)
        return (
            sum(position[0] for position in self.positions) / len(self.positions),
            sum(position[1] for position in self.positions) / len(self.positions)
        )


class RoomSpriteDiscovery:
    # Collects every sprite a room can draw: the first pass over placed
    # instances and layers, then the second pass through object code.

    def __init__(self, projectRoot, assetIndex, symbolIndex, options, log = None):
        self.projectRoot = projectRoot
        self.assetIndex = assetIndex
        self.symbolIndex = symbolIndex
        self.options = options
        self.logCallback = log

        self.discovered = {}
        self.warnings = []
        self.objectsWithoutSprite = []
        self.placedObjectNames = set()
        self.scannedObjects = set()
        self.excludedObjects = []
        self.excludedLayers = []
        self.buildingFiles = []
        self.scannedScripts = set()
        self.unresolvedTokens = []

    def log(self, message):
        if self.logCallback:
            self.logCallback(message)

    def addWarning(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def record(self, spriteName, source, position = None, objectName = "", layerName = "", origin = "", depth = None):
        if spriteName not in self.symbolIndex.spriteNames:
            return None

        entry = self.discovered.get(spriteName)
        if entry is None:
            entry = DiscoveredSprite(name = spriteName)
            self.discovered[spriteName] = entry

        entry.addSource(source)
        if position is not None:
            entry.positions.append(position)
        if depth is not None:
            entry.depths.append(depth)
        entry.addUnique(entry.objectNames, objectName)
        entry.addUnique(entry.layerNames, layerName)
        entry.addUnique(entry.discoveredFrom, origin)
        return entry

    #region First pass
    def isExcludedLayer(self, layerName):
        for pattern in self.options.excludeLayers or []:
            if fnmatch.fnmatch(layerName, pattern):
                if layerName not in self.excludedLayers:
                    self.excludedLayers.append(layerName)
                return True
        return False

    def runFirstPass(self, room):
        placedObjects = []

        for instance in room.instances:
            if self.isExcludedLayer(instance.layerName):
                continue
            spriteName = self.assetIndex.resolveSpriteForObject(instance.objectName)
            if spriteName:
                self.record(spriteName, SOURCE_INSTANCE, (instance.x, instance.y),
                            instance.objectName, instance.layerName, depth = instance.layerDepth)
            elif instance.objectName not in self.objectsWithoutSprite:
                self.objectsWithoutSprite.append(instance.objectName)

            for propertyName in instance.propertyNames:
                self.record(propertyName, SOURCE_INSTANCE_PROPERTY, (instance.x, instance.y),
                            instance.objectName, instance.layerName,
                            instance.objectName + " instance property", instance.layerDepth)

            if instance.objectName not in placedObjects:
                placedObjects.append(instance.objectName)
                self.placedObjectNames.add(instance.objectName)

            if self.isBuildingJsonObject(instance.objectName):
                self.resolveBuildingInstance(instance, placedObjects)

        for graphic in room.spriteGraphics:
            if self.isExcludedLayer(graphic.layerName):
                continue
            self.record(graphic.spriteName, SOURCE_SPRITE_LAYER, (graphic.x, graphic.y),
                        "", graphic.layerName, depth = graphic.layerDepth)

        for background in room.backgrounds:
            if self.isExcludedLayer(background.layerName):
                continue
            self.record(background.spriteName, SOURCE_BACKGROUND, None, "", background.layerName,
                        depth = background.layerDepth)

        if not self.options.ignoreTilesets:
            for tileLayer in room.tileLayers:
                spriteName = room_parser.resolveTilesetSprite(self.projectRoot, tileLayer.tilesetName)
                if spriteName:
                    self.record(spriteName, SOURCE_TILESET, None, "", tileLayer.layerName,
                                "tileset " + tileLayer.tilesetName)
                else:
                    self.addWarning("Tileset " + tileLayer.tilesetName + " has no sprite behind it")

        return placedObjects
    #endregion

    #region Second pass
    def isExcludedFromCodeScan(self, objectName):
        # Wildcards allowed, so "*Ctrl" covers a whole family of controllers
        for pattern in self.options.excludeCodeScanObjects or []:
            if fnmatch.fnmatch(objectName, pattern):
                return True
        return False

    def scanText(self, text, originLabel, objectName, ownerPosition, ownerDepth = None):
        # Returns the object names and script paths worth following next
        cleaned = stripGMLComments(text)

        if self.options.includeRandomChoiceLists:
            tokens = identifiersInCode(cleaned)
        else:
            tokens = assignedIdentifiers(cleaned)

        nextObjects = []
        nextScripts = []
        symbolToScript = self.symbolIndex.buildScriptSymbols() if self.options.followScriptReferences else {}

        for token in tokens:
            if token in self.symbolIndex.spriteNames:
                self.record(token, SOURCE_CODE, ownerPosition, objectName, "", originLabel, ownerDepth)
                continue

            if self.options.followSpawnedObjects and token in self.symbolIndex.objectNames:
                if token not in self.scannedObjects and token not in nextObjects:
                    nextObjects.append(token)
                continue

            scriptPath = symbolToScript.get(token)
            if scriptPath and scriptPath not in self.scannedScripts and scriptPath not in nextScripts:
                nextScripts.append(scriptPath)

        return nextObjects, nextScripts

    def readTextFile(self, filePath):
        try:
            with open(filePath, 'r', encoding = 'utf-8-sig', errors = 'replace') as file:
                return file.read()
        except OSError as error:
            self.addWarning("Could not read " + os.path.basename(filePath) + ": " + str(error))
            return ""

    def objectPropertyText(self, objectName):
        # Variable definitions can hold a sprite name as their default value
        objectData = self.assetIndex.loadObjectData(objectName)
        if not objectData:
            return ""

        values = []
        for propertyEntry in objectData.get('properties', []) or []:
            resource = propertyEntry.get('resource') or {}
            if resource.get('name'):
                values.append(str(propertyEntry.get('name', '')) + " = " + resource['name'])
            value = propertyEntry.get('value')
            if isinstance(value, str):
                values.append(str(propertyEntry.get('name', '')) + " = " + value)

        return "\n".join(values)

    def objectChain(self, objectName):
        # An object and every parent it inherits from
        chain = []
        currentName = objectName

        while currentName and currentName not in chain:
            chain.append(currentName)
            objectData = self.assetIndex.loadObjectData(currentName)
            if not objectData:
                break
            parentObjectId = objectData.get('parentObjectId')
            currentName = parentObjectId.get('name') if parentObjectId else None

        return chain

    def scanObject(self, objectName, ownerPosition, depth, ownerDepth = None):
        if objectName in self.scannedObjects:
            return []
        self.scannedObjects.add(objectName)

        if self.isExcludedFromCodeScan(objectName):
            # An excluded object contributes nothing that only code knows about,
            # neither its code nor its own sprite. If it is actually placed in
            # the room the first pass already recorded its sprite, which is a
            # fact about the room rather than something reached through code.
            if objectName not in self.excludedObjects:
                self.excludedObjects.append(objectName)
            return []

        # An object reached through code was never placed in the room, so the
        # sprite assigned to it in the object editor has not been seen yet
        if objectName not in self.placedObjectNames:
            ownSprite = self.assetIndex.resolveSpriteForObject(objectName)
            if ownSprite:
                self.record(ownSprite, SOURCE_CODE, ownerPosition, objectName, "",
                            objectName + " (object sprite, reached from code)", ownerDepth)

        pendingObjects = []
        pendingScripts = []

        for chainName in self.objectChain(objectName):
            originLabel = objectName + " (" + chainName + " variable definitions)"
            nextObjects, nextScripts = self.scanText(
                self.objectPropertyText(chainName), originLabel, objectName, ownerPosition, ownerDepth
            )
            pendingObjects.extend(nextObjects)
            pendingScripts.extend(nextScripts)

            for eventFile in self.symbolIndex.objectEventFiles(chainName):
                if len(self.scannedScripts) + len(self.scannedObjects) > self.options.maxScannedFiles:
                    self.addWarning("Stopped the code scan at the " + str(self.options.maxScannedFiles) + " file cap")
                    return pendingObjects

                originLabel = objectName + " (" + chainName + " " + os.path.basename(eventFile) + ")"
                nextObjects, nextScripts = self.scanText(
                    self.readTextFile(eventFile), originLabel, objectName, ownerPosition, ownerDepth
                )
                pendingObjects.extend(nextObjects)
                pendingScripts.extend(nextScripts)

        for scriptPath in pendingScripts:
            self.scanScript(scriptPath, objectName, ownerPosition, depth, ownerDepth)

        return pendingObjects

    def scanScript(self, scriptPath, objectName, ownerPosition, depth, ownerDepth = None):
        if scriptPath in self.scannedScripts:
            return
        self.scannedScripts.add(scriptPath)

        originLabel = objectName + " (script " + os.path.basename(scriptPath) + ")"
        nextObjects, nextScripts = self.scanText(
            self.readTextFile(scriptPath), originLabel, objectName, ownerPosition, ownerDepth
        )

        if depth < self.options.maxScriptDepth:
            for nextScriptPath in nextScripts:
                self.scanScript(nextScriptPath, objectName, ownerPosition, depth + 1, ownerDepth)
        elif nextScripts:
            self.unresolvedTokens.append(originLabel + " references more scripts past the depth limit")

    def isBuildingJsonObject(self, objectName):
        # obj_build_01 and friends are children of oBuildingJSON, so the whole
        # inheritance chain has to be checked, not just the placed object name
        targets = self.options.buildingJsonObjects or []
        if not targets:
            return False

        for chainName in self.objectChain(objectName):
            if chainName in targets:
                return True
        return False

    def objectPropertyValue(self, objectName, propertyName):
        # A child object sets a parent variable definition through
        # overriddenProperties, the declaring object holds the default in
        # properties. Nearest in the chain wins.
        for chainName in self.objectChain(objectName):
            objectData = self.assetIndex.loadObjectData(chainName)
            if not objectData:
                continue

            for entry in objectData.get('overriddenProperties', []) or []:
                propertyId = entry.get('propertyId') or {}
                if propertyId.get('name') == propertyName:
                    return entry.get('value')

            for entry in objectData.get('properties', []) or []:
                if entry.get('name') == propertyName:
                    return entry.get('value')

        return None

    def resolveBuildingInstance(self, instance, placedObjects):
        # An oBuildingJSON instance names an Included File in its buildingName
        # variable definition. That file lists the objects the building creates,
        # and those objects carry the sprites the room actually draws.
        # An override on the placed instance beats the object level default
        buildingName = instance.propertyValues.get(self.options.buildingNameProperty)
        if not isinstance(buildingName, str) or not buildingName.strip():
            buildingName = self.objectPropertyValue(instance.objectName, self.options.buildingNameProperty)

        if not isinstance(buildingName, str) or not buildingName.strip():
            self.addWarning(instance.objectName + " instance " + instance.instanceName +
                            " has no " + self.options.buildingNameProperty + " set, its building was skipped")
            return

        buildingName = buildingName.strip()
        filePath = room_parser.includedFilePath(self.projectRoot, buildingName + ".json")

        if not os.path.isfile(filePath):
            self.addWarning("Included File " + buildingName + ".json was not found for " + instance.objectName)
            return

        try:
            with open(filePath, 'r', encoding = 'utf-8-sig') as file:
                buildingData = json.load(file)
        except Exception as error:
            self.addWarning("Could not read " + buildingName + ".json: " + str(error))
            return

        objectTypes = collectObjectTypesFromJson(buildingData, [])
        if buildingName not in self.buildingFiles:
            self.buildingFiles.append(buildingName)
        self.log("Building " + buildingName + ".json names " + str(len(objectTypes)) + " object types")

        for objectName in objectTypes:
            spriteName = self.assetIndex.resolveSpriteForObject(objectName)
            if spriteName:
                self.record(spriteName, SOURCE_BUILDING_JSON, (instance.x, instance.y),
                            objectName, instance.layerName,
                            buildingName + ".json (" + instance.objectName + ")", instance.layerDepth)

            # The building objects are really in the room, so their code counts
            if objectName not in placedObjects:
                placedObjects.append(objectName)
                self.placedObjectNames.add(objectName)

    def runSecondPass(self, placedObjects, room):
        # Position each code discovered sprite at the object that referenced it
        positionForObject = {}
        depthForObject = {}
        for instance in room.instances:
            positionForObject.setdefault(instance.objectName, (instance.x, instance.y))
            depthForObject.setdefault(instance.objectName, instance.layerDepth)

        frontier = [(objectName, 0) for objectName in placedObjects]

        while frontier:
            objectName, depth = frontier.pop(0)
            ownerPosition = positionForObject.get(objectName)
            ownerDepth = depthForObject.get(objectName)
            spawnedObjects = self.scanObject(objectName, ownerPosition, 0, ownerDepth)

            if depth < self.options.maxObjectDepth:
                for spawnedName in spawnedObjects:
                    if spawnedName not in self.scannedObjects:
                        positionForObject.setdefault(spawnedName, ownerPosition)
                        depthForObject.setdefault(spawnedName, ownerDepth)
                        frontier.append((spawnedName, depth + 1))
    #endregion

    def discover(self, room):
        self.log("First pass: placed instances, sprite layers and backgrounds")
        placedObjects = self.runFirstPass(room)
        firstPassCount = len(self.discovered)
        self.log("First pass found " + str(firstPassCount) + " sprites")
        if self.buildingFiles:
            self.log("Resolved " + str(len(self.buildingFiles)) + " building files: " +
                     ", ".join(sorted(self.buildingFiles)))

        if self.options.scanObjectCode:
            self.log("Second pass: scanning object code for " + str(len(placedObjects)) + " object types")
            self.runSecondPass(placedObjects, room)
            self.log("Second pass added " + str(len(self.discovered) - firstPassCount) + " sprites from " +
                     str(len(self.scannedObjects)) + " objects and " + str(len(self.scannedScripts)) + " scripts")
            if self.excludedObjects:
                self.log("Code scan skipped " + str(len(self.excludedObjects)) + " excluded objects: " +
                         ", ".join(sorted(self.excludedObjects)))
        if self.excludedLayers:
            self.log("Skipped " + str(len(self.excludedLayers)) + " excluded layers: " +
                     ", ".join(sorted(self.excludedLayers)))

        return self.discovered

    def countsBySource(self):
        counts = {}
        for entry in self.discovered.values():
            for source in entry.sources:
                counts[source] = counts.get(source, 0) + 1
        return counts
