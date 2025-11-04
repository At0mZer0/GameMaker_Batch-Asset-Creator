import json
import json5
import uuid
import shutil
from PIL import Image 
import os
from tkinter import messagebox
from asset_types import ASSET
from async_json_loader import AsyncJsonLoader

class AssetCreator:
    # Pass in the UI instance with widgets
    def __init__(self, uiInst):
        self.ui = uiInst
        self.jsonLoader = AsyncJsonLoader(uiInst.root)

#region Core Asset Creation and Write Methods
    # Gets all the .png files in a directory and returns an array of file names in string format
    def getSpriteNamesFromFiles(self, spritesPath):
        spriteFiles = []
        allFiles = os.listdir(spritesPath)

        for fileName in allFiles:
            if fileName.endswith('.png'):
                spriteFiles.append(fileName)
        spriteNames = self.removeExtensions(spriteFiles)
        return spriteNames
    
    # Removes the file extensions from the sprite file name strings
    def removeExtensions(self, fileList):
        trimmedNames = []
        for fileName in fileList:
            nameWithNoExt = os.path.splitext(fileName)[0] # Using os.path.splitext to remove extension
            trimmedNames.append(nameWithNoExt)
        return trimmedNames

    # Creates object names by replacing textFrom to textTo entered in UI Entry widgets 
    def createObjNamesFromSpr(self, spriteNames, textFrom, textTo):
        objectNames = []
        for name in spriteNames:
            if textFrom in name:
                objName = name.replace(textFrom, textTo)
                objectNames.append(objName)
        return objectNames
    
    # Writes the data for the .yy or .yyp as json and then adds trailing commas where needed to match Game Makers format
    def writeCompatibleYY(self, data, filePath):
        jsonStr = json.dumps(data, indent = 2)

        # Add trailing commas line by line and create a list of each line
        lines = jsonStr.split('\n')
        result = []

        # Loops through and adds each line to the result list 
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Keep blank and last line unchanged
            if not stripped or i == len(lines) - 1:
                result.append(line)
                continue
            # Detect empty containers (no comma needed)
            isEmpty = stripped.endswith('[]') or stripped.endswith('{}')

            # Detect value or closing brace / bracket lines
            isValue = (
                stripped.endswith('}') or
                stripped.endswith(']') or
                stripped.endswith('"') or
                stripped.endswith('true') or
                stripped.endswith('false') or
                stripped.endswith('null') or
                stripped[-1].isdigit() # stripped[-1] will always give the last character of the string (-2 second to last etc...)
            )
            if isValue and not stripped.endswith(',') and not isEmpty:
                line += ','
            result.append(line)

        # Write the result to the file
        with open(filePath, 'w') as file:
            file.write('\n'.join(result))

    # Creates directories / Wrties the .yy files / Creates the resource data for the .yyp file
    def createDirectoryWithYYFile(self, assetType, assetPath, assetName, spriteName = None, selectedFolder = None):
        assetDir = os.path.join(assetPath, assetName)
        os.makedirs(assetDir, exist_ok = True)

        yyFilePath = os.path.join(assetDir, f"{assetName}.yy")
        assetData = self.createObjectData(assetName, selectedFolder, spriteName)

        # Creates the yy file if it doesn't exist
        self.writeCompatibleYY(assetData, yyFilePath)
        resource = self.createResourceYYP(assetType, assetName)

        return resource

    # Creates the resource data dictionary that will be added to the .yyp file
    def createResourceYYP(self, assetType, assetName):
        pathMap = {
            ASSET.OBJECT: f"objects/{assetName}/{assetName}.yy",
            ASSET.SPRITE: f"sprites/{assetName}/{assetName}.yy"
        }
        return {
            "id" : {
                "name": assetName,
                "path": pathMap[assetType]
            }
        }
        # converts data to json5 format and just replaces the last } with ,}, to account for both trailing commas
        #resourceJson = json5.dumps(objectResources, indent=2)
        #resourceJson = resourceJson.rsplit(resourceJson, "}", 1)[0] + ",},"
    
    # Takes an array of all new resources and adds them to the .yyp 'resources' array 
    def addResourcesToYYP(self, assetResources, yypFilePath):
        try:
            # Loads project data synchronously
            projectData = self.loadJson5Simple(yypFilePath)

            # Add new resources
            projectData['resources'].extend(assetResources)
            self.writeCompatibleYY(projectData, yypFilePath)

            messagebox.showinfo("Success", f"Successfully added {len(assetResources)} assets!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update YYP file: {str(e)}")
            print(f"Error updating YYP file: {e}")

    # Creates and returns disctionary data for Objects to by json.dump into the .yy file
    def createObjectData(self, objectName, selectedFolder, spriteName = None, isParent = False):
        parentObjectName = self.ui.parentObjectName.get().strip()

        # Set parentObjectId based on whether a parent was specified
        if parentObjectName and not isParent:
            parentObjectId = {
                "name": parentObjectName,
                "path": f"objects/{parentObjectName}/{parentObjectName}.yy"
            }
        else:
            parentObjectId = None

        folderName = selectedFolder.replace("folders/", "").replace(".yy", "")

        projectPath = self.ui.projectDirectory.get()
        spriteId = None
        if spriteName and self.spriteExists(spriteName, projectPath):
            spriteId = {
                "name": spriteName,
                "path": f"sprites/{spriteName}/{spriteName}.yy"
            }
        
        tags = self.parseSpriteTags(self.ui.spriteTags.get())

        objectData = {
            "$GMObject": "",
            "%Name": objectName,
            "eventList": [],
            "managed": True,
            "name": objectName,
            "overriddenProperties": [],
            "parent": {
                "name": folderName,
                "path": selectedFolder
            },
            "parentObjectId": parentObjectId,
            "persistent": False,
            "physicsAngularDamping": 0.1,
            "physicsDensity": 0.5,
            "physicsFriction": 0.2,
            "physicsGroup": 1,
            "physicsKinematic": False,
            "physicsLinearDamping": 0.1,
            "physicsObject": False,
            "physicsRestitution": 0.1,
            "physicsSensor": False,
            "physicsShape": 1,
            "physicsShapePoints": [],
            "physicsStartAwake": True,
            "properties": [],
            "resourceType": "GMObject",
            "resourceVersion": "2.0",
            "solid": False,
            "spriteId": spriteId,
            "spriteMaskId": None,
            "visible": True
        }
    
        if tags: 
            objectData["tags"] = tags
        
        return objectData
    
    def verifyOrCreateParent(self, parentObjectName, objectsPath, selectedFolder):
        # Check that parent exists
        if not parentObjectName: 
            return
        parentObjectPath = os.path.join(objectsPath, parentObjectName)
        
        if os.path.exists(parentObjectPath):
            return

        print(f"Parent object {parentObjectName} not found. Creating it...")
        os.makedirs(parentObjectPath, exist_ok = True)

        parentObjectData = self.createObjectData(parentObjectName, selectedFolder, None, True)

        parentYYPath = os.path.join(parentObjectPath, f"{parentObjectName}.yy")
        self.writeCompatibleYY(parentObjectData, parentYYPath)

        # Ceate resource Entry for the parent object
        parentResource = self.createResourceYYP(ASSET.OBJECT, parentObjectName)

        # Add parent object to the project
        try:
            projectData = self.loadJson5Simple(self.ui.yypFilePath)
            projectData['resources'].append(parentResource)
            self.writeCompatibleYY(projectData, self.ui.yypFilePath)
            print(f"Parent object '{parentObjectName}' and added to project")
        except Exception as e:
            print(f"Error adding parent object to project {e}")

    def checkForExistingAsset(self, assetNames, assetsPath):
        existing = []
        newAssets = []

        for assetName in assetNames:
            assetPath = os.path.join(assetsPath, assetName)
            if os.path.exists(assetPath):
                existing.append(assetName)
            else:
                newAssets.append(assetName)
        return existing, newAssets

    def showDuplicateMessage(self, skippedObjects, skippedSprites, createdObjects, createdSprites):
        message = "Asset Creation Complete\n\n"

        if createdObjects or createdSprites:
            message += "Successfully Created:\n"
            if createdObjects:
                message += f" {len(createdObjects)} objects\n"
            if createdSprites:
                message += f" {len(createdSprites)} sprites\n"
            message += "\n"

        if skippedObjects or skippedSprites:
            message += "Skipped (already exist):\n"
            if skippedObjects:
                message += f" {len(skippedObjects)} objects: {', '.join(skippedObjects)}"
            if skippedSprites:
                message += f" {len(skippedSprites)} sprites: {', '.join(skippedSprites)}"
            message += "\nRename existing objects or sprites and import (this avoids duplicate assets in Game Maker Studio 2)"
        
        messagebox.showinfo("Asset Creation Report", message)

        

    def generateUUID(self):
        return str(uuid.uuid4())
    
    
    def copySpritesWithUUIDs(self, spriteDir, layersDir, spriteName):
        sprUUID = self.generateUUID()
        layerUUID = self.generateUUID()

        # Get original sprite file path
        sourceDir = self.ui.spriteDirectory.get()
        sourceFilePath = os.path.join(sourceDir, f"{spriteName}.png")

        with Image.open(sourceFilePath) as img:
            width, height = img.size

        # Copy sprite and rename with UUID
        spritePath = os.path.join(spriteDir, f"{sprUUID}.png")
        shutil.copy2(sourceFilePath, spritePath)

        # Create UUID Layer directory   
        uuidDir = os.path.join(layersDir, sprUUID)
        os.makedirs(uuidDir, exist_ok = True)

        layerPath = os.path.join(uuidDir, f"{layerUUID}.png")
        shutil.copy2(sourceFilePath, layerPath)

        return {
            'sprUUID': sprUUID,
            'layerUUID': layerUUID,
            'width': width,
            'height': height
        }

    # Gets the correct values for the origin point based on drop down choice
    def getOriginValues(self, originOption, width, height):
        originMap = {
            "Top Left": (0, 0, 0),
            "Top Center": (1, int(width*.5), 0),
            "Top Right": (2, int(width), 0),
            "Middle Left": (3, 0, int(height*.5)),
            "Middle Center": (4, int(width*.5), int(height*.5)),
            "Middle Right": (5, int(width), int(height*.5)),
            "Bottom Left": (6, 0, int(height)),
            "Bottom Center": (7, int(width*.5), int(height)),
            "Bottom Right": (8, int(width), int(height))
        }
        return originMap.get(originOption, (0, 0, 0)) # Default to Top Left

    def parseSpriteTags(self, tagsString):
        # Checks to see if the sting is empty
        if not tagsString.strip():
            return []
        # splits by comma and strips each tag then adds it to the array if it's not empty
        tags = [tag.strip() for tag in tagsString.split(',') if tag.strip()]
        return tags

    def createSpriteDirectoryWithYYFile(self, assetType, assetPath, spriteName, selectedSpriteFolder):
        assetDir = os.path.join(assetPath, spriteName)
        os.makedirs(assetDir, exist_ok = True)

        layersDir = os.path.join(assetDir, "layers")
        os.makedirs(layersDir, exist_ok = True)

        yyFilePath = os.path.join(assetDir, f"{spriteName}.yy")
        imageData = self.copySpritesWithUUIDs(assetDir, layersDir, spriteName)

        assetData = self.createSpriteData(spriteName, imageData, selectedSpriteFolder)

        # Creates the yy file if it doesn't exist
        self.writeCompatibleYY(assetData, yyFilePath)
        resource = self.createResourceYYP(assetType, spriteName)

        return resource

    # frames and layers are dictionaries that generate their uuid

    def createSequenceData(self, spriteName, spriteUUID, width, height, originX, originY):
        return {
            "$GMSequence": "v1",
            "%Name": spriteName,
            "autoRecord": True,
            "backdropHeight": 768,
            "backdropImageOpacity": 0.5,
            "backdropImagePath": "",
            "backdropWidth": 1366,
            "backdropXOffset": 0.0,
            "backdropYOffset": 0.0,
            "events": {
                "$KeyframeStore<MessageEventKeyframe>": "",
                "Keyframes": [],
                "resourceType": "KeyframeStore<MessageEventKeyframe>",
                "resourceVersion": "2.0"
            },
            "eventStubScript": None,
            "eventToFunction": {},
            "length": 1.0,
            "lockOrigin": False,
            "moments": {
                "$KeyframeStore<MomentsEventKeyframe>": "",
                "Keyframes": [],
                "resourceType": "KeyframeStore<MomentsEventKeyframe>",
                "resourceVersion": "2.0"
            },
            "name": spriteName,
            "playback": 1,
            "playbackSpeed": 30.0,
            "playbackSpeedType": 0,
            "resourceType": "GMSequence",
            "resourceVersion": "2.0",
            "seqHeight": float(height),
            "seqWidth": float(width),
            "showBackdrop": True,
            "showBackdropImage": False,
            "timeUnits": 1,
            "tracks": [
                {
                    "$GMSpriteFramesTrack": "",
                    "builtinName": 0,
                    "events": [],
                    "inheritsTrackColour": True,
                    "interpolation": 1,
                    "isCreationTrack": False,
                    "keyframes": {
                        "$KeyframeStore<SpriteFrameKeyframe>": "",
                        "Keyframes": [
                            {
                                "$Keyframe<SpriteFrameKeyframe>": "",
                                "Channels": {
                                    "0": {
                                        "$SpriteFrameKeyframe": "",
                                        "Id": {
                                            "name": spriteUUID,
                                            "path": f"sprites/{spriteName}/{spriteName}.yy"
                                        },
                                        "resourceType": "SpriteFrameKeyframe",
                                        "resourceVersion": "2.0"
                                    }
                                },
                                "Disabled": False,
                                "id": self.generateUUID(),  # Generate new UUID for this keyframe
                                "IsCreationKey": False,
                                "Key": 0.0,
                                "Length": 1.0,
                                "resourceType": "Keyframe<SpriteFrameKeyframe>",
                                "resourceVersion": "2.0",
                                "Stretch": False
                            }
                        ],
                        "resourceType": "KeyframeStore<SpriteFrameKeyframe>",
                        "resourceVersion": "2.0"
                    },
                    "modifiers": [],
                    "name": "frames",
                    "resourceType": "GMSpriteFramesTrack",
                    "resourceVersion": "2.0",
                    "spriteId": None,
                    "trackColour": 0,
                    "tracks": [],
                    "traits": 0
                }
            ],
            "visibleRange": None,
            "volume": 1.0,
            "xorigin": originX,
            "yorigin": originY  # Usually set to bottom of sprite
        }

    def createSpriteData(self, spriteName, imageData, selectedSpriteFolder):
        sprUUID = imageData['sprUUID']
        layerUUID = imageData['layerUUID']
        width = imageData['width']
        height = imageData['height']

        # Get selected origin from UI
        selectedOrigin = self.ui.selectedOrigin.get()
        originInt, originX, originY = self.getOriginValues(selectedOrigin, width, height)

        tags = self.parseSpriteTags(self.ui.spriteTags.get())

        folderName = selectedSpriteFolder.replace("folders/", "").replace(".yy", "")

        spriteData =  {
            "$GMSprite": "",
            "%Name": spriteName,
            "bboxMode": 0,
            "bbox_bottom": height - 1,
            "bbox_left": 0,
            "bbox_right": width - 1,
            "bbox_top": 0,
            "collisionKind": 1,
            "collisionTolerance": 0,
            "DynamicTexturePage": False,
            "edgeFiltering": False,
            "For3D": False,
            "frames": [
                {
                    "$GMSpriteFrame": "",
                    "%Name": sprUUID,
                    "name": sprUUID,
                    "resourceType": "GMSpriteFrame",
                    "resourceVersion": "2.0"
                }
            ],
            "gridX": 0,
            "gridY": 0,
            "height": height,
            "HTile": False,
            "layers": [
                {
                    "$GMImageLayer": "",
                    "%Name": layerUUID,
                    "blendMode": 0,
                    "displayName": "default",
                    "isLocked": False,
                    "name": layerUUID,
                    "opacity": 100.0,
                    "resourceType": "GMImageLayer",
                    "resourceVersion": "2.0",
                    "visible": True
                }
            ],
            "name": spriteName,
            "nineSlice": None,
            "origin": originInt,
            "parent": {
                "name": folderName,
                "path": selectedSpriteFolder
            },
            "preMultiplyAlpha": False,
            "resourceType": "GMSprite",
            "resourceVersion": "2.0",
            "sequence": self.createSequenceData(spriteName, sprUUID, width, height, originX, originY),
            "swatchColours": None,
            "swfPrecision": 0.5,
            "textureGroupId": {
                "name": "Default",
                "path": "texturegroups/Default"
            },
            "type": 0,
            "VTile": False,
            "width": width
        }

        # Only add tags field if there are actual tags
        if tags:
            spriteData["tags"] = tags

        return spriteData
    #endregion

    def loadJson5Simple(self, filePath):
        with open(filePath, 'r', encoding='utf-8') as file:
            content = file.read()
        return json5.loads(content)

    # Main method used to create assets
    def createAssets(self, assetType = ASSET.OBJECT):
        # Get values from UI entries
        spritesPath = self.ui.spriteDirectory.get()
        projectPath = self.ui.projectDirectory.get()
        selectedFolder = self.ui.selectedAssetFolder.get()  # For Objects
        selectedSpriteFolder = self.ui.selectedSpriteFolder.get() # For Sprites
        yypFilePath = self.ui.yypFilePath


        # You got errors?? We got MASSAGES!
        if not spritesPath:
            messagebox.showerror("Error", "Please select a sprites directory")
            return
        if not projectPath:
            messagebox.showerror("Error", "Please select a Game Maker project directory")
            return
        if not selectedFolder or selectedFolder.strip() == "":
            messagebox.showerror("Error", "Please select an object target folder")
            return
        if not selectedSpriteFolder or selectedSpriteFolder.strip() == "":
            messagebox.showerror("Error", "Please select a sprite target folder")
            return


        spriteNames = self.getSpriteNamesFromFiles(spritesPath)
        spritesPath = os.path.join(projectPath, "sprites")

        skippedObjects = []
        skippedSprites = []
        createdObjects = []
        createdSprites = []

        if assetType == ASSET.OBJECT or assetType == ASSET.BOTH:
            textFrom = self.ui.textToReplace.get()
            textTo = self.ui.replaceText.get()

            if not textFrom:
                messagebox.showerror("Error", "Please enter text to replace")
                return
            if not textTo:
                messagebox.showerror("Error", "Please enter replacement text")
                return
            
            objectNames = self.createObjNamesFromSpr(spriteNames, textFrom, textTo)
            # Get game maker asset directories
            objectsPath = os.path.join(projectPath, "objects")

            skippedObjects, validObjects = self.checkForExistingAsset(objectNames, objectsPath)

            # filter sprite names if object exists to avoid problems when creating the pairs
            validSpriteNames = []
            for i, objName in enumerate(objectNames):
                if objName in validObjects:
                    validSpriteNames.append(spriteNames[i])

            # Verify parent object exists already in project and creates a blank object if it doesn't
            parentObjectName = self.ui.parentObjectName.get().strip()
            if parentObjectName:
                self.verifyOrCreateParent(parentObjectName, objectsPath, selectedFolder)
        
        assetResources = []
        
        if assetType == ASSET.OBJECT:
            # zip() will pair elements from different lists to iterate at the same index position
            for objectName, spriteName in zip(validObjects, validSpriteNames):
                assetResource = self.createDirectoryWithYYFile(ASSET.OBJECT, objectsPath, objectName, spriteName, selectedFolder)
                assetResources.append(assetResource)
                createdObjects.append(objectName)

        elif assetType == ASSET.SPRITE:
            skippedSprites, validSpriteNames = self.checkForExistingAsset(spriteNames, spritesPath)

            for spriteName in validSpriteNames:
                assetResource = self.createSpriteDirectoryWithYYFile(ASSET.SPRITE, spritesPath, spriteName, selectedSpriteFolder)
                assetResources.append(assetResource)
                createdSprites.append(spriteName)   

        elif assetType == ASSET.BOTH:
            skippedSprites, validSprites = self.checkForExistingAsset(spriteNames, spritesPath)
            # Create sprites first
            for spriteName in validSprites:
                assetResource = self.createSpriteDirectoryWithYYFile(ASSET.SPRITE, spritesPath, spriteName, selectedSpriteFolder)
                assetResources.append(assetResource)
                createdSprites.append(spriteName)

            # Create objects using referenced sprites
            for objectName, spriteName in zip(validObjects, validSpriteNames):
                assetResource = self.createDirectoryWithYYFile(ASSET.OBJECT, objectsPath, objectName, spriteName, selectedFolder)
                assetResources.append(assetResource)
                createdObjects.append(objectName)

        if assetResources:
            self.addResourcesToYYP(assetResources, yypFilePath)
            self.showDuplicateMessage(skippedObjects, skippedSprites, createdObjects, createdSprites)
        else:
            messagebox.showinfo("No Assets Created", "All assets already exist. Rename existing assets to create new ones.")

    def spriteExists(self, spriteName, projectPath):
        # Check to see if sprites actually exist with that name
        if not spriteName:
            return False
        # Check if sprite directory exists
        spritePath = os.path.join(projectPath, "sprites", spriteName)
        if not os.path.exists(spritePath):
            return False
        
        # Check if sprite .yy file exists
        spriteYYPath = os.path.join(spritePath, f"{spriteName}.yy")
        return os.path.exists(spriteYYPath)