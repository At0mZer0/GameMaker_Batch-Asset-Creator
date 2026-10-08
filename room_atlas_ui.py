import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import atlas_packer
import exclude_presets
import room_parser
from room_atlas_builder import RoomAtlasBuilder, defaultOutputDir

PAGE_SIZES = ["1024", "2048", "4096", "8192"]


class RoomAtlasPanel:
    # Room atlas packer tab. Reads the project directory chosen on the batch
    # asset tab, lists the rooms in that project and packs the sprites used by
    # the objects placed in the selected room into texture pages.

    def __init__(self, parent, uiInst):
        self.parent = parent
        self.ui = uiInst
        self.root = uiInst.root

        self.rooms = {}
        self.textureGroupNames = []
        self.messageQueue = queue.Queue()
        self.worker = None
        self.outputDirTouched = False
        self.groupNameTouched = False

        self.selectedRoom = tk.StringVar()
        self.groupName = tk.StringVar()
        self.outputDirectory = tk.StringVar()
        self.pageSize = tk.StringVar(value = "4096")
        self.padding = tk.StringVar(value = "2")
        self.gridSize = tk.StringVar(value = "256")
        self.oversizePolicy = tk.StringVar(value = "skip")
        self.orderBy = tk.StringVar(value = "depth")
        self.excludePreset = tk.StringVar(value = exclude_presets.DEFAULT_PRESET_NAME)
        self.excludeObjects = tk.StringVar(
            value = exclude_presets.asCommaText(exclude_presets.presetObjects(exclude_presets.DEFAULT_PRESET_NAME)))
        self.excludeLayers = tk.StringVar(
            value = exclude_presets.asCommaText(exclude_presets.presetLayers(exclude_presets.DEFAULT_PRESET_NAME)))
        self.allowRotation = tk.BooleanVar(value = False)
        self.includeIgnored = tk.BooleanVar(value = False)
        self.writeDebugImages = tk.BooleanVar(value = False)
        self.scanObjectCode = tk.BooleanVar(value = True)
        self.includeRandomChoiceLists = tk.BooleanVar(value = True)
        self.ignoreTilesets = tk.BooleanVar(value = True)

        self.createWidgets()
        self.selectedRoom.trace_add("write", self.onRoomChanged)

