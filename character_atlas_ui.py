import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import atlas_packer
import character_atlas_builder as builder
import room_parser

PAGE_SIZES = ["1024", "2048", "4096", "8192"]


class CharacterAtlasPanel:
    # Character atlas packer tab. This is deliberately not an exclusion preset on
    # the room packer: a room pack starts from what a .yy file says is placed and
    # subtracts, and none of the character art is placed anywhere. A body sheet is
    # reached by concatenating a body style, a layer word and an anim group at
    # runtime, so the only way to find it is to build the same names the draw code
    # builds and check which ones exist. That has no room, no layers and no
    # instances, which is why it gets its own tab and its own three buttons.

    def __init__(self, parent, uiInst):
        self.parent = parent
        self.ui = uiInst
        self.root = uiInst.root

        self.rooms = {}
        self.textureGroupNames = []
        self.messageQueue = queue.Queue()
        self.worker = None
        self.buttons = []

        self.npcRoom = tk.StringVar()
        self.groupPrefix = tk.StringVar(value = "tg_")
        self.outputDirectory = tk.StringVar()
        self.outputDirTouched = False
        self.pageSize = tk.StringVar(value = "4096")
        self.padding = tk.StringVar(value = "2")
        self.oversizePolicy = tk.StringVar(value = "skip")

        self.pageBreakPerPass = tk.BooleanVar(value = True)
        self.pageBreakPerSlot = tk.BooleanVar(value = False)
        self.npcIncludeBodyLayers = tk.BooleanVar(value = True)
        self.includeItemIcons = tk.BooleanVar(value = False)
        self.includeWrists = tk.BooleanVar(value = False)
        self.includeUnattributedCreatures = tk.BooleanVar(value = True)
        self.writeDebugImages = tk.BooleanVar(value = False)

        self.createWidgets()

