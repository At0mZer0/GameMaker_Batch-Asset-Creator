import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import atlas_packer
import character_atlas_builder as builder
import character_sources as sources
from test_room_atlas import (instanceLayer, makeInstance, makeObject, makeProject, makeRoom, makeSprite)
from test_second_pass import makeObjectCode, makeScript


# A miniature of the real project's character grammar: two body styles, two anim
# groups, one equippable outfit, one spawn only outfit, one NPC outfit, a head
# item with an attachment, and one creature family.
ANIM_STATE_SCRIPT = [
    "var _walk = merge({ animGroup : \"_walk\" }, _ANIM_4DIR);",
    "var _slash = merge({ animGroup : \"_slash\" }, _ANIM_4DIR);",
    "AnimState = {",
    "    idle : merge({ start : 0 }, _walk),",
    "    slash : merge({ animGroupUpper : \"_slash\" }, _slash)",
    "};",
    "// a commented out group must not count: animGroup : \"_neverbuilt\"",
]

SETTINGS_SCRIPT = [
    "UserSettings = {",
    "    characterOptions : {",
    "        bodyStyles : [\"male\", \"female\"],",
    "        hairs : [\"bald\", \"messy\",",
    "                 \"spiked\"],",
    "        skins : [\"Light\", \"Amber\"],",
    "        hairColors : [\"Blonde\"]",
    "    }",
    "};",
]

ITEM_SCRIPT = [
    "ITEMS[ITEM.TORSO_VAGABOND] = new Clothing(ITEM.TORSO_VAGABOND, \"Tunic\", spr_tunic_icon,",
    "    \"oLootTorsoVagabond\", 1, MATERIAL.CLOTH, EQUIP_SLOT.TORSO, 100, \" \", \"vagabond\");",
    "ITEMS[ITEM.LEGS_VAGABOND] = new Clothing(ITEM.LEGS_VAGABOND, \"Trousers\", spr_trousers_icon,",
    "    \"oLootLegsVagabond\", 1, MATERIAL.CLOTH, EQUIP_SLOT.LEGS, 100, \" \", \"vagabond\");",
    "ITEMS[ITEM.GREAT_HELM] = new Clothing(ITEM.GREAT_HELM, \"Great Helm\", spr_great_helm_icon,",
    "    \"oLootGreatHelm\", 1, MATERIAL.METAL, EQUIP_SLOT.HEAD, 100, \" \", \"great_helm\");",
    "global.headAttachmentPools = {",
    "    heavyVisor : [\"grated_visor\"]",
    "}",
]

ACTOR_UTIL_SCRIPT = [
    "function defaultActorSpawnData() {",
    "    return {",
    "        bodyStyle : \"skele\",",
    "        hairStyle : \"bald\",",
    "        outfit : \"vagabond\"",
    "    };",
    "}",
]

CREATURE_SCRIPT = [
    "makeCreatureProfile({",
    "    id : \"rat1\",",
    "    name : \"Rat\",",
    "    cols : { idle : 4, walk : 8 }",
    "});",
]


