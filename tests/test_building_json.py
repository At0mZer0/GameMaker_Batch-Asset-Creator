import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import atlas_packer
import room_parser
import sprite_discovery
from test_room_atlas import (instanceLayer, makeInstance, makeObject, makeProject,
                             makeRoom, makeSprite, writeJson)
from test_second_pass import discoverFor


def makeObjectWithOverride(projectRoot, objectName, parentName, propertyName, value, spriteName = None):
    # A child object setting a parent variable definition, the shape GameMaker
    # writes when you override buildingName on obj_build_01
    objectDir = os.path.join(projectRoot, "objects", objectName)
    os.makedirs(objectDir, exist_ok = True)

    writeJson(os.path.join(objectDir, objectName + ".yy"), {
        "$GMObject": "",
        "name": objectName,
        "spriteId": {"name": spriteName, "path": "sprites/" + spriteName + "/" + spriteName + ".yy"} if spriteName else None,
        "parentObjectId": {"name": parentName, "path": "objects/" + parentName + "/" + parentName + ".yy"},
        "properties": [],
        "overriddenProperties": [{
            "$GMOverriddenProperty": "v1",
            "name": "",
            "objectId": {"name": parentName, "path": "objects/" + parentName + "/" + parentName + ".yy"},
            "propertyId": {"name": propertyName, "path": "objects/" + parentName + "/" + parentName + ".yy"},
            "value": value,
            "resourceType": "GMOverriddenProperty"
        }],
        "resourceType": "GMObject"
    })


def makeBuildingParent(projectRoot, objectName = "oBuildingJSON"):
    objectDir = os.path.join(projectRoot, "objects", objectName)
    os.makedirs(objectDir, exist_ok = True)

    writeJson(os.path.join(objectDir, objectName + ".yy"), {
        "$GMObject": "",
        "name": objectName,
        "spriteId": None,
        "parentObjectId": None,
        "properties": [{
            "$GMObjectProperty": "v2",
            "name": "buildingName",
            "value": "",
            "varType": 2,
            "resourceType": "GMObjectProperty"
        }],
        "overriddenProperties": [],
        "resourceType": "GMObject"
    })


def writeIncludedFile(projectRoot, fileName, data):
    dataFiles = os.path.join(projectRoot, "datafiles")
    os.makedirs(dataFiles, exist_ok = True)
    with open(os.path.join(dataFiles, fileName), 'w', encoding = 'utf-8') as file:
        json.dump(data, file, indent = 2)


