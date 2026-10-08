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
from room_atlas_builder import RoomAtlasBuilder
from test_room_atlas import (instanceLayer, makeInstance, makeObject, makeRoom,
                             makeSprite, readJson, writeJson)


def makeProjectWithTextureGroups(projectRoot, groupNames, projectName = "TestProject"):
    writeJson(os.path.join(projectRoot, projectName + ".yyp"), {
        "$GMProject": "",
        "name": projectName,
        "resources": [],
        "Folders": [],
        "TextureGroups": [
            {"$GMTextureGroup": "", "name": name, "resourceType": "GMTextureGroup"}
            for name in groupNames
        ],
        "resourceType": "GMProject"
    })


class TestTextureGroupName(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        self.outputDir = os.path.join(self.projectRoot, "out")
        makeProjectWithTextureGroups(self.projectRoot, ["Default", "City", "Forest"])

        makeSprite(self.projectRoot, "sprCrate", 1, 32, 32)
        makeObject(self.projectRoot, "objCrate", "sprCrate")
        makeRoom(self.projectRoot, "rCity", [
            instanceLayer("Instances", [makeInstance("objCrate", 40, 40)])
        ], width = 512, height = 512)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testProjectTextureGroupsAreListed(self):
        self.assertEqual(room_parser.listTextureGroupNames(self.projectRoot), ["City", "Default", "Forest"])

    def testGroupNameDefaultsToTheRoomName(self):
        result = RoomAtlasBuilder(self.projectRoot, atlas_packer.PackOptions()).build("rCity", self.outputDir)
        metadata = readJson(result["metadataPath"])

        self.assertEqual(result["groupName"], "rCity")
        self.assertEqual(metadata["meta"]["group_name"], "rCity")
        self.assertFalse(result["groupNameClash"])

    def testCustomGroupNameIsUsed(self):
        options = atlas_packer.PackOptions(groupName = "tg_RoomCity")
        result = RoomAtlasBuilder(self.projectRoot, options).build("rCity", self.outputDir)

        self.assertEqual(result["groupName"], "tg_RoomCity")
        self.assertEqual(readJson(result["metadataPath"])["meta"]["group_name"], "tg_RoomCity")
        self.assertFalse(result["groupNameClash"])

    def testAGroupNameThatAlreadyExistsIsFlagged(self):
        options = atlas_packer.PackOptions(groupName = "City")
        result = RoomAtlasBuilder(self.projectRoot, options).build("rCity", self.outputDir)

        self.assertTrue(result["groupNameClash"])
        self.assertTrue(any("already a texture group" in warning for warning in result["warnings"]))

    def testBlankGroupNameFallsBackToTheRoomName(self):
        options = atlas_packer.PackOptions(groupName = "   ")
        self.assertEqual(atlas_writer.resolveGroupName(options, "rCity"), "rCity")

    def testReportNamesTheGroup(self):
        options = atlas_packer.PackOptions(groupName = "tg_RoomCity")
        result = RoomAtlasBuilder(self.projectRoot, options).build("rCity", self.outputDir)

        with open(result["reportPath"], encoding = 'utf-8') as file:
            report = file.read()

        self.assertIn("Texture group name: tg_RoomCity", report)


if __name__ == "__main__":
    unittest.main(verbosity = 2)