def makeCharacterProject(projectRoot):
    makeProject(projectRoot)

    makeScript(projectRoot, "actorSpriteAnimState_s", ANIM_STATE_SCRIPT)
    makeScript(projectRoot, "settings_s", SETTINGS_SCRIPT)
    makeScript(projectRoot, "item_s", ITEM_SCRIPT)
    makeScript(projectRoot, "actor_s_util", ACTOR_UTIL_SCRIPT)
    makeScript(projectRoot, "actorSpriteAnimStateCreature_s", CREATURE_SCRIPT)

    # Body layers, both styles, both anim groups
    for bodyStyle in ("male", "female"):
        for animGroup in ("_walk", "_slash"):
            makeSprite(projectRoot, "spr_" + bodyStyle + "_lower_body" + animGroup, 1, 64, 64)
            makeSprite(projectRoot, "spr_" + bodyStyle + "_upper_body" + animGroup, 1, 64, 64)
        makeSprite(projectRoot, "spr_" + bodyStyle + "_head", 1, 64, 64)

    # Hair: bald deliberately has no sheet, the way the real project says
    # "no hair layer"
    makeSprite(projectRoot, "spr_hair_messy", 1, 64, 64)
    makeSprite(projectRoot, "spr_hair_spiked", 1, 64, 64)

    # vagabond is equippable, so it belongs to the equipment atlas
    for bodyStyle in ("male", "female"):
        for animGroup in ("_walk", "_slash"):
            makeSprite(projectRoot, "spr_" + bodyStyle + "_vagabond_torso" + animGroup, 1, 64, 64)
            makeSprite(projectRoot, "spr_" + bodyStyle + "_vagabond_legs" + animGroup, 1, 64, 64)

    # zombie is spawn only, so it belongs to the actors atlas
    makeSprite(projectRoot, "spr_male_zombie_torso_walk", 1, 64, 64)

    # bumboy01 is an NPC outfit, torso and legs only, the way every NPC is
    makeSprite(projectRoot, "spr_male_bumboy01_torso_walk", 1, 64, 64)
    makeSprite(projectRoot, "spr_male_bumboy01_legs_walk", 1, 64, 64)

    makeSprite(projectRoot, "spr_head_great_helm", 1, 64, 64)
    makeSprite(projectRoot, "spr_head_grated_visor", 1, 64, 64)

    makeSprite(projectRoot, "spr_crt_rat1_idle", 1, 64, 64)
    makeSprite(projectRoot, "spr_crt_rat1_walk", 1, 64, 64)

    # The spawn point tree
    makeObject(projectRoot, "oSpawnPointAI", None)
    makeObject(projectRoot, "oSpawnPointAINpc", None, "oSpawnPointAI")
    makeObjectCode(projectRoot, "oSpawnPointAINpc", "Create_0.gml", ["event_inherited();"])

    makeObject(projectRoot, "oSpawnPointAIBumBoy01", None, "oSpawnPointAINpc")
    makeObjectCode(projectRoot, "oSpawnPointAIBumBoy01", "Create_0.gml", [
        "event_inherited();",
        "getTemplate = function() {",
        "    return {",
        "        bodyStyle : \"male\",",
        "        hairStyle : \"bald\",",
        "        outfit : \"bumboy01\"",
        "    };",
        "};",
        "/*",
        "Body Styles :",
        "    \"male\"",
        "    \"female\"",
        "Hairs",
        "    \"messy\"",
        "    \"spiked\"",
        "*/"
    ])

    makeObject(projectRoot, "oSpawnPointAIZombie", None, "oSpawnPointAI")
    makeObjectCode(projectRoot, "oSpawnPointAIZombie", "Create_0.gml", [
        "event_inherited();",
        "defaultTemplate = merge(defaultTemplate, { outfit : \"zombie\", isZombie : true });",
        "getTemplate = function() {",
        "    return {",
        "        bodyStyle : getRandomHumanBodyStyle(),",
        "        hairStyle : getRandomHairStyle([\"messy\", \"spiked\"])",
        "    };",
        "};"
    ])

    # No outfit of its own, so it wears defaultActorSpawnData's vagabond
    makeObject(projectRoot, "oSpawnPointAIPunk", None, "oSpawnPointAI")
    makeObjectCode(projectRoot, "oSpawnPointAIPunk", "Create_0.gml", [
        "event_inherited();",
        "getTemplate = function() {",
        "    return {",
        "        bodyStyle : getRandomHumanBodyStyle(),",
        "        hairStyle : getRandomHairStyle()",
        "    };",
        "};"
    ])

    makeRoom(projectRoot, "rTown", [
        instanceLayer("Instances", [makeInstance("oSpawnPointAIBumBoy01", 64, 64)])
    ])
    makeRoom(projectRoot, "rEmpty", [instanceLayer("Instances", [])])


def buildFor(projectRoot, kind, outputDir, **characterKeywords):
    packOptions = atlas_packer.PackOptions(pageWidth = 512, pageHeight = 512, padding = 2,
                                           groupName = "tg_" + kind)
    characterOptions = builder.CharacterAtlasOptions(kind = kind, **characterKeywords)
    atlasBuilder = builder.CharacterAtlasBuilder(projectRoot, packOptions, characterOptions)
    return atlasBuilder, atlasBuilder.build(outputDir)