#region UI Creation Methods
    def createWidgets(self):
        self.createIntroSection()
        self.createNpcRoomSection()
        self.createGroupSection()
        self.createOutputSection()
        self.createOptionsSection()
        self.createPackButtons()
        self.createLogSection()

    def createIntroSection(self):
        introFrame = ttk.Frame(self.parent)
        introFrame.pack(pady = (10, 0), padx = 20, fill = "x")

        ttk.Label(introFrame,
                  text = "Packs the character art this project can build, layer major, for the actor draw controller.",
                  font = ("Arial", 9)).pack(anchor = "w")
        ttk.Label(introFrame,
                  text = "No room is parsed. The sheet list is composed from the customization options, the item "
                         "table,\nthe spawn templates and the creature profiles, then checked against the sprite "
                         "folder.",
                  font = ("Arial", 8), foreground = "gray", justify = "left").pack(anchor = "w")

    def createNpcRoomSection(self):
        roomFrame = ttk.Frame(self.parent)
        roomFrame.pack(pady = (10, 5), padx = 20, fill = "x")

        ttk.Label(roomFrame, text = "NPC Map (NPCs button only): ").pack(anchor = "w")

        roomSelectFrame = ttk.Frame(roomFrame)
        roomSelectFrame.pack(fill = "x", pady = 5)

        self.roomCombobox = ttk.Combobox(roomSelectFrame, state = "readonly", textvariable = self.npcRoom)
        self.roomCombobox.pack(side = "left", fill = "x", expand = True)

        ttk.Button(roomSelectFrame, text = "Refresh", command = self.refreshRooms).pack(side = "right", padx = (5, 0))

        self.roomInfoLabel = ttk.Label(
            roomFrame,
            text = "Scans the map for objects that inherit from oSpawnPointAINpc. "
                   "Leave on (every map) to pack them all.",
            font = ("Arial", 8), foreground = "gray")
        self.roomInfoLabel.pack(anchor = "w")

    def createGroupSection(self):
        groupFrame = ttk.Frame(self.parent)
        groupFrame.pack(pady = 5, padx = 20, fill = "x")

        ttk.Label(groupFrame, text = "Texture Group Prefix (for texturegroup_add): ").pack(anchor = "w")

        self.groupEntry = ttk.Entry(groupFrame, textvariable = self.groupPrefix)
        self.groupEntry.pack(fill = "x", pady = 5)
        self.groupEntry.bind("<KeyRelease>", lambda event: self.checkGroupNames())

        self.groupInfoLabel = ttk.Label(groupFrame, text = "Each button appends its own name, e.g. tg_actors",
                                        font = ("Arial", 8), foreground = "gray")
        self.groupInfoLabel.pack(anchor = "w")

    def createOutputSection(self):
        outputFrame = ttk.Frame(self.parent)
        outputFrame.pack(pady = 5, padx = 20, fill = "x")

        ttk.Label(outputFrame, text = "Output Folder (a subfolder per atlas is created inside it): ").pack(anchor = "w")

        outputSelectFrame = ttk.Frame(outputFrame)
        outputSelectFrame.pack(fill = "x", pady = 5)

        self.outputEntry = ttk.Entry(outputSelectFrame, textvariable = self.outputDirectory)
        self.outputEntry.pack(side = "left", fill = "x", expand = True)

        ttk.Button(outputSelectFrame, text = "Browse",
                   command = self.selectOutputDirectory).pack(side = "right", padx = (5, 0))

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

        ttk.Label(gridFrame, text = "Oversize Sprites: ").grid(row = 1, column = 0, sticky = "w", pady = 2)
        ttk.Combobox(gridFrame, state = "readonly", textvariable = self.oversizePolicy,
                     values = ["skip", "scale"], width = 8).grid(row = 1, column = 1, sticky = "w", padx = (5, 20))

        checkFrame = ttk.Frame(optionsFrame)
        checkFrame.pack(fill = "x", pady = (8, 0))

        ttk.Checkbutton(checkFrame, text = "One page per draw pass (body / clothing / weapon)",
                        variable = self.pageBreakPerPass).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "One page per draw slot as well (more pages, one bind per layer)",
                        variable = self.pageBreakPerSlot).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "NPC atlas carries its own body layers (also in the actors atlas)",
                        variable = self.npcIncludeBodyLayers).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Equipment atlas includes inventory icons",
                        variable = self.includeItemIcons).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Include the wrists slot (resolved by the outfit code, never drawn)",
                        variable = self.includeWrists).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Include creature sheets no profile could be rebuilt from",
                        variable = self.includeUnattributedCreatures).pack(anchor = "w")
        ttk.Checkbutton(checkFrame, text = "Write debug preview images",
                        variable = self.writeDebugImages).pack(anchor = "w")

    def createPackButtons(self):
        buttonFrame = ttk.Frame(self.parent)
        buttonFrame.pack(pady = 10)

        self.buttons = []
        for kind, label in (
            (builder.KIND_ACTORS, "Pack Actors / Creatures"),
            (builder.KIND_NPCS, "Pack NPCs"),
            (builder.KIND_EQUIPMENT, "Pack Equipment")
        ):
            button = ttk.Button(buttonFrame, text = label,
                                command = lambda packKind = kind: self.runPacking(packKind))
            button.pack(side = "left", padx = (0, 5))
            self.buttons.append(button)

        openButton = ttk.Button(buttonFrame, text = "Open Output", command = self.openOutputFolder)
        openButton.pack(side = "left")
        self.buttons.append(openButton)

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

#region Project state
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

        # An empty first entry is "every NPC spawn point in the project"
        roomNames = [""] + [name for name, path in roomList]
        self.roomCombobox['values'] = roomNames
        self.roomCombobox.current(0)
        self.npcRoom.set("")

        if not self.outputDirTouched:
            self.outputDirectory.set(os.path.join(projectPath, builder.DEFAULT_OUTPUT_FOLDER))

        self.roomInfoLabel.config(
            text = str(len(roomList)) + " rooms found. Leave blank to pack every NPC spawn point in the project.")
        self.checkGroupNames()

    def checkGroupNames(self):
        # texturegroup_add raises a fatal error on a name that already exists, so
        # all three names are checked up front rather than one at a time
        prefix = self.groupPrefix.get().strip()
        clashes = [prefix + name for name in builder.DEFAULT_ATLAS_NAMES.values()
                   if prefix + name in self.textureGroupNames]

        if clashes:
            self.groupInfoLabel.config(
                text = "Already a texture group in this project: " + ", ".join(clashes),
                foreground = "#FF8080")
        else:
            self.groupInfoLabel.config(text = "Each button appends its own name, e.g. " + prefix + "actors",
                                       foreground = "gray")

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
            messagebox.showinfo("Nothing to open", "Pack an atlas first, the output folder does not exist yet")
#endregion

