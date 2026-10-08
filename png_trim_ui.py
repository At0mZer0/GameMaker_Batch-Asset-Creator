import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import png_trimmer


class PngTrimPanel:
    # PNG trim tab. Takes a selection of pngs from one folder and crops the
    # transparent border off each one.

    def __init__(self, parent, uiInst):
        self.parent = parent
        self.ui = uiInst
        self.root = uiInst.root

        self.files = []
        self.messageQueue = queue.Queue()
        self.worker = None

        self.outputDirectory = tk.StringVar()
        self.overwrite = tk.BooleanVar(value = False)
        self.padding = tk.StringVar(value = "0")
        self.sharedBounds = tk.BooleanVar(value = False)

        self.createWidgets()

#region UI Creation Methods
    def createWidgets(self):
        self.createFilesSection()
        self.createOutputSection()
        self.createOptionsSection()
        self.createTrimButton()
        self.createLogSection()

    def createFilesSection(self):
        filesFrame = ttk.Frame(self.parent)
        filesFrame.pack(pady = (10, 5), padx = 20, fill = "x")

        ttk.Label(filesFrame, text = "Select PNGs: ").pack(anchor = "w")

        buttonFrame = ttk.Frame(filesFrame)
        buttonFrame.pack(fill = "x", pady = 5)

        ttk.Button(buttonFrame, text = "Browse", command = self.selectFiles).pack(side = "left")
        ttk.Button(buttonFrame, text = "Clear", command = self.clearFiles).pack(side = "left", padx = (5, 0))

        listFrame = ttk.Frame(filesFrame)
        listFrame.pack(fill = "x")

        self.fileList = tk.Listbox(listFrame, height = 8, bg = "#404040", fg = "#B8C5D1",
                                   selectbackground = "#2b2b2b", highlightthickness = 0, borderwidth = 0)
        self.fileList.pack(side = "left", fill = "x", expand = True)

        scrollbar = ttk.Scrollbar(listFrame, orient = "vertical", command = self.fileList.yview)
        scrollbar.pack(side = "right", fill = "y")
        self.fileList.config(yscrollcommand = scrollbar.set)

        self.filesInfoLabel = ttk.Label(filesFrame, text = "Ctrl or Shift click to pick several files",
                                        font = ("Arial", 8), foreground = "gray")
        self.filesInfoLabel.pack(anchor = "w")

    def createOutputSection(self):
        outputFrame = ttk.Frame(self.parent)
        outputFrame.pack(pady = 5, padx = 20, fill = "x")

        ttk.Label(outputFrame, text = "Output Folder: ").pack(anchor = "w")

        outputSelectFrame = ttk.Frame(outputFrame)
        outputSelectFrame.pack(fill = "x", pady = 5)

        self.outputEntry = ttk.Entry(outputSelectFrame, textvariable = self.outputDirectory)
        self.outputEntry.pack(side = "left", fill = "x", expand = True)

        self.outputBrowseButton = ttk.Button(outputSelectFrame, text = "Browse", command = self.selectOutputDirectory)
        self.outputBrowseButton.pack(side = "right", padx = (5, 0))

        ttk.Checkbutton(outputFrame, text = "Overwrite the original files", variable = self.overwrite,
                        command = self.onOverwriteChanged).pack(anchor = "w")

    def createOptionsSection(self):
        optionsFrame = ttk.Frame(self.parent)
        optionsFrame.pack(pady = 5, padx = 20, fill = "x")

        paddingFrame = ttk.Frame(optionsFrame)
        paddingFrame.pack(fill = "x")

        ttk.Label(paddingFrame, text = "Padding (px): ").pack(side = "left")
        ttk.Entry(paddingFrame, textvariable = self.padding, width = 6).pack(side = "left")

        ttk.Checkbutton(optionsFrame, text = "Use one shared trim box for all files", variable = self.sharedBounds).pack(anchor = "w", pady = (5, 0))

        helpLabel = ttk.Label(optionsFrame, text = "Keeps animation frames lined up with each other",
                              font = ("Arial", 8), foreground = "gray")
        helpLabel.pack(anchor = "w")

    def createTrimButton(self):
        buttonFrame = ttk.Frame(self.parent)
        buttonFrame.pack(pady = 10)

        self.trimButton = ttk.Button(buttonFrame, text = "Trim PNGs", command = self.runTrim)
        self.trimButton.pack(side = "left", padx = (0, 5))

        ttk.Button(buttonFrame, text = "Open Output Folder", command = self.openOutputFolder).pack(side = "left")

    def createLogSection(self):
        logFrame = ttk.Frame(self.parent)
        logFrame.pack(pady = (0, 10), padx = 20, fill = "both", expand = True)

        self.logText = tk.Text(logFrame, height = 10, bg = "#404040", fg = "#B8C5D1",
                               insertbackground = "#B8C5D1", borderwidth = 0, wrap = "word")
        self.logText.pack(side = "left", fill = "both", expand = True)

        scrollbar = ttk.Scrollbar(logFrame, orient = "vertical", command = self.logText.yview)
        scrollbar.pack(side = "right", fill = "y")
        self.logText.config(yscrollcommand = scrollbar.set)
