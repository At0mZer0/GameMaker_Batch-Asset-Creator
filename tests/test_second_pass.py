import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import atlas_packer
import atlas_writer
import room_parser
import sprite_discovery
from room_atlas_builder import RoomAtlasBuilder
from test_room_atlas import (instanceLayer, makeInstance, makeObject, makeProject, makeRoom,
                             makeSprite, readJson, writeJson)


#region Fixtures for layers, code and scripts
def spriteLayer(name, entries):
    # entries is a list of (spriteName, x, y)
    return {
        "$GMRAssetLayer": "",
        "%Name": name,
        "name": name,
        "assets": [
            {
                "$GMRSpriteGraphic": "v1",
                "%Name": "graphic_" + spriteName,
                "name": "graphic_" + spriteName,
                "spriteId": {"name": spriteName, "path": "sprites/" + spriteName + "/" + spriteName + ".yy"},
                "ignore": False,
                "x": float(x),
                "y": float(y),
                "resourceType": "GMRSpriteGraphic"
            }
            for spriteName, x, y in entries
        ],
        "layers": [],
        "resourceType": "GMRAssetLayer"
    }


def backgroundLayer(name, spriteName):
    return {
        "$GMRBackgroundLayer": "",
        "%Name": name,
        "name": name,
        "spriteId": {"name": spriteName, "path": "sprites/" + spriteName + "/" + spriteName + ".yy"},
        "layers": [],
        "resourceType": "GMRBackgroundLayer"
    }


def tileLayer(name, tilesetName):
    return {
        "$GMRTileLayer": "",
        "%Name": name,
        "name": name,
        "tilesetId": {"name": tilesetName, "path": "tilesets/" + tilesetName + "/" + tilesetName + ".yy"},
        "layers": [],
        "resourceType": "GMRTileLayer"
    }


def makeTileset(projectRoot, tilesetName, spriteName):
    writeJson(os.path.join(projectRoot, "tilesets", tilesetName, tilesetName + ".yy"), {
        "$GMTileSet": "",
        "name": tilesetName,
        "spriteId": {"name": spriteName, "path": "sprites/" + spriteName + "/" + spriteName + ".yy"},
        "resourceType": "GMTileSet"
    })


def makeObjectCode(projectRoot, objectName, eventFileName, lines):
    objectDir = os.path.join(projectRoot, "objects", objectName)
    os.makedirs(objectDir, exist_ok = True)
    with open(os.path.join(objectDir, eventFileName), 'w', encoding = 'utf-8') as file:
        file.write("\n".join(lines))


def makeScript(projectRoot, scriptName, lines):
    scriptDir = os.path.join(projectRoot, "scripts", scriptName)
    os.makedirs(scriptDir, exist_ok = True)
    writeJson(os.path.join(scriptDir, scriptName + ".yy"), {
        "$GMScript": "", "name": scriptName, "resourceType": "GMScript"
    })
    with open(os.path.join(scriptDir, scriptName + ".gml"), 'w', encoding = 'utf-8') as file:
        file.write("\n".join(lines))


def makeObjectWithProperty(projectRoot, objectName, propertyName, propertyValue, parentName = None):
    objectDir = os.path.join(projectRoot, "objects", objectName)
    os.makedirs(objectDir, exist_ok = True)
    writeJson(os.path.join(objectDir, objectName + ".yy"), {
        "$GMObject": "",
        "name": objectName,
        "spriteId": None,
        "parentObjectId": {"name": parentName, "path": "objects/" + parentName + "/" + parentName + ".yy"} if parentName else None,
        "properties": [{
            "$GMObjectProperty": "v2",
            "%Name": propertyName,
            "name": propertyName,
            "value": propertyValue,
            "varType": 2,
            "resourceType": "GMObjectProperty"
        }],
        "resourceType": "GMObject"
    })


def discoverFor(projectRoot, roomName, options):
    rooms = dict(room_parser.parseProjectRooms(projectRoot))
    room = room_parser.parseRoom(rooms[roomName], options.includeIgnoredInstances)
    assetIndex = room_parser.ProjectAssetIndex(projectRoot)
    symbolIndex = sprite_discovery.ProjectSymbolIndex(projectRoot)
    discovery = sprite_discovery.RoomSpriteDiscovery(projectRoot, assetIndex, symbolIndex, options)
    return room, discovery, discovery.discover(room)