class TestBuildingJsonLookup(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeProject(self.projectRoot)

        makeSprite(self.projectRoot, "spr_build_01_json", 1, 32, 32)
        makeSprite(self.projectRoot, "spr_dresser", 1, 32, 32)
        makeSprite(self.projectRoot, "spr_chair", 1, 32, 32)
        makeSprite(self.projectRoot, "spr_pillar", 1, 32, 32)
        makeSprite(self.projectRoot, "spr_floor", 1, 32, 32)

        makeBuildingParent(self.projectRoot)
        makeObjectWithOverride(self.projectRoot, "obj_build_01", "oBuildingJSON",
                               "buildingName", "Build_01", "spr_build_01_json")

        makeObject(self.projectRoot, "obj_dresser", "spr_dresser")
        makeObject(self.projectRoot, "obj_chair", "spr_chair")
        makeObject(self.projectRoot, "obj_pillar", "spr_pillar")
        makeObject(self.projectRoot, "oBuildingRoom", "spr_floor")

        # The nesting Build_XX.json actually uses: rooms, then contents
        writeIncludedFile(self.projectRoot, "Build_01.json", {
            "buildingProps": {"buildWidth": 100, "buildYthickness": 50, "buildZheight": 80},
            "arrays": {
                "buildingRooms": [{
                    "objectType": "oBuildingRoom",
                    "variables": {
                        "contents": [
                            {"objectType": "obj_dresser", "variables": {}},
                            {"objectType": "obj_chair", "variables": {}}
                        ]
                    }
                }],
                "pillars": [{"objectType": "obj_pillar", "variables": {}}]
            }
        })

        makeRoom(self.projectRoot, "rBuild", [
            instanceLayer("Instances", [makeInstance("obj_build_01", 300, 400)])
        ], width = 1024, height = 1024)

        self.discovery = sprite_discovery.RoomSpriteDiscovery(
            self.projectRoot,
            room_parser.ProjectAssetIndex(self.projectRoot),
            sprite_discovery.ProjectSymbolIndex(self.projectRoot),
            atlas_packer.PackOptions()
        )

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testObjectTypesAreCollectedFromNestedJson(self):
        with open(os.path.join(self.projectRoot, "datafiles", "Build_01.json"), encoding = 'utf-8') as file:
            data = json.load(file)

        found = sprite_discovery.collectObjectTypesFromJson(data, [])
        self.assertEqual(sorted(found), ["oBuildingRoom", "obj_chair", "obj_dresser", "obj_pillar"])

    def testAChildOfTheBuildingObjectIsRecognised(self):
        self.assertTrue(self.discovery.isBuildingJsonObject("obj_build_01"))
        self.assertTrue(self.discovery.isBuildingJsonObject("oBuildingJSON"))
        self.assertFalse(self.discovery.isBuildingJsonObject("obj_chair"))

    def testBuildingNameComesFromTheChildOverride(self):
        self.assertEqual(self.discovery.objectPropertyValue("obj_build_01", "buildingName"), "Build_01")

    def testBuildingContentsReachTheAtlas(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rBuild", atlas_packer.PackOptions())

        for name in ["spr_dresser", "spr_chair", "spr_pillar", "spr_floor"]:
            self.assertIn(name, discovered, name + " should come from Build_01.json")

        self.assertIn(sprite_discovery.SOURCE_BUILDING_JSON, discovered["spr_dresser"].sources)
        self.assertEqual(discovery.buildingFiles, ["Build_01"])

    def testBuildingContentsTakeThePlacedInstancePosition(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rBuild", atlas_packer.PackOptions())

        self.assertEqual(discovered["spr_dresser"].positions, [(300.0, 400.0)])

    def testDiscoveredFromNamesTheIncludedFile(self):
        room, discovery, discovered = discoverFor(self.projectRoot, "rBuild", atlas_packer.PackOptions())

        self.assertTrue(any("Build_01.json" in origin for origin in discovered["spr_dresser"].discoveredFrom))

    def testAnInstanceOverrideBeatsTheObjectDefault(self):
        writeIncludedFile(self.projectRoot, "Build_02.json", {
            "arrays": {"pillars": [{"objectType": "obj_chair", "variables": {}}]}
        })

        instance = makeInstance("obj_build_01", 10, 10)
        instance["properties"] = [{
            "$GMOverriddenProperty": "v1",
            "name": "buildingName",
            "value": "Build_02",
            "resourceType": "GMOverriddenProperty"
        }]
        makeRoom(self.projectRoot, "rOverride", [instanceLayer("Instances", [instance])],
                 width = 512, height = 512)

        room, discovery, discovered = discoverFor(self.projectRoot, "rOverride", atlas_packer.PackOptions())

        self.assertEqual(discovery.buildingFiles, ["Build_02"])
        self.assertIn("spr_chair", discovered)
        self.assertNotIn("spr_dresser", discovered)

    def testAMissingIncludedFileIsWarnedAboutNotFatal(self):
        makeObjectWithOverride(self.projectRoot, "obj_build_99", "oBuildingJSON",
                               "buildingName", "Build_99")
        makeRoom(self.projectRoot, "rMissing", [
            instanceLayer("Instances", [makeInstance("obj_build_99", 10, 10)])
        ], width = 512, height = 512)

        room, discovery, discovered = discoverFor(self.projectRoot, "rMissing", atlas_packer.PackOptions())

        self.assertTrue(any("Build_99.json was not found" in warning for warning in discovery.warnings))

    def testTheLookupCanBeSwitchedOff(self):
        options = atlas_packer.PackOptions(buildingJsonObjects = [])
        room, discovery, discovered = discoverFor(self.projectRoot, "rBuild", options)

        self.assertNotIn("spr_dresser", discovered)
        self.assertEqual(discovery.buildingFiles, [])


if __name__ == "__main__":
    unittest.main(verbosity = 2)