#region Packing
    def readOptions(self, kind):
        pageSize = int(self.pageSize.get())

        packOptions = atlas_packer.PackOptions(
            pageWidth = pageSize,
            pageHeight = pageSize,
            padding = max(0, int(self.padding.get())),
            oversizePolicy = self.oversizePolicy.get(),
            # texturegroup_add has no member for a rotated frame, and every one
            # of these atlases is destined for it
            allowRotation = False,
            groupName = self.groupPrefix.get().strip() + builder.DEFAULT_ATLAS_NAMES.get(kind, kind)
        )

        characterOptions = builder.CharacterAtlasOptions(
            kind = kind,
            roomName = self.npcRoom.get().strip() if kind == builder.KIND_NPCS else "",
            npcIncludeBodyLayers = self.npcIncludeBodyLayers.get(),
            includeItemIcons = self.includeItemIcons.get(),
            includeWrists = self.includeWrists.get(),
            includeUnattributedCreatures = self.includeUnattributedCreatures.get(),
            pageBreakPerPass = self.pageBreakPerPass.get(),
            pageBreakPerSlot = self.pageBreakPerSlot.get()
        )

        return packOptions, characterOptions

    def runPacking(self, kind):
        projectPath = self.ui.projectDirectory.get()

        if not projectPath:
            messagebox.showerror("Error", "Please select a Game Maker project directory on the Batch Assets tab")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "A pack is already running")
            return

        try:
            packOptions, characterOptions = self.readOptions(kind)
        except ValueError:
            messagebox.showerror("Error", "Page size and padding both have to be whole numbers")
            return

        rootOutput = self.outputDirectory.get() or os.path.join(projectPath, builder.DEFAULT_OUTPUT_FOLDER)
        self.outputDirectory.set(rootOutput)

        self.logText.delete("1.0", "end")
        self.setButtonsEnabled(False)

        self.worker = threading.Thread(
            target = self.packWorker,
            args = (projectPath, packOptions, characterOptions, rootOutput, self.writeDebugImages.get()),
            daemon = True
        )
        self.worker.start()
        self.root.after(100, self.drainMessageQueue)

    def packWorker(self, projectPath, packOptions, characterOptions, rootOutput, writeDebugImages):
        try:
            atlasBuilder = builder.CharacterAtlasBuilder(
                projectPath, packOptions, characterOptions,
                lambda message: self.messageQueue.put(("log", message))
            )
            outputDir = os.path.join(rootOutput, atlasBuilder.atlasName())
            result = atlasBuilder.build(outputDir, writeDebugImages)
            self.messageQueue.put(("done", result))
        except Exception as error:
            self.messageQueue.put(("error", str(error)))

    def setButtonsEnabled(self, enabled):
        for button in self.buttons:
            button.config(state = "normal" if enabled else "disabled")

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
            self.setButtonsEnabled(True)
        else:
            self.root.after(100, self.drainMessageQueue)

    def appendLog(self, message):
        self.logText.insert("end", message + "\n")
        self.logText.see("end")

    def onPackComplete(self, result):
        pageCount = len(result["pageFiles"])
        summary = ("Packed " + str(result["sheetCount"]) + " sheets onto " +
                   str(pageCount) + " texture page(s)")

        self.appendLog(summary)
        self.appendLog("Texture group name: " + result["groupName"])

        # The number the draw controller actually cares about
        for passName, pages in sorted(result["passPages"].items()):
            self.appendLog("    pass " + passName + ": " + str(len(pages)) +
                           (" bind" if len(pages) == 1 else " binds") +
                           " (page " + ", ".join(str(index) for index in pages) + ")")

        self.appendLog("Output: " + result["outputDir"])

        message = summary + "\n\nOutput folder:\n" + result["outputDir"]
        message += "\n\nPasses:"
        for passName, pages in sorted(result["passPages"].items()):
            message += "\n  " + passName + ": " + str(len(pages)) + " page(s)"

        if result["problems"]:
            message += "\n\nValidation problems: " + str(len(result["problems"]))
        if result["warnings"]:
            message += "\nWarnings: " + str(len(result["warnings"])) + " (see the pack report)"
        if result["missingSprites"]:
            message += "\nResolved but unreadable: " + str(len(result["missingSprites"]))
        if result["groupNameClash"]:
            message += ("\n\nWARNING: the texture group " + result["groupName"] +
                        " already exists in this project, texturegroup_add fails fatally on an existing group name")

        if result["problems"]:
            messagebox.showwarning("Pack Complete With Problems", message)
        else:
            messagebox.showinfo("Pack Complete", message)
#endregion