class TestCharacterSources(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        makeCharacterProject(self.projectRoot)
        self.sources = sources.CharacterSources(self.projectRoot)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)

    def testAnimGroupsComeFromTheAnimStateTableAndSkipComments(self):
        groups = self.sources.animGroups()

        self.assertIn("_walk", groups)
        self.assertIn("_slash", groups)
        self.assertIn("", groups, "the empty group is what makes spr_<body>_head resolve")
        self.assertNotIn("_neverbuilt", groups, "a commented out group is not a group")

    def testBodyStylesTakeSkeleFromTheSpawnDefaultsNotTheCustomizationList(self):
        styles = self.sources.bodyStyles()

        self.assertEqual(["male", "female"], styles[:2])
        self.assertIn("skele", styles, "skele only reaches the draw through defaultActorSpawnData")

    def testHairStylesComeFromTheCustomizationListAcrossLines(self):
        styles = self.sources.hairStyles()

        for expected in ("bald", "messy", "spiked"):
            self.assertIn(expected, styles)

    def testOnlyNonHeadClothingItemsBecomeOutfitKeys(self):
        keys = self.sources.itemOutfitKeys()

        self.assertIn("vagabond", keys)
        self.assertNotIn("great_helm", keys,
                         "a head item resolves through getHeadLayers, not the body prefixed grammar")

    def testHeadgearTakesTheItemAndTheRolledAttachment(self):
        names = self.sources.headgearNames()

        self.assertIn("great_helm", names)
        self.assertIn("grated_visor", names, "a helmet instance can roll one more pipe layer")

    def testNpcSpawnReadsTheOutfitStringNotASpriteToken(self):
        spawns = {spawn.objectName: spawn for spawn in self.sources.npcSpawnPoints()}

        self.assertIn("oSpawnPointAIBumBoy01", spawns)
        self.assertEqual("bumboy01", spawns["oSpawnPointAIBumBoy01"].outfit)
        self.assertEqual(["male"], spawns["oSpawnPointAIBumBoy01"].bodyStyles)
        self.assertEqual(["bald"], spawns["oSpawnPointAIBumBoy01"].hairStyles,
                         "the commented out reference block must not widen the hair set")

    def testARandomisedSpawnContributesEveryOptionTheRollCanProduce(self):
        spawns = {spawn.objectName: spawn for spawn in self.sources.actorSpawnPoints()}
        zombie = spawns["oSpawnPointAIZombie"]

        self.assertEqual(["male", "female"], zombie.bodyStyles)
        self.assertEqual(["messy", "spiked"], zombie.hairStyles)
        self.assertEqual("zombie", zombie.outfit)

    def testASpawnWithNoOutfitInheritsTheSpawnDataDefault(self):
        spawns = {spawn.objectName: spawn for spawn in self.sources.actorSpawnPoints()}

        self.assertEqual("vagabond", spawns["oSpawnPointAIPunk"].outfit)
        self.assertIn("bald", spawns["oSpawnPointAIPunk"].hairStyles,
                      "getRandomHairStyle with no subset can return any style in the list")

    def testNpcSpawnPointsAreTheChildrenOfTheNpcSpawnOnly(self):
        npcNames = {spawn.objectName for spawn in self.sources.npcSpawnPoints()}
        actorNames = {spawn.objectName for spawn in self.sources.actorSpawnPoints()}

        self.assertIn("oSpawnPointAIBumBoy01", npcNames)
        self.assertNotIn("oSpawnPointAIZombie", npcNames)
        self.assertIn("oSpawnPointAIZombie", actorNames)
        self.assertIn("oSpawnPointAIPunk", actorNames)

    def testAComposedNameWithNoArtIsNotPacked(self):
        sheets = self.sources.composeOutfitSheets(["male", "female"], ["bumboy01"])

        self.assertIn("spr_male_bumboy01_torso_walk", sheets)
        self.assertNotIn("spr_female_bumboy01_torso_walk", sheets,
                         "there is no female bumboy01 art, so no name is kept for it")
        self.assertNotIn("spr_male_bumboy01_feet_walk", sheets,
                         "an NPC outfit has no feet art and the composer must not invent it")

    def testBaldResolvesToNoHairSheet(self):
        sheets = self.sources.composeHairSheets(["bald", "messy"])

        self.assertIn("spr_hair_messy", sheets)
        self.assertFalse([name for name in sheets if "bald" in name],
                         "spr_hair_bald does not exist, which is how the draw code says no hair")

    def testACasingMismatchIsReportedAndNotPacked(self):
        makeSprite(self.projectRoot, "spr_male_lower_body_walkz", 1, 64, 64)
        freshSources = sources.CharacterSources(self.projectRoot)

        # _walkz is not an anim group, _walk and _slash are, so the composed name
        # for the sheet on disk is never built and the sheet is unreachable
        sheets = freshSources.composeBodySheets(["male"])
        self.assertNotIn("spr_male_lower_body_walkz", sheets)

    def testCreatureSheetsComeFromTheProfileSpriteBase(self):
        sheets, families, unattributed = freshCreatureSheets(self.projectRoot)

        self.assertIn("rat1", families)
        self.assertIn("spr_crt_rat1_idle", sheets)
        self.assertIn("spr_crt_rat1_walk", sheets)
        self.assertEqual("rat1", sheets["spr_crt_rat1_idle"].family)