#endregion


class TestGMLTextHandling(unittest.TestCase):

    def testCommentsAreStrippedButStringsSurvive(self):
        code = 'a = sprLive; // sprCommented\nb = "sprInString"; /* sprBlock */ c = sprAlsoLive;'
        cleaned = sprite_discovery.stripGMLComments(code)

        self.assertIn("sprLive", cleaned)
        self.assertIn("sprAlsoLive", cleaned)
        self.assertIn("sprInString", cleaned)
        self.assertNotIn("sprCommented", cleaned)
        self.assertNotIn("sprBlock", cleaned)

    def testCommentStrippingKeepsLineCount(self):
        code = "one // note\ntwo /* a\nb */ three"
        self.assertEqual(sprite_discovery.stripGMLComments(code).count("\n"), code.count("\n"))

    def testAssignedIdentifiersOnlyTakesSpriteLookingVariables(self):
        code = "sprite_index = sprHero; hp = oEnemy; mySprite = sprCrate; count = 3;"
        names = sprite_discovery.assignedIdentifiers(code)

        self.assertIn("sprHero", names)
        self.assertIn("sprCrate", names)
        self.assertNotIn("oEnemy", names)


class TestLayerDiscovery(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeProject(self.projectRoot)

        for name in ["sprCliffA", "sprCliffB", "sprBackdrop", "sprTileSheet", "sprBox"]:
            makeSprite(self.projectRoot, name, 1, 32, 32)
        makeObject(self.projectRoot, "objBox", "sprBox")
        makeTileset(self.projectRoot, "tsGround", "sprTileSheet")

        makeRoom(self.projectRoot, "rLayers", [
            instanceLayer("Instances", [makeInstance("objBox", 40, 40)]),
            spriteLayer("z48_Spr_Cliffs", [("sprCliffA", 100, 200), ("sprCliffB", 300, 400)]),
            backgroundLayer("blyr", "sprBackdrop"),
            tileLayer("z0_TileSet", "tsGround")
        ], width = 1024, height = 1024)

        self.options = atlas_packer.PackOptions(scanObjectCode = False)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testSpriteLayerGraphicsAreParsedWithPositions(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rLayers", self.options)

        self.assertEqual(len(room.spriteGraphics), 2)
        self.assertEqual(discovered["sprCliffA"].positions, [(100.0, 200.0)])
        self.assertIn(sprite_discovery.SOURCE_SPRITE_LAYER, discovered["sprCliffA"].sources)
        self.assertEqual(discovered["sprCliffA"].layerNames, ["z48_Spr_Cliffs"])

    def testBackgroundLayerSpriteIsIncludedWithNoPosition(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rLayers", self.options)

        self.assertIn("sprBackdrop", discovered)
        self.assertFalse(discovered["sprBackdrop"].hasPosition)

    def testTilesetsAreIgnoredByDefaultAndCanBeIncluded(self):
        room, discovery, ignored = discoverFor(self.projectRoot, "rLayers", self.options)
        self.assertNotIn("sprTileSheet", ignored)

        withTilesets = atlas_packer.PackOptions(scanObjectCode = False, ignoreTilesets = False)
        room, discovery, included = discoverFor(self.projectRoot, "rLayers", withTilesets)
        self.assertIn("sprTileSheet", included)
        self.assertIn(sprite_discovery.SOURCE_TILESET, included["sprTileSheet"].sources)


class TestCodeDiscovery(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeProject(self.projectRoot)

        for name in ["sprSeed", "sprDirect", "sprChooseA", "sprChooseB", "sprSpawned",
                     "sprVariantA", "sprVariantB", "sprCommentOnly"]:
            makeSprite(self.projectRoot, name, 1, 32, 32)

        makeObject(self.projectRoot, "objSeed", "sprSeed")
        makeObjectCode(self.projectRoot, "objSeed", "Create_0.gml", [
            "sprite_index = sprDirect;",
            "// sprCommentOnly should not be picked up",
            "swapSprite = choose(sprChooseA, sprChooseB);",
            'var spawned = instance_create_layer(x, y, "Instances", objSpawned);',
            "variants = VARIANTS[$ variantKey];"
        ])

        makeObject(self.projectRoot, "objSpawned", "sprSpawned")
        makeScript(self.projectRoot, "item_s", [
            "#macro VARIANTS global.variants",
            "global.variants = {};",
            "VARIANTS.FOOD_NODE = [sprVariantA, sprVariantB];"
        ])

        makeRoom(self.projectRoot, "rCode", [
            instanceLayer("Instances", [makeInstance("objSeed", 64, 64)])
        ], width = 512, height = 512)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testSecondPassFindsDirectAssignmentsAndChooseLists(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rCode", atlas_packer.PackOptions())

        self.assertIn("sprDirect", discovered)
        self.assertIn("sprChooseA", discovered)
        self.assertIn("sprChooseB", discovered)
        self.assertNotIn("sprCommentOnly", discovered)

    def testSecondPassFollowsSpawnedObjects(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rCode", atlas_packer.PackOptions())

        self.assertIn("sprSpawned", discovered)
        self.assertIn("objSpawned", discovery.scannedObjects)

    def testSecondPassFollowsAMacroIntoItsScript(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rCode", atlas_packer.PackOptions())

        self.assertIn("sprVariantA", discovered)
        self.assertIn("sprVariantB", discovered)
        self.assertTrue(any("item_s" in path for path in discovery.scannedScripts))

    def testDiscoveredFromRecordsWhereTheSpriteCameFrom(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rCode", atlas_packer.PackOptions())

        self.assertTrue(any("Create_0.gml" in origin for origin in discovered["sprDirect"].discoveredFrom))
        self.assertTrue(any("item_s" in origin for origin in discovered["sprVariantA"].discoveredFrom))

    def testRandomChoiceListsCanBeSwitchedOff(self):
        options = atlas_packer.PackOptions(includeRandomChoiceLists = False)
        room, discovery, discovered = discoverFor(self.projectRoot, "rCode", options)

        self.assertIn("sprDirect", discovered)
        self.assertNotIn("sprChooseA", discovered)
        self.assertNotIn("sprVariantA", discovered)

    def testSecondPassCanBeSwitchedOffEntirely(self):
        options = atlas_packer.PackOptions(scanObjectCode = False)
        room, discovery, discovered = discoverFor(self.projectRoot, "rCode", options)

        self.assertEqual(sorted(discovered), ["sprSeed"])

    def testCodeDiscoveredSpritesInheritTheReferencingInstancePosition(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rCode", atlas_packer.PackOptions())

        self.assertEqual(discovered["sprDirect"].positions, [(64.0, 64.0)])

    def testObjectVariableDefinitionsAreScanned(self):
        makeSprite(self.projectRoot, "sprFromProperty", 1, 32, 32)
        makeObjectWithProperty(self.projectRoot, "objProp", "portraitSprite", "sprFromProperty")
        makeRoom(self.projectRoot, "rProp", [
            instanceLayer("Instances", [makeInstance("objProp", 10, 10)])
        ], width = 256, height = 256)

        room, discovery, discovered = discoverFor(self.projectRoot, "rProp", atlas_packer.PackOptions())
        self.assertIn("sprFromProperty", discovered)


class TestInstancePropertyOverrides(unittest.TestCase):

    def testOverriddenInstancePropertyNamingASpriteIsPicked(self):
        projectRoot = tempfile.mkdtemp()
        try:
            makeProject(projectRoot)
            makeSprite(projectRoot, "sprTrigger", 1, 16, 16)
            makeSprite(projectRoot, "spr_face_portrait", 1, 48, 48)
            makeObject(projectRoot, "objTrigger", "sprTrigger")

            instance = makeInstance("objTrigger", 200, 100)
            instance["properties"] = [{
                "$GMOverriddenProperty": "v1",
                "name": "dialogueSprite",
                "resource": {"name": "spr_face_portrait", "path": "sprites/spr_face_portrait/spr_face_portrait.yy"},
                "value": "spr_face_portrait",
                "resourceType": "GMOverriddenProperty"
            }]

            makeRoom(projectRoot, "rTrigger", [instanceLayer("Instances", [instance])], width = 512, height = 512)

            room, discovery, discovered = discoverFor(projectRoot, "rTrigger",
                                                     atlas_packer.PackOptions(scanObjectCode = False))
            self.assertIn("spr_face_portrait", discovered)
            self.assertIn(sprite_discovery.SOURCE_INSTANCE_PROPERTY, discovered["spr_face_portrait"].sources)
        finally:
            shutil.rmtree(projectRoot, ignore_errors = True)


class TestCityForestShapedRoom(unittest.TestCase):
    # A miniature of the rCity_Forest case: sprites on an asset layer, an object
    # that picks its sprite from a variant list in a script, and enough pixels
    # to force more than one page

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        self.outputDir = os.path.join(self.projectRoot, "out")
        makeProject(self.projectRoot)

        self.cliffNames = ["spr_z48_cliff_top_0" + str(index) for index in range(1, 6)]
        for name in self.cliffNames:
            makeSprite(self.projectRoot, name, 1, 400, 400)

        self.variantNames = ["spr_resource_food_bush_01", "spr_resource_food_berries_01",
                             "spr_resource_food_bush_02", "spr_resource_food_berries_02"]
        for name in self.variantNames:
            makeSprite(self.projectRoot, name, 1, 400, 400)

        makeSprite(self.projectRoot, "spr_node_base", 1, 400, 400)
        makeObject(self.projectRoot, "oResourceNode", "spr_node_base")
        makeObjectCode(self.projectRoot, "oResourceNode", "Create_0.gml",
                       ["resourceVariants = VARIANTS[$ resourceVariants];"])
        makeObjectWithProperty(self.projectRoot, "oResourceFood", "resourceVariants", "FOOD_NODE", "oResourceNode")

        makeScript(self.projectRoot, "item_s", [
            "#macro VARIANTS global.variants",
            "global.variants = {};",
            "VARIANTS.FOOD_NODE = [",
            "    [3, 5, spr_resource_food_bush_01, spr_resource_food_berries_01],",
            "    [6, 9, spr_resource_food_bush_02, spr_resource_food_berries_02]",
            "];"
        ])

        makeRoom(self.projectRoot, "rCityForestMini", [
            instanceLayer("Instances", [makeInstance("oResourceFood", 100, 100)]),
            spriteLayer("z48_Spr_Cliffs", [(name, 500 + index * 40, 600) for index, name in enumerate(self.cliffNames)])
        ], width = 4096, height = 4096)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testEverySpriteLayerAndVariantSpriteReachesTheAtlas(self):
        options = atlas_packer.PackOptions(pageWidth = 1024, pageHeight = 1024)
        result = RoomAtlasBuilder(self.projectRoot, options).build("rCityForestMini", self.outputDir)
        metadata = readJson(result["metadataPath"])

        for name in self.cliffNames:
            self.assertIn(name, metadata["sprites"], name + " is missing from the atlas")
            self.assertEqual(metadata["sprites"][name]["layer_name"], "z48_Spr_Cliffs")

        for name in self.variantNames:
            self.assertIn(name, metadata["sprites"], name + " is missing from the atlas")
            self.assertIn("code", metadata["sprites"][name]["sources"])

        self.assertGreater(len(result["pageFiles"]), 1, "the fixture should need more than one page")
        self.assertEqual(metadata["meta"]["pages"], [os.path.basename(path) for path in result["pageFiles"]])
        self.assertEqual(result["problems"], [])

    def testMetadataMatchesTheTextureGroupAddStruct(self):
        options = atlas_packer.PackOptions(pageWidth = 1024, pageHeight = 1024)
        result = RoomAtlasBuilder(self.projectRoot, options).build("rCityForestMini", self.outputDir)
        metadata = readJson(result["metadataPath"])

        for spriteName, entry in metadata["sprites"].items():
            # The members texturegroup_add requires
            self.assertIn("width", entry)
            self.assertIn("height", entry)
            self.assertTrue(entry["frames"])
            for frame in entry["frames"]:
                self.assertIn("x", frame)
                self.assertIn("y", frame)
                # tp indexes the file array handed to texturegroup_add
                self.assertEqual(frame["tp"], frame["page"])
                self.assertLess(frame["tp"], len(metadata["meta"]["pages"]))

    def testMinimalStructKeepsOnlyWhatGameMakerReads(self):
        options = atlas_packer.PackOptions(pageWidth = 1024, pageHeight = 1024)
        result = RoomAtlasBuilder(self.projectRoot, options).build("rCityForestMini", self.outputDir)
        metadata = readJson(result["metadataPath"])

        minimal = atlas_writer.minimalTextureGroupStruct(metadata)

        self.assertEqual(sorted(minimal), ["sprites"])
        self.assertEqual(sorted(minimal["sprites"]), sorted(metadata["sprites"]))

        sample = minimal["sprites"][sorted(minimal["sprites"])[0]]
        self.assertNotIn("sources", sample)
        self.assertNotIn("objects", sample)
        self.assertIn("width", sample)
        self.assertIn("xoffset", sample)
        self.assertNotIn("rotated", sample["frames"][0])
        self.assertNotIn("frame_index", sample["frames"][0])

    def testRotatedFramesAreFlaggedAsIncompatible(self):
        options = atlas_packer.PackOptions(pageWidth = 512, pageHeight = 512, allowRotation = True)
        result = RoomAtlasBuilder(self.projectRoot, options).build("rCityForestMini", self.outputDir)
        metadata = readJson(result["metadataPath"])

        rotated = atlas_writer.rotatedFrameNames(metadata)
        if rotated:
            self.assertTrue(any("texturegroup_add" in warning for warning in result["warnings"]))
        else:
            self.assertEqual(rotated, [])

    def testSpritesWithNoPositionArePackedAfterThePositionedOnes(self):
        makeSprite(self.projectRoot, "spr_backdrop", 1, 100, 100)
        makeRoom(self.projectRoot, "rWithBackground", [
            instanceLayer("Instances", [makeInstance("oResourceFood", 100, 100)]),
            backgroundLayer("blyr", "spr_backdrop"),
            spriteLayer("z48_Spr_Cliffs", [(self.cliffNames[0], 500, 600)])
        ], width = 4096, height = 4096)

        options = atlas_packer.PackOptions(scanObjectCode = False)
        room, discovery, discovered = discoverFor(self.projectRoot, "rWithBackground", options)
        assetIndex = room_parser.ProjectAssetIndex(self.projectRoot)
        blocks, missing = atlas_packer.buildAssetBlocks(discovered, assetIndex)
        grouped = atlas_packer.groupAssetsBySpatialProximity(blocks, options.gridSize)

        self.assertEqual(grouped[-1].spriteName, "spr_backdrop")
        self.assertFalse(grouped[-1].hasPosition)


class TestMissingSpriteReporting(unittest.TestCase):

    def testSpriteWithNoFrameImagesIsReportedAsMissing(self):
        projectRoot = tempfile.mkdtemp()
        try:
            makeProject(projectRoot)
            makeSprite(projectRoot, "sprGood", 1, 32, 32)
            makeSprite(projectRoot, "sprBroken", 1, 32, 32)
            os.remove(os.path.join(projectRoot, "sprites", "sprBroken", "sprBroken_f0.png"))

            makeObject(projectRoot, "objGood", "sprGood")
            makeObjectCode(projectRoot, "objGood", "Create_0.gml", ["sprite_index = sprBroken;"])
            makeRoom(projectRoot, "rBroken", [
                instanceLayer("Instances", [makeInstance("objGood", 10, 10)])
            ], width = 256, height = 256)

            outputDir = os.path.join(projectRoot, "out")
            result = RoomAtlasBuilder(projectRoot, atlas_packer.PackOptions()).build("rBroken", outputDir)

            self.assertEqual(result["missingSprites"], ["sprBroken"])
            self.assertIn("sprGood", readJson(result["metadataPath"])["sprites"])
        finally:
            shutil.rmtree(projectRoot, ignore_errors = True)


if __name__ == "__main__":
    unittest.main(verbosity = 2)
