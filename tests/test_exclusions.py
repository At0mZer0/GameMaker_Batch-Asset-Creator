import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import atlas_packer
import exclude_presets
import room_parser
from test_room_atlas import (instanceLayer, makeInstance, makeObject, makeProject, makeRoom, makeSprite)
from test_second_pass import discoverFor, makeObjectCode, spriteLayer


class TestExclusions(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeProject(self.projectRoot)

        for name in ["sprMap", "sprCtrlArt", "sprMenuArt", "sprUIBadge", "sprCliff"]:
            makeSprite(self.projectRoot, name, 1, 32, 32)

        # A controller whose code reaches a menu object, which reaches more art
        makeObject(self.projectRoot, "oCtrl", None)
        makeObjectCode(self.projectRoot, "oCtrl", "Create_0.gml", [
            "loadingArt = sprCtrlArt;",
            "menu = instance_create_layer(0, 0, \"Instances\", oMenu);"
        ])
        makeObject(self.projectRoot, "oMenu", "sprMenuArt")

        makeObject(self.projectRoot, "oMapThing", "sprMap")
        makeObject(self.projectRoot, "oUIBadge", "sprUIBadge")

        makeRoom(self.projectRoot, "rMap", [
            instanceLayer("Controllers", [makeInstance("oCtrl", 0, 0)]),
            instanceLayer("Instances", [makeInstance("oMapThing", 100, 100)]),
            instanceLayer("UI_Ctrl", [makeInstance("oUIBadge", 10, 10)]),
            spriteLayer("z48_Spr_Cliffs", [("sprCliff", 200, 200)])
        ], width = 1024, height = 1024)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testWithoutExclusionsTheControllerArtIsPulledIn(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", atlas_packer.PackOptions())

        self.assertIn("sprCtrlArt", discovered)
        self.assertIn("sprMenuArt", discovered)
        self.assertIn("sprUIBadge", discovered)

    def testExcludingTheControllerCascadesToWhatItSpawns(self):
        options = atlas_packer.PackOptions(excludeCodeScanObjects = ["oCtrl"])
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", options)

        self.assertNotIn("sprCtrlArt", discovered)
        self.assertNotIn("sprMenuArt", discovered, "the menu is only reachable through oCtrl")
        self.assertIn("sprMap", discovered)
        self.assertEqual(discovery.excludedObjects, ["oCtrl"])

    def testAnExcludedObjectContributesNothingReachedThroughCode(self):
        # oMenu is only reachable through oCtrl, so excluding oMenu directly
        # must drop its own sprite too, not just leave its code unread
        options = atlas_packer.PackOptions(excludeCodeScanObjects = ["oMenu"])
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", options)

        self.assertNotIn("sprMenuArt", discovered)
        self.assertIn("sprCtrlArt", discovered, "oCtrl itself was not excluded")

    def testAnExcludedObjectThatIsPlacedKeepsItsRoomSprite(self):
        # oMapThing is placed in the room, so its sprite is a fact of the room
        options = atlas_packer.PackOptions(excludeCodeScanObjects = ["oMapThing"])
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", options)

        self.assertIn("sprMap", discovered)

    def testWildcardMatchesAFamilyOfControllers(self):
        options = atlas_packer.PackOptions(excludeCodeScanObjects = ["*Ctrl"])
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", options)

        self.assertNotIn("sprCtrlArt", discovered)

    def testExcludedLayerContentsAreLeftOutEntirely(self):
        options = atlas_packer.PackOptions(excludeLayers = ["UI_*"])
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", options)

        self.assertNotIn("sprUIBadge", discovered)
        self.assertIn("sprMap", discovered)
        self.assertIn("sprCliff", discovered)
        self.assertEqual(discovery.excludedLayers, ["UI_Ctrl"])

    def testExcludedLayerAlsoDropsSpriteLayerGraphics(self):
        options = atlas_packer.PackOptions(excludeLayers = ["z48_*"])
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", options)

        self.assertNotIn("sprCliff", discovered)
        self.assertIn("sprMap", discovered)

    def testAnObjectOnAnExcludedLayerIsNotACodeScanSeed(self):
        options = atlas_packer.PackOptions(excludeLayers = ["Controllers"])
        room, discovery, discovered = discoverFor(self.projectRoot, "rMap", options)

        self.assertNotIn("sprCtrlArt", discovered)
        self.assertNotIn("oCtrl", discovery.scannedObjects)


class TestDepthOrdering(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeProject(self.projectRoot)

        for name in ["sprBack", "sprMid", "sprFront"]:
            makeSprite(self.projectRoot, name, 1, 32, 32)
            makeObject(self.projectRoot, "obj_" + name, name)

        # Front sits at the top left of the room but on the shallowest layer,
        # so position ordering and depth ordering disagree
        back = instanceLayer("z_back", [makeInstance("obj_sprBack", 900, 900)])
        back["depth"] = 9000
        mid = instanceLayer("z_mid", [makeInstance("obj_sprMid", 500, 500)])
        mid["depth"] = 5000
        front = instanceLayer("z_front", [makeInstance("obj_sprFront", 10, 10)])
        front["depth"] = 100

        makeRoom(self.projectRoot, "rDepth", [front, mid, back], width = 1024, height = 1024)
        self.assetIndex = room_parser.ProjectAssetIndex(self.projectRoot)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def orderedNames(self, orderBy):
        options = atlas_packer.PackOptions(scanObjectCode = False, orderBy = orderBy)
        room, discovery, discovered = discoverFor(self.projectRoot, "rDepth", options)
        blocks, missing = atlas_packer.buildAssetBlocks(discovered, self.assetIndex)
        grouped = atlas_packer.groupAssetsBySpatialProximity(blocks, options.gridSize, orderBy)
        return [block.spriteName for block in grouped]

    def testLayerDepthIsRead(self):
        room = room_parser.parseRoom(dict(room_parser.parseProjectRooms(self.projectRoot))["rDepth"])
        depths = {instance.layerName: instance.layerDepth for instance in room.instances}

        self.assertEqual(depths, {"z_front": 100, "z_mid": 5000, "z_back": 9000})

    def testDepthOrderingFollowsDrawOrder(self):
        # GameMaker draws the highest depth first, so it packs first
        self.assertEqual(self.orderedNames("depth"), ["sprBack", "sprMid", "sprFront"])

    def testPositionOrderingIgnoresDepth(self):
        self.assertEqual(self.orderedNames("position"), ["sprFront", "sprMid", "sprBack"])




class TestExcludePresets(unittest.TestCase):

    def testMapPresetCarriesTheControllersAndUILayers(self):
        objects = exclude_presets.presetObjects(exclude_presets.MAP_PRESET_NAME)
        layers = exclude_presets.presetLayers(exclude_presets.MAP_PRESET_NAME)

        for name in ["oCtrl", "oGlareCtrl", "oCamera", "oBuildings", "obj_render"]:
            self.assertIn(name, objects, name + " is on the rCity_Forest Controllers layer")
        for name in ["oGUICtrl", "oGameCtrl", "oSteam", "oUiCtrl", "oTitleScreen", "oPressStart"]:
            self.assertIn(name, objects, name + " is placed in rTitleScreen")
        self.assertIn("*Menu", objects)
        self.assertEqual(layers, ["UI_*", "GUI"])

    def testEverythingPresetExcludesNothing(self):
        self.assertEqual(exclude_presets.presetObjects(exclude_presets.EVERYTHING_PRESET_NAME), [])
        self.assertEqual(exclude_presets.presetLayers(exclude_presets.EVERYTHING_PRESET_NAME), [])

    def testCommaTextRoundTrips(self):
        values = ["oCtrl", "*Menu", "obj_render"]
        self.assertEqual(exclude_presets.fromCommaText(exclude_presets.asCommaText(values)), values)
        self.assertEqual(exclude_presets.fromCommaText("  a , ,b  "), ["a", "b"])

    def testTheLibraryDefaultStaysNeutral(self):
        # PackOptions itself excludes nothing, the preset is applied by the app
        # layer, so a caller of the packer gets no surprise filtering
        self.assertEqual(atlas_packer.PackOptions().excludeCodeScanObjects, [])
        self.assertEqual(atlas_packer.PackOptions().excludeLayers, [])


if __name__ == "__main__":
    unittest.main(verbosity = 2)