#endregion

#region Handlers
    def selectFiles(self):
        paths = filedialog.askopenfilenames(title = "Select PNGs to Trim", filetypes = [("PNG images", "*.png")])
        if not paths:
            return

        self.files = list(paths)
        self.fileList.delete(0, "end")
        for path in self.files:
            self.fileList.insert("end", os.path.basename(path))

        self.filesInfoLabel.config(text = str(len(self.files)) + " files selected")

        if not self.outputDirectory.get():
            self.outputDirectory.set(os.path.join(os.path.dirname(self.files[0]), "trimmed"))

    def clearFiles(self):
        self.files = []
        self.fileList.delete(0, "end")
        self.filesInfoLabel.config(text = "Ctrl or Shift click to pick several files")

    def selectOutputDirectory(self):
        directory = filedialog.askdirectory(title = "Select Trim Output Directory")
        if directory:
            self.outputDirectory.set(directory)

    def onOverwriteChanged(self):
        state = "disabled" if self.overwrite.get() else "normal"
        self.outputEntry.config(state = state)
        self.outputBrowseButton.config(state = state)

    def openOutputFolder(self):
        if self.overwrite.get() and self.files:
            outputPath = os.path.dirname(self.files[0])
        else:
            outputPath = self.outputDirectory.get()

        if outputPath and os.path.isdir(outputPath):
            os.startfile(outputPath)
        else:
            messagebox.showinfo("Nothing to open", "Trim some files first, the output folder does not exist yet")
#endregion

#region Trimming
    def runTrim(self):
        if not self.files:
            messagebox.showerror("Error", "Please select the PNGs to trim")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "A trim is already running")
            return

        try:
            padding = max(0, int(self.padding.get()))
        except ValueError:
            messagebox.showerror("Error", "Padding has to be a whole number")
            return

        if self.overwrite.get():
            outputDir = None
            if not messagebox.askyesno("Overwrite Originals",
                                       "This replaces " + str(len(self.files)) + " original files with the trimmed versions. Continue?"):
                return
        else:
            outputDir = self.outputDirectory.get().strip()
            if not outputDir:
                messagebox.showerror("Error", "Please select an output folder or tick Overwrite the original files")
                return

        self.logText.delete("1.0", "end")
        self.trimButton.config(state = "disabled")

        self.worker = threading.Thread(
            target = self.trimWorker,
            args = (list(self.files), outputDir, padding, self.sharedBounds.get()),
            daemon = True
        )
        self.worker.start()
        self.root.after(100, self.drainMessageQueue)

    def trimWorker(self, paths, outputDir, padding, sharedBounds):
        try:
            result = png_trimmer.trimFiles(paths, outputDir, padding, sharedBounds,
                                           lambda message: self.messageQueue.put(("log", message)))
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
                self.onTrimComplete(payload)
                finished = True
            elif kind == "error":
                self.appendLog("Failed: " + payload)
                messagebox.showerror("Trim Failed", payload)
                finished = True

        if finished:
            self.trimButton.config(state = "normal")
        else:
            self.root.after(100, self.drainMessageQueue)

    def appendLog(self, message):
        self.logText.insert("end", message + "\n")
        self.logText.see("end")

    def onTrimComplete(self, result):
        summary = ("Trimmed " + str(len(result["trimmed"])) + ", nothing to trim " + str(len(result["unchanged"])) +
                   ", fully transparent " + str(len(result["empty"])) + ", failed " + str(len(result["failed"])))
        self.appendLog(summary)

        if result["failed"]:
            messagebox.showwarning("Trim Complete With Errors", summary)
        else:
            messagebox.showinfo("Trim Complete", summary)
#endregion