#region UI Creation Methods
    def createWidgets(self):
        self.createRoomSection()
        self.createGroupNameSection()
        self.createOutputSection()
        self.createOptionsSection()
        self.createPackButton()
        self.createLogSection()

    def createRoomSection(self):
        roomFrame = ttk.Frame(self.parent)
        roomFrame.pack(pady = (10, 5), padx = 20, fill = "x")

        ttk.Label(roomFrame, text = "Select Room: ").pack(anchor = "w")

        roomSelectFrame = ttk.Frame(roomFrame)
        roomSelectFrame.pack(fill = "x", pady = 5)

        self.roomCombobox = ttk.Combobox(roomSelectFrame, state = "readonly", textvariable = self.selectedRoom)
        self.roomCombobox.pack(side = "left", fill = "x", expand = True)

        ttk.Button(roomSelectFrame, text = "Refresh", command = self.refreshRooms).pack(side = "right", padx = (5, 0))

        self.roomInfoLabel = ttk.Label(roomFrame, text = "Select a project directory on the Batch Assets tab",
                                       font = ("Arial", 8), foreground = "gray")
        self.roomInfoLabel.pack(anchor = "w")

    def createGroupNameSection(self):
        groupFrame = ttk.Frame(self.parent)
        groupFrame.pack(pady = 5, padx = 20, fill = "x")

        ttk.Label(groupFrame, text = "Texture Group Name (for texturegroup_add): ").pack(anchor = "w")

        self.groupEntry = ttk.Entry(groupFrame, textvariable = self.groupName)
        self.groupEntry.pack(fill = "x", pady = 5)
        self.groupEntry.bind("<KeyRelease>", self.onGroupNameEdited)

        self.groupInfoLabel = ttk.Label(groupFrame, text = "Must not match a texture group that already exists",
                                        font = ("Arial", 8), foreground = "gray")
        self.groupInfoLabel.pack(anchor = "w")

    def onPresetChanged(self, event = None):
        presetName = self.excludePreset.get()
        self.excludeObjects.set(exclude_presets.asCommaText(exclude_presets.presetObjects(presetName)))
        self.excludeLayers.set(exclude_presets.asCommaText(exclude_presets.presetLayers(presetName)))

    def onGroupNameEdited(self, event = None):
        self.groupNameTouched = True
        self.checkGroupName()

    def checkGroupName(self):
        # texturegroup_add raises a fatal error on a name that already exists
        name = self.groupName.get().strip()

        if name and name in self.textureGroupNames:
            self.groupInfoLabel.config(
                text = name + " already exists in this project, texturegroup_add would fail on it",
                foreground = "#FF8080"
            )
        else:
            self.groupInfoLabel.config(
                text = "Must not match a texture group that already exists",
                foreground = "gray"
            )

    def createOutputSection(self):
        outputFrame = ttk.Frame(self.parent)
        outputFrame.pack(pady = 5, padx = 20, fill = "x")

        ttk.Label(outputFrame, text = "Output Folder: ").pack(anchor = "w")

        outputSelectFrame = ttk.Frame(outputFrame)
        outputSelectFrame.pack(fill = "x", pady = 5)

        self.outputEntry = ttk.Entry(outputSelectFrame, textvariable = self.outputDirectory)
        self.outputEntry.pack(side = "left", fill = "x", expand = True)

        ttk.Button(outputSelectFrame, text = "Browse", command = self.selectOutputDirectory).pack(side = "right", padx = (5, 0))

    def createOptionsSection(self):
        optionsFrame = ttk.Frame(self.parent)
        optionsFrame.pack(pady = 5, padx = 20, fill = "x")

        gridFrame = ttk.Frame(optionsFrame)
        gridFrame.pack(fill = "x")

        ttk.Label(gridFrame, text = "Page Size: ").grid(row = 0, column = 0, sticky = "w", pady = 2)
        ttk.Combobox(gridFrame, state = "readonly", textvariable = self.pageSize,
                     values = PAGE_SIZES, width = 8).grid(row = 0, column = 1, sticky = "w", padx = (5, 20))

        ttk.Label(gridFrame, text = "Padding: ").grid(row = 0, column = 2, sticky = "w", pady = 2)
        ttk.Spinbox(gridFrame, from_ = 0, to = 32, textvariable = self.padding,
                    width = 6).grid(row = 0, column = 3, sticky = "w", padx = (5, 0))

        ttk.Label(gridFrame, text = "Grid Cell Size: ").grid(row = 1, column = 0, sticky = "w", pady = 2)
        ttk.Spinbox(gridFrame, from_ = 16, to = 4096, increment = 16, textvariable = self.gridSize,
                    width = 8).grid(row = 1, column = 1, sticky = "w", padx = (5, 20))

        ttk.Label(gridFrame, text = "Oversize Sprites: ").grid(row = 1, column = 2, sticky = "w", pady = 2)
        ttk.Combobox(gridFrame, state = "readonly", textvariable = self.oversizePolicy,
                     values = ["skip", "scale"], width = 6).grid(row = 1, column = 3, sticky = "w", padx = (5, 0))

        ttk.Label(gridFrame, text = "Order Pages By: ").grid(row = 2, column = 0, sticky = "w", pady = 2)
        ttk.Combobox(gridFrame, state = "readonly", textvariable = self.orderBy,
                     values = ["depth", "position"], width = 8).grid(row = 2, column = 1, sticky = "w", padx = (5, 20))

        excludeFrame = ttk.Frame(optionsFrame)
        excludeFrame.pack(fill = "x", pady = (8, 0))

        presetRow = ttk.Frame(excludeFrame)
        presetRow.pack(fill = "x")
        ttk.Label(presetRow, text = "Exclusion Preset: ").pack(side = "left")
        presetCombobox = ttk.Combobox(presetRow, state = "readonly", textvariable = self.excludePreset,
                                      values = exclude_presets.presetNames(), width = 14)
        presetCombobox.pack(side = "left", padx = (5, 0))
        presetCombobox.bind("<<ComboboxSelected>>", self.onPresetChanged)

        ttk.Label(excludeFrame, text = "Exclude From Code Scan (comma separated, wildcards allowed): ").pack(anchor = "w", pady = (6, 0))
        ttk.Entry(excludeFrame, textvariable = self.excludeObjects).pack(fill = "x", pady = 3)
        ttk.Label(excludeFrame, text = "Controllers reach art the room never draws, e.g. oCtrl, obj_render",
                  font = ("Arial", 8), foreground = "gray").pack(anchor = "w")

        ttk.Label(excludeFrame, text = "Exclude Layers (comma separated, wildcards allowed): ").pack(anchor = "w", pady = (8, 0))
        ttk.Entry(excludeFrame, textvariable = self.excludeLayers).pack(fill = "x", pady = 3)
        ttk.Label(excludeFrame, text = "Everything on these layers is left out, e.g. UI_*, GUI",
                  font = ("Arial", 8), foreground = "gray").pack(anchor = "w")

        checkFrame = ttk.Frame(optionsFrame)
        checkFrame.pack(fill = "x", pady = (5, 0))

        ttk.Checkbutton(checkFrame, text = "Second pass into object code",
                        variable = self.scanObjectCode).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Include random choice lists (choose / variant arrays)",
                        variable = self.includeRandomChoiceLists).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Ignore tilesets",
                        variable = self.ignoreTilesets).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Allow 90 degree rotation",
                        variable = self.allowRotation).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Include instances flagged as ignored",
                        variable = self.includeIgnored).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Write debug preview images",
                        variable = self.writeDebugImages).pack(anchor = "w")

    def createPackButton(self):
        buttonFrame = ttk.Frame(self.parent)
        buttonFrame.pack(pady = 10)

        self.packButton = ttk.Button(buttonFrame, text = "Pack Room Atlases", command = self.runPacking)
        self.packButton.pack(side = "left", padx = (0, 5))

        ttk.Button(buttonFrame, text = "Open Output Folder", command = self.openOutputFolder).pack(side = "left")

    def createLogSection(self):
        logFrame = ttk.Frame(self.parent)
        logFrame.pack(pady = (0, 10), padx = 20, fill = "both", expand = True)

        ttk.Label(logFrame, text = "Log: ").pack(anchor = "w")

        textFrame = ttk.Frame(logFrame)
        textFrame.pack(fill = "both", expand = True)

        scrollbar = ttk.Scrollbar(textFrame)
        scrollbar.pack(side = "right", fill = "y")

        self.logText = tk.Text(textFrame, height = 10, wrap = "word", yscrollcommand = scrollbar.set,
                               background = "#404040", foreground = "#B8C5D1", insertbackground = "#B8C5D1",
                               borderwidth = 0)
        self.logText.pack(side = "left", fill = "both", expand = True)
        scrollbar.config(command = self.logText.yview)
