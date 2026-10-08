import json
import os
import shutil
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import atlas_packer
import room_parser
import sprite_discovery
from room_atlas_builder import RoomAtlasBuilder
from yy_io import loadYY, stripTrailingCommas


#region Fixture helpers
def readJson(filePath):
    with open(filePath, encoding = 'utf-8') as file:
        return json.load(file)


def writeJson(filePath, data):
    os.makedirs(os.path.dirname(filePath), exist_ok = True)
    with open(filePath, 'w', encoding = 'utf-8') as file:
        json.dump(data, file, indent = 2)


def makeSprite(projectRoot, spriteName, frameCount = 1, width = 32, height = 32, originX = 0, originY = 0):
    # Writes a sprite the same shape GameMaker does: one .yy plus one png per frame
    spriteDir = os.path.join(projectRoot, "sprites", spriteName)
    os.makedirs(spriteDir, exist_ok = True)

    frames = []
    for frameIndex in range(frameCount):
        frameName = spriteName + "_f" + str(frameIndex)
        image = Image.new("RGBA", (width, height), (10 * frameIndex, 60, 200, 255))
        draw = ImageDraw.Draw(image)
        # Deliberately not symmetric so a bad rotation or a swapped frame shows up
        draw.rectangle([0, 0, max(1, width // 3), max(1, height // 2)], fill = (255, 20 * frameIndex, 0, 255))
        image.save(os.path.join(spriteDir, frameName + ".png"))
        frames.append({"$GMSpriteFrame": "", "%Name": frameName, "name": frameName, "resourceType": "GMSpriteFrame"})

    writeJson(os.path.join(spriteDir, spriteName + ".yy"), {
        "$GMSprite": "",
        "%Name": spriteName,
        "name": spriteName,
        "width": width,
        "height": height,
        "origin": 0,
        "frames": frames,
        "sequence": {"xorigin": originX, "yorigin": originY, "length": float(frameCount)},
        "textureGroupId": {"name": "Default", "path": "texturegroups/Default"},
        "resourceType": "GMSprite"
    })


def makeObject(projectRoot, objectName, spriteName = None, parentName = None):
    objectDir = os.path.join(projectRoot, "objects", objectName)
    os.makedirs(objectDir, exist_ok = True)

    writeJson(os.path.join(objectDir, objectName + ".yy"), {
        "$GMObject": "",
        "%Name": objectName,
        "name": objectName,
        "spriteId": {"name": spriteName, "path": "sprites/" + spriteName + "/" + spriteName + ".yy"} if spriteName else None,
        "parentObjectId": {"name": parentName, "path": "objects/" + parentName + "/" + parentName + ".yy"} if parentName else None,
        "resourceType": "GMObject"
    })


def makeInstance(objectName, x, y, ignore = False, instanceName = None):
    return {
        "$GMRInstance": "v4",
        "%Name": instanceName or ("inst_" + objectName + "_" + str(int(x)) + "_" + str(int(y))),
        "name": instanceName or ("inst_" + objectName + "_" + str(int(x)) + "_" + str(int(y))),
        "objectId": {"name": objectName, "path": "objects/" + objectName + "/" + objectName + ".yy"},
        "ignore": ignore,
        "x": float(x),
        "y": float(y),
        "scaleX": 1.0,
        "scaleY": 1.0,
        "rotation": 0.0,
        "resourceType": "GMRInstance"
    }


def makeRoom(projectRoot, roomName, layers, width = 1024, height = 1024):
    roomDir = os.path.join(projectRoot, "rooms", roomName)
    os.makedirs(roomDir, exist_ok = True)

    writeJson(os.path.join(roomDir, roomName + ".yy"), {
        "$GMRoom": "v1",
        "%Name": roomName,
        "name": roomName,
        "layers": layers,
        "roomSettings": {"Width": width, "Height": height, "persistent": False},
        "resourceType": "GMRoom"
    })


def instanceLayer(name, instances, subLayers = None):
    return {
        "$GMRInstanceLayer": "",
        "%Name": name,
        "name": name,
        "instances": instances,
        "layers": subLayers or [],
        "resourceType": "GMRInstanceLayer"
    }


def makeProject(projectRoot, projectName = "TestProject"):
    writeJson(os.path.join(projectRoot, projectName + ".yyp"), {
        "$GMProject": "",
        "name": projectName,
        "resources": [],
        "Folders": [],
        "resourceType": "GMProject"
    })
#endregion


class TestYYLoading(unittest.TestCase):

    def testStripTrailingCommasLeavesStringContentAlone(self):
        source = '{"a":[1,2,],"b":"Wood,}","c":{"d":1,},}'
        stripped = stripTrailingCommas(source)
        data = json.loads(stripped)

        self.assertEqual(data["a"], [1, 2])
        self.assertEqual(data["b"], "Wood,}")
        self.assertEqual(data["c"], {"d": 1})

    def testLoadYYReadsGameMakerStyleTrailingCommas(self):
        tempDir = tempfile.mkdtemp()
        try:
            filePath = os.path.join(tempDir, "sample.yy")
            with open(filePath, 'w', encoding = 'utf-8') as file:
                file.write('{\n  "name":"spr_test",\n  "frames":[\n    {"name":"a",},\n  ],\n}')

            data = loadYY(filePath)
            self.assertEqual(data["name"], "spr_test")
            self.assertEqual(data["frames"][0]["name"], "a")
        finally:
            shutil.rmtree(tempDir, ignore_errors = True)


class TestRoomParsing(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeProject(self.projectRoot)
        makeSprite(self.projectRoot, "sprBox", 1, 32, 32)
        makeSprite(self.projectRoot, "sprPlayer", 3, 16, 16, originX = 8, originY = 16)
        makeObject(self.projectRoot, "objParent", "sprBox")
        makeObject(self.projectRoot, "objBox", "sprBox")
        makeObject(self.projectRoot, "objChild", None, "objParent")
        makeObject(self.projectRoot, "objPlayer", "sprPlayer")
        makeObject(self.projectRoot, "objNoSprite", None)

        makeRoom(self.projectRoot, "rTest", [
            instanceLayer("Instances", [
                makeInstance("objBox", 10, 20),
                makeInstance("objNoSprite", 30, 40),
                makeInstance("objHidden", 50, 60, ignore = True)
            ], [
                instanceLayer("Nested", [
                    makeInstance("objPlayer", 100, 200),
                    makeInstance("objChild", 300, 400)
                ])
            ])
        ], width = 800, height = 600)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testParseProjectRoomsFindsRooms(self):
        rooms = room_parser.parseProjectRooms(self.projectRoot)
        self.assertEqual([name for name, path in rooms], ["rTest"])

    def testParseRoomReadsNestedLayersAndSize(self):
        room = room_parser.parseRoom(dict(room_parser.parseProjectRooms(self.projectRoot))["rTest"])

        self.assertEqual(room.width, 800)
        self.assertEqual(room.height, 600)
        self.assertEqual(
            sorted(instance.objectName for instance in room.instances),
            ["objBox", "objChild", "objNoSprite", "objPlayer"]
        )

    def testIgnoredInstancesAreOptional(self):
        roomPath = dict(room_parser.parseProjectRooms(self.projectRoot))["rTest"]

        withoutIgnored = room_parser.parseRoom(roomPath, includeIgnored = False)
        withIgnored = room_parser.parseRoom(roomPath, includeIgnored = True)

        self.assertNotIn("objHidden", [instance.objectName for instance in withoutIgnored.instances])
        self.assertIn("objHidden", [instance.objectName for instance in withIgnored.instances])

    def testResolveSpriteForObjectWalksTheParentChain(self):
        index = room_parser.ProjectAssetIndex(self.projectRoot)

        self.assertEqual(index.resolveSpriteForObject("objBox"), "sprBox")
        self.assertEqual(index.resolveSpriteForObject("objChild"), "sprBox")
        self.assertIsNone(index.resolveSpriteForObject("objNoSprite"))

    def testResolveSpriteSurvivesAParentCycle(self):
        makeObject(self.projectRoot, "objLoopA", None, "objLoopB")
        makeObject(self.projectRoot, "objLoopB", None, "objLoopA")
        index = room_parser.ProjectAssetIndex(self.projectRoot)

        self.assertIsNone(index.resolveSpriteForObject("objLoopA"))

    def testCollectSpriteFramesKeepsFrameOrder(self):
        index = room_parser.ProjectAssetIndex(self.projectRoot)
        sprite = index.collectSpriteFrames("sprPlayer")

        self.assertEqual(sprite.frameCount, 3)
        self.assertEqual([frame.frameIndex for frame in sprite.frames], [0, 1, 2])
        self.assertEqual([frame.width for frame in sprite.frames], [16, 16, 16])
        self.assertEqual((sprite.originX, sprite.originY), (8, 16))

    def testMissingFrameImageIsReportedAndSkipped(self):
        os.remove(os.path.join(self.projectRoot, "sprites", "sprPlayer", "sprPlayer_f1.png"))
        index = room_parser.ProjectAssetIndex(self.projectRoot)
        sprite = index.collectSpriteFrames("sprPlayer")

        self.assertEqual(sprite.frameCount, 2)
        self.assertTrue(any("Missing frame image" in warning for warning in index.warnings))


class TestGrouping(unittest.TestCase):

    def makeBlock(self, name, x, y):
        sprite = room_parser.SpriteAsset(
            name = name, yyPath = "", width = 8, height = 8,
            originX = 0, originY = 0, textureGroup = "Default"
        )
        sprite.frames.append(room_parser.SpriteFrame(name, 0, "", 8, 8))
        return atlas_packer.AssetBlock(sprite = sprite, roomX = x, roomY = y, instanceCount = 1)

    def testGridCellAssignment(self):
        blocks = [self.makeBlock("a", 0, 0), self.makeBlock("b", 255, 255), self.makeBlock("c", 256, 512)]
        atlas_packer.groupAssetsBySpatialProximity(blocks, 256)

        self.assertEqual((blocks[0].cellX, blocks[0].cellY), (0, 0))
        self.assertEqual((blocks[1].cellX, blocks[1].cellY), (0, 0))
        self.assertEqual((blocks[2].cellX, blocks[2].cellY), (1, 2))

    def testGroupOrderRunsRowsTopLeftToBottomRight(self):
        blocks = [
            self.makeBlock("bottomLeft", 10, 600),
            self.makeBlock("topRight", 600, 10),
            self.makeBlock("topLeft", 10, 10)
        ]
        grouped = atlas_packer.groupAssetsBySpatialProximity(blocks, 256)

        self.assertEqual([block.spriteName for block in grouped], ["topLeft", "topRight", "bottomLeft"])

    def testGroupingIsStableAcrossRuns(self):
        blocks = [self.makeBlock("a", 10, 10), self.makeBlock("b", 10, 10), self.makeBlock("c", 10, 10)]
        firstRun = [block.spriteName for block in atlas_packer.groupAssetsBySpatialProximity(list(blocks), 256)]
        secondRun = [block.spriteName for block in atlas_packer.groupAssetsBySpatialProximity(list(blocks), 256)]

        self.assertEqual(firstRun, secondRun)
        self.assertEqual(firstRun, ["a", "b", "c"])


class TestPacking(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeProject(self.projectRoot)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def buildBlocks(self, specs):
        # specs is a list of (spriteName, frameCount, width, height, roomX, roomY)
        index = room_parser.ProjectAssetIndex(self.projectRoot)
        blocks = []

        for spriteName, frameCount, width, height, roomX, roomY in specs:
            makeSprite(self.projectRoot, spriteName, frameCount, width, height)
            sprite = index.collectSpriteFrames(spriteName)
            blocks.append(atlas_packer.AssetBlock(
                sprite = sprite, roomX = roomX, roomY = roomY, instanceCount = 1
            ))

        return blocks

    def orderedNames(self, blocks):
        return [block.spriteName for block in blocks]

    def testPackedFramesNeverOverlapAndStayInsideThePage(self):
        options = atlas_packer.PackOptions(pageWidth = 256, pageHeight = 256, padding = 2)
        blocks = self.buildBlocks([
            ("sprA", 3, 40, 40, 0, 0),
            ("sprB", 1, 100, 60, 10, 10),
            ("sprC", 5, 30, 30, 20, 20),
            ("sprD", 2, 80, 80, 30, 30)
        ])

        result = atlas_packer.packGroupsIntoPages(
            atlas_packer.groupAssetsBySpatialProximity(blocks, 256), options
        )

        self.assertEqual(atlas_packer.validatePlacements(result, options), [])

    def testAnimationFramesStayContiguousAndInOrder(self):
        options = atlas_packer.PackOptions(pageWidth = 512, pageHeight = 512, padding = 2)
        blocks = self.buildBlocks([("sprAnim", 6, 40, 40, 0, 0)])

        result = atlas_packer.packGroupsIntoPages(blocks, options)
        placements = sorted(result.pages[0].framePlacements(), key = lambda placement: placement.frameIndex)

        self.assertEqual(len(result.pages), 1)
        self.assertEqual([placement.y for placement in placements], [placements[0].y] * 6)
        for previous, current in zip(placements, placements[1:]):
            self.assertEqual(current.x, previous.x + previous.width + options.padding)

    def testWideAnimationWrapsIntoRowsAndKeepsReadingOrder(self):
        options = atlas_packer.PackOptions(pageWidth = 128, pageHeight = 512, padding = 2)
        blocks = self.buildBlocks([("sprWide", 6, 40, 40, 0, 0)])

        result = atlas_packer.packGroupsIntoPages(blocks, options)
        block = result.pages[0].blocks[0].block

        self.assertEqual(block.columns, 3)
        self.assertEqual(block.rows, 2)
        self.assertEqual(atlas_packer.validateAnimationContiguity(result), [])

    def testBlocksOverflowOntoANewPage(self):
        options = atlas_packer.PackOptions(pageWidth = 128, pageHeight = 128, padding = 2)
        blocks = self.buildBlocks([
            ("sprOne", 1, 100, 100, 0, 0),
            ("sprTwo", 1, 100, 100, 10, 10)
        ])

        result = atlas_packer.packGroupsIntoPages(blocks, options)

        self.assertEqual(len(result.pages), 2)
        self.assertEqual(atlas_packer.validatePlacements(result, options), [])

    def testOversizeSpriteIsSkippedByDefault(self):
        options = atlas_packer.PackOptions(pageWidth = 64, pageHeight = 64, padding = 2, oversizePolicy = "skip")
        blocks = self.buildBlocks([("sprHuge", 1, 200, 200, 0, 0)])

        result = atlas_packer.packGroupsIntoPages(blocks, options)

        self.assertEqual(result.pages, [])
        self.assertEqual([block.spriteName for block in result.skippedBlocks], ["sprHuge"])

    def testOversizeSpriteCanBeScaledDown(self):
        options = atlas_packer.PackOptions(pageWidth = 64, pageHeight = 64, padding = 2, oversizePolicy = "scale")
        blocks = self.buildBlocks([("sprHuge", 1, 200, 200, 0, 0)])

        result = atlas_packer.packGroupsIntoPages(blocks, options)
        placement = result.pages[0].framePlacements()[0]

        self.assertEqual(result.skippedBlocks, [])
        self.assertLessEqual(placement.width, 64)
        self.assertLessEqual(placement.height, 64)

    def testRotationIsOnlyUsedWhenAllowed(self):
        # A block that is too wide but would fit turned on its side
        options = atlas_packer.PackOptions(pageWidth = 300, pageHeight = 300, padding = 2, allowRotation = True)
        blocks = self.buildBlocks([
            ("sprTall", 1, 60, 280, 0, 0),
            ("sprWide", 6, 40, 40, 10, 10)
        ])

        result = atlas_packer.packGroupsIntoPages(blocks, options)

        self.assertEqual(len(result.pages), 1)
        self.assertTrue(any(placement.rotated for placement in result.pages[0].blocks))
        self.assertEqual(atlas_packer.validatePlacements(result, options), [])

    def testValidationCatchesADeliberateOverlap(self):
        options = atlas_packer.PackOptions(pageWidth = 256, pageHeight = 256, padding = 2)
        blocks = self.buildBlocks([("sprA", 1, 40, 40, 0, 0), ("sprB", 1, 40, 40, 10, 10)])

        result = atlas_packer.packGroupsIntoPages(blocks, options)
        second = result.pages[0].blocks[1]
        second.frames[0].x = result.pages[0].blocks[0].frames[0].x
        second.frames[0].y = result.pages[0].blocks[0].frames[0].y

        problems = atlas_packer.validatePlacements(result, options)
        self.assertTrue(any("Overlap" in problem for problem in problems))


class TestBuildAndOutput(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        self.outputDir = os.path.join(self.projectRoot, "out")
        makeProject(self.projectRoot)

        makeSprite(self.projectRoot, "sprCrate", 1, 32, 32, originX = 16, originY = 16)
        makeSprite(self.projectRoot, "sprHero", 4, 48, 64, originX = 24, originY = 64)
        makeObject(self.projectRoot, "objCrate", "sprCrate")
        makeObject(self.projectRoot, "objHero", "sprHero")
        makeObject(self.projectRoot, "objEmpty", None)

        makeRoom(self.projectRoot, "rDemo", [
            instanceLayer("Instances", [
                makeInstance("objCrate", 64, 64),
                makeInstance("objCrate", 96, 64),
                makeInstance("objHero", 500, 300),
                makeInstance("objEmpty", 10, 10)
            ])
        ], width = 1024, height = 1024)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testBuildWritesPagesMetadataAndReport(self):
        builder = RoomAtlasBuilder(self.projectRoot, atlas_packer.PackOptions(pageWidth = 512, pageHeight = 512))
        result = builder.build("rDemo", self.outputDir, writeDebugImages = True)

        self.assertEqual(result["spriteCount"], 2)
        self.assertEqual(result["frameCount"], 5)
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["objectsWithoutSprite"], ["objEmpty"])
        self.assertTrue(os.path.isfile(result["metadataPath"]))
        self.assertTrue(os.path.isfile(result["reportPath"]))
        self.assertTrue(all(os.path.isfile(path) for path in result["pageFiles"]))
        self.assertTrue(all(os.path.isfile(path) for path in result["debugFiles"]))

    def testMetadataSchemaAndOrigins(self):
        builder = RoomAtlasBuilder(self.projectRoot, atlas_packer.PackOptions(pageWidth = 512, pageHeight = 512))
        result = builder.build("rDemo", self.outputDir)
        metadata = readJson(result["metadataPath"])

        self.assertEqual(metadata["meta"]["room"], "rDemo")
        self.assertEqual(metadata["meta"]["page_size"], [512, 512])
        self.assertEqual(metadata["meta"]["pages"], [os.path.basename(path) for path in result["pageFiles"]])
        self.assertEqual(sorted(metadata["sprites"]), ["sprCrate", "sprHero"])

        hero = metadata["sprites"]["sprHero"]
        self.assertEqual(hero["animation_length"], 4)
        self.assertEqual(hero["origin"], [24, 64])
        self.assertEqual([frame["frame_index"] for frame in hero["frames"]], [0, 1, 2, 3])
        for frame in hero["frames"]:
            self.assertEqual((frame["w"], frame["h"]), (48, 64))
            self.assertGreaterEqual(frame["x"], 0)
            self.assertLess(frame["x"] + frame["w"], 513)

    def testMetadataRoundTripsAgainstThePagePixels(self):
        # The real proof: crop every rectangle the JSON describes back out of the
        # PNG and compare it to the source frame
        builder = RoomAtlasBuilder(self.projectRoot, atlas_packer.PackOptions(pageWidth = 512, pageHeight = 512))
        result = builder.build("rDemo", self.outputDir)
        metadata = readJson(result["metadataPath"])

        pages = [Image.open(os.path.join(result["outputDir"], name)).convert("RGBA")
                 for name in metadata["meta"]["pages"]]
        index = room_parser.ProjectAssetIndex(self.projectRoot)

        for spriteName, entry in metadata["sprites"].items():
            sprite = index.collectSpriteFrames(spriteName)
            for frameEntry in entry["frames"]:
                source = Image.open(sprite.frames[frameEntry["frame_index"]].imagePath).convert("RGBA")
                cropped = pages[frameEntry["page"]].crop((
                    frameEntry["x"], frameEntry["y"],
                    frameEntry["x"] + frameEntry["w"], frameEntry["y"] + frameEntry["h"]
                ))
                self.assertEqual(source.tobytes(), cropped.tobytes(),
                                 spriteName + " frame " + str(frameEntry["frame_index"]) + " does not match the atlas")

    def testRepeatedRunsProduceTheSameLayout(self):
        options = atlas_packer.PackOptions(pageWidth = 512, pageHeight = 512)
        firstResult = RoomAtlasBuilder(self.projectRoot, options).build("rDemo", self.outputDir)
        firstMetadata = readJson(firstResult["metadataPath"])

        secondResult = RoomAtlasBuilder(self.projectRoot, options).build("rDemo", self.outputDir)
        secondMetadata = readJson(secondResult["metadataPath"])

        self.assertEqual(firstMetadata, secondMetadata)


class TestSpatialLocality(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        self.outputDir = os.path.join(self.projectRoot, "out")
        makeProject(self.projectRoot)

        # Two clusters far apart in the room, four sprites each, sized so that
        # exactly four blocks fit on a 1024 page
        self.nearNames = []
        self.farNames = []
        instances = []

        for index in range(4):
            nearName = "sprNear" + str(index)
            farName = "sprFar" + str(index)
            self.nearNames.append(nearName)
            self.farNames.append(farName)

            makeSprite(self.projectRoot, nearName, 1, 500, 500)
            makeSprite(self.projectRoot, farName, 1, 500, 500)
            makeObject(self.projectRoot, "objNear" + str(index), nearName)
            makeObject(self.projectRoot, "objFar" + str(index), farName)

            instances.append(makeInstance("objNear" + str(index), 20 + index * 10, 20 + index * 10))
            instances.append(makeInstance("objFar" + str(index), 3000 + index * 10, 3000 + index * 10))

        makeRoom(self.projectRoot, "rClusters", [instanceLayer("Instances", instances)], width = 4096, height = 4096)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testNearbyObjectsLandOnTheSamePage(self):
        options = atlas_packer.PackOptions(pageWidth = 1024, pageHeight = 1024, padding = 2, gridSize = 256)
        result = RoomAtlasBuilder(self.projectRoot, options).build("rClusters", self.outputDir)
        packResult = result["packResult"]

        pageForSprite = {}
        for page in packResult.pages:
            for blockPlacement in page.blocks:
                pageForSprite[blockPlacement.block.spriteName] = page.index

        nearPages = {pageForSprite[name] for name in self.nearNames}
        farPages = {pageForSprite[name] for name in self.farNames}

        self.assertEqual(len(nearPages), 1, "the near cluster was split across pages")
        self.assertEqual(len(farPages), 1, "the far cluster was split across pages")
        self.assertNotEqual(nearPages, farPages)


if __name__ == "__main__":
    unittest.main(verbosity = 2)