def freshCreatureSheets(projectRoot):
    return sources.CharacterSources(projectRoot).creatureSheets(True)


class TestCharacterAtlasBuild(unittest.TestCase):

    def setUp(self):
        self.projectRoot = tempfile.mkdtemp()
        self.outputRoot = tempfile.mkdtemp()
        makeCharacterProject(self.projectRoot)

    def tearDown(self):
        shutil.rmtree(self.projectRoot, ignore_errors = True)
        shutil.rmtree(self.outputRoot, ignore_errors = True)

    def packedNames(self, result):
        return {blockPlacement.block.spriteName
                for page in result["packResult"].pages
                for blockPlacement in page.blocks}

    def metadataFor(self, result):
        with open(result["metadataPath"], 'r', encoding = 'utf-8') as file:
            return json.load(file)

    def testActorsAtlasCarriesTheBodyAndTheSpawnOnlyOutfit(self):
        _, result = buildFor(self.projectRoot, builder.KIND_ACTORS, os.path.join(self.outputRoot, "actors"))
        names = self.packedNames(result)

        self.assertIn("spr_male_lower_body_walk", names)
        self.assertIn("spr_hair_messy", names)
        self.assertIn("spr_male_zombie_torso_walk", names, "zombie is spawn only, no item equips it")
        self.assertIn("spr_crt_rat1_idle", names)

    def testActorsAndEquipmentDoNotBothCarryAnEquippableOutfit(self):
        _, actorsResult = buildFor(self.projectRoot, builder.KIND_ACTORS,
                                   os.path.join(self.outputRoot, "actors"))
        _, equipmentResult = buildFor(self.projectRoot, builder.KIND_EQUIPMENT,
                                      os.path.join(self.outputRoot, "equipment"))

        actorNames = self.packedNames(actorsResult)
        equipmentNames = self.packedNames(equipmentResult)

        self.assertIn("spr_male_vagabond_torso_walk", equipmentNames)
        self.assertNotIn("spr_male_vagabond_torso_walk", actorNames,
                         "vagabond is ITEM.TORSO_VAGABOND, so packing it twice would load it twice")

    def testEquipmentAtlasCarriesTheHeadStack(self):
        _, result = buildFor(self.projectRoot, builder.KIND_EQUIPMENT,
                             os.path.join(self.outputRoot, "equipment"))
        names = self.packedNames(result)

        self.assertIn("spr_head_great_helm", names)
        self.assertIn("spr_head_grated_visor", names)

    def testNpcAtlasCarriesTheNpcOutfitAndNotTheEquippableOne(self):
        _, result = buildFor(self.projectRoot, builder.KIND_NPCS, os.path.join(self.outputRoot, "npcs"))
        names = self.packedNames(result)

        self.assertIn("spr_male_bumboy01_torso_walk", names)
        self.assertIn("spr_male_bumboy01_legs_walk", names)
        self.assertNotIn("spr_male_vagabond_torso_walk", names)

    def testNpcAtlasCanLeaveTheBodyLayersToTheActorsAtlas(self):
        _, withBody = buildFor(self.projectRoot, builder.KIND_NPCS,
                               os.path.join(self.outputRoot, "npcsWith"))
        _, withoutBody = buildFor(self.projectRoot, builder.KIND_NPCS,
                                  os.path.join(self.outputRoot, "npcsWithout"),
                                  npcIncludeBodyLayers = False)

        self.assertIn("spr_male_lower_body_walk", self.packedNames(withBody))
        self.assertNotIn("spr_male_lower_body_walk", self.packedNames(withoutBody))

    def testNpcAtlasCanBeRestrictedToOneMap(self):
        _, result = buildFor(self.projectRoot, builder.KIND_NPCS,
                             os.path.join(self.outputRoot, "npcsTown"), roomName = "rTown")

        self.assertIn("spr_male_bumboy01_torso_walk", self.packedNames(result))
        self.assertEqual("npcs_rTown", result["atlasName"])

    def testRestrictingToAMapWithNoNpcSpawnsIsAnError(self):
        with self.assertRaises(ValueError):
            buildFor(self.projectRoot, builder.KIND_NPCS,
                     os.path.join(self.outputRoot, "npcsEmpty"), roomName = "rEmpty")

    def testAPageNeverSpansTwoDrawPasses(self):
        _, result = buildFor(self.projectRoot, builder.KIND_NPCS, os.path.join(self.outputRoot, "npcs"))
        metadata = self.metadataFor(result)

        passByPage = {}
        for entry in metadata["sprites"].values():
            for frame in entry["frames"]:
                passByPage.setdefault(frame["tp"], set()).add(entry["pass"])

        for pageIndex, passNames in passByPage.items():
            self.assertEqual(1, len(passNames),
                             "page " + str(pageIndex) + " holds " + str(sorted(passNames)))

    def testMetadataNamesThePagesEachPassHasToBind(self):
        _, result = buildFor(self.projectRoot, builder.KIND_NPCS, os.path.join(self.outputRoot, "npcs"))
        metadata = self.metadataFor(result)

        self.assertIn(sources.PASS_BODY, metadata["meta"]["pass_pages"])
        self.assertIn(sources.PASS_CLOTHING, metadata["meta"]["pass_pages"])
        self.assertEqual(metadata["meta"]["pass_pages"], result["passPages"])

    def testEverySheetCarriesItsSlotAndPass(self):
        _, result = buildFor(self.projectRoot, builder.KIND_NPCS, os.path.join(self.outputRoot, "npcs"))
        metadata = self.metadataFor(result)

        entry = metadata["sprites"]["spr_male_bumboy01_torso_walk"]
        self.assertEqual(sources.SLOT_TORSO, entry["slot"])
        self.assertEqual(sources.PASS_CLOTHING, entry["pass"])
        self.assertEqual("bumboy01", entry["outfit"])
        self.assertEqual("male", entry["body_style"])
        self.assertEqual("_walk", entry["anim_group"])

    def testASheetIsPackedWholeSoTheColRowSliceStillWorks(self):
        # Every LPC layer is a single frame image the draw reads sub rectangles
        # out of with draw_sprite_part_ext, so the packer must never split it
        _, result = buildFor(self.projectRoot, builder.KIND_NPCS, os.path.join(self.outputRoot, "npcs"))
        metadata = self.metadataFor(result)

        entry = metadata["sprites"]["spr_male_bumboy01_torso_walk"]
        self.assertEqual(1, len(entry["frames"]))
        self.assertEqual(64, entry["frames"][0]["w"])
        self.assertEqual(64, entry["frames"][0]["h"])

    def testEveryPageFileIsWrittenAndListedInOrder(self):
        _, result = buildFor(self.projectRoot, builder.KIND_ACTORS, os.path.join(self.outputRoot, "actors"))
        metadata = self.metadataFor(result)

        self.assertEqual(len(result["pageFiles"]), len(metadata["meta"]["pages"]))
        for path in result["pageFiles"]:
            self.assertTrue(os.path.isfile(path))

    def testNothingIsPackedRotatedBecauseTextureGroupAddCannotDescribeIt(self):
        _, result = buildFor(self.projectRoot, builder.KIND_ACTORS, os.path.join(self.outputRoot, "actors"))
        metadata = self.metadataFor(result)

        rotated = [name for name, entry in metadata["sprites"].items()
                   if any(frame.get("rotated") for frame in entry["frames"])]
        self.assertEqual([], rotated)

    def testTheReportNamesTheBindCountPerPass(self):
        _, result = buildFor(self.projectRoot, builder.KIND_NPCS, os.path.join(self.outputRoot, "npcs"))

        with open(result["reportPath"], 'r', encoding = 'utf-8') as file:
            text = file.read()

        self.assertIn("Pages a draw pass has to bind:", text)
        self.assertIn(sources.PASS_BODY, text)


class TestRoomPackingIsUnaffected(unittest.TestCase):
    # The page break key is opt in, so a room pack must behave exactly as before

    def testPageBreakKeyIsOffByDefault(self):
        options = atlas_packer.PackOptions()
        self.assertFalse(options.breakPagesOnKeyChange)

        block = atlas_packer.AssetBlock(sprite = None, roomX = 0, roomY = 0, instanceCount = 0)
        self.assertEqual("", block.pageBreakKey)


if __name__ == "__main__":
    unittest.main()