#endregion

#region Room list
    def refreshRooms(self):
        projectPath = self.ui.projectDirectory.get()

        if not projectPath:
            self.roomInfoLabel.config(text = "Select a project directory on the Batch Assets tab")
            self.roomCombobox['values'] = []
            self.rooms = {}
            return

        if room_parser.isLegacyGMXProject(projectPath):
            self.roomInfoLabel.config(text = "GameMaker 1.4 .gmx projects are not supported")
            self.roomCombobox['values'] = []
            self.rooms = {}
            return

        try:
            roomList = room_parser.parseProjectRooms(projectPath)
        except Exception as error:
            self.roomInfoLabel.config(text = "Could not read rooms: " + str(error))
            self.roomCombobox['values'] = []
            self.rooms = {}
            return

        self.rooms = dict(roomList)
        self.textureGroupNames = room_parser.listTextureGroupNames(projectPath)
        roomNames = [name for name, path in roomList]
        self.roomCombobox['values'] = roomNames

        if roomNames:
            self.roomCombobox.current(0)
            self.selectedRoom.set(roomNames[0])
            self.roomInfoLabel.config(text = str(len(roomNames)) + " rooms found in this project")
        else:
            self.selectedRoom.set("")
            self.roomInfoLabel.config(text = "No rooms found in this project")

    def onRoomChanged(self, *args):
        # Keeps the output folder pointing at the selected room until the user
        # picks a folder of their own
        if self.outputDirTouched:
            return

        projectPath = self.ui.projectDirectory.get()
        roomName = self.selectedRoom.get()

        if projectPath and roomName:
            self.outputDirectory.set(defaultOutputDir(projectPath, roomName))

        if roomName and not self.groupNameTouched:
            self.groupName.set(roomName)
            self.checkGroupName()

    def selectOutputDirectory(self):
        directory = filedialog.askdirectory(title = "Select Atlas Output Directory")
        if directory:
            self.outputDirTouched = True
            self.outputDirectory.set(directory)

    def openOutputFolder(self):
        outputPath = self.outputDirectory.get()
        if outputPath and os.path.isdir(outputPath):
            os.startfile(outputPath)
        else:
            messagebox.showinfo("Nothing to open", "Pack a room first, the output folder does not exist yet")
#endregion

#region Packing
    def readOptions(self):
        pageSize = int(self.pageSize.get())
        return atlas_packer.PackOptions(
            pageWidth = pageSize,
            pageHeight = pageSize,
            padding = max(0, int(self.padding.get())),
            gridSize = max(1, int(self.gridSize.get())),
            allowRotation = self.allowRotation.get(),
            oversizePolicy = self.oversizePolicy.get(),
            includeIgnoredInstances = self.includeIgnored.get(),
            groupName = self.groupName.get().strip(),
            orderBy = self.orderBy.get(),
            excludeCodeScanObjects = exclude_presets.fromCommaText(self.excludeObjects.get()),
            excludeLayers = exclude_presets.fromCommaText(self.excludeLayers.get()),
            scanObjectCode = self.scanObjectCode.get(),
            includeRandomChoiceLists = self.includeRandomChoiceLists.get(),
            ignoreTilesets = self.ignoreTilesets.get()
        )

    def runPacking(self):
        projectPath = self.ui.projectDirectory.get()
        roomName = self.selectedRoom.get()

        if not projectPath:
            messagebox.showerror("Error", "Please select a Game Maker project directory on the Batch Assets tab")
            return
        if not roomName:
            messagebox.showerror("Error", "Please select a room to pack")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "A pack is already running")
            return

        try:
            options = self.readOptions()
        except ValueError:
            messagebox.showerror("Error", "Page size, padding and grid cell size all have to be whole numbers")
            return

        outputPath = self.outputDirectory.get() or defaultOutputDir(projectPath, roomName)
        self.outputDirectory.set(outputPath)

        self.logText.delete("1.0", "end")
        self.packButton.config(state = "disabled")

        self.worker = threading.Thread(
            target = self.packWorker,
            args = (projectPath, roomName, options, outputPath, self.writeDebugImages.get()),
            daemon = True
        )
        self.worker.start()
        self.root.after(100, self.drainMessageQueue)

    def packWorker(self, projectPath, roomName, options, outputPath, writeDebugImages):
        try:
            builder = RoomAtlasBuilder(projectPath, options, lambda message: self.messageQueue.put(("log", message)))
            result = builder.build(roomName, outputPath, writeDebugImages)
            self.messageQueue.put(("done", result))
        except Exception as error:
            self.messageQueue.put(("error", str(error)))

    def drainMessageQueue(self):
        # Runs on the tkinter thread so the worker never touches a widget
        finished = False

        while True:
            try:
                kind, payload = self.messageQueue.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self.appendLog(payload)
            elif kind == "done":
                self.onPackComplete(payload)
                finished = True
            elif kind == "error":
                self.appendLog("Failed: " + payload)
                messagebox.showerror("Pack Failed", payload)
                finished = True

        if finished:
            self.packButton.config(state = "normal")
        else:
            self.root.after(100, self.drainMessageQueue)

    def appendLog(self, message):
        self.logText.insert("end", message + "\n")
        self.logText.see("end")

    def onPackComplete(self, result):
        pageCount = len(result["pageFiles"])
        summary = ("Packed " + str(result["spriteCount"]) + " sprites and " +
                   str(result["frameCount"]) + " frames onto " + str(pageCount) + " texture page(s)")

        self.appendLog(summary)
        self.appendLog("Texture group name: " + result["groupName"])
        if result["excludedObjects"]:
            self.appendLog("Code scan skipped: " + ", ".join(sorted(result["excludedObjects"])))
        if result["excludedLayers"]:
            self.appendLog("Layers skipped: " + ", ".join(sorted(result["excludedLayers"])))
        for source in sorted(result["discovery"].countsBySource()):
            self.appendLog("    " + source + ": " + str(result["discovery"].countsBySource()[source]))
        self.appendLog("Output: " + result["outputDir"])

        message = summary + "\n\nOutput folder:\n" + result["outputDir"]

        if result["problems"]:
            message += "\n\nValidation problems: " + str(len(result["problems"]))
        if result["warnings"]:
            message += "\nWarnings: " + str(len(result["warnings"]))
        if result["objectsWithoutSprite"]:
            message += "\nObjects with no sprite: " + str(len(result["objectsWithoutSprite"]))
        if result["missingSprites"]:
            message += "\nReferenced but missing on disk: " + str(len(result["missingSprites"]))
        if result["groupNameClash"]:
            message += "\n\nWARNING: the texture group " + result["groupName"] + " already exists in this project, texturegroup_add fails fatally on an existing group name"

        if result["problems"]:
            messagebox.showwarning("Pack Complete With Problems", message)
        else:
            messagebox.showinfo("Pack Complete", message)
#endregion
