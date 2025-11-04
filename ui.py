import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
from asset_types import ASSET
from async_json_loader import AsyncJsonLoader
from asset_creator import AssetCreator

class AutoObjectCreatorUI:
    # Pass in the root widget for the app in the main() need to create an instance of Tk()
    def __init__(self, root):
        self.root = root
        self.root.title("GMS2 Object and Sprite Batch Asset Creator")
        self.root.geometry("600x800")

        # Set Dark theme
        try:
            self.root.tk.call("source", "azure.tcl")
            self.root.tk.call("set_theme", "dark")
        except:
            self.setupDarkTheme()

        # String variables that work with tkinter Widgets
        self.spriteDirectory = tk.StringVar()
        self.projectDirectory = tk.StringVar()
        self.folderPaths = []
        self.yypFilePath = None
        self.selectedAssetFolder = tk.StringVar()
        self.selectedSpriteFolder = tk.StringVar()
        self.selectedOrigin = tk.StringVar()
        self.parentObjectName = tk.StringVar()
        self.spriteTags = tk.StringVar()

        # Add JSON Loader
        self.jsonLoader = AsyncJsonLoader(self.root)

        self.createWidgets()


    def createWidgets(self):
        self.createTitleSection()
        self.createSpritesSection()
        self.createProjectSection()
        self.createReplaceSection()
        self.createOriginSection()
        self.createParentObjectSection()
        self.createTagsSection()
        self.createObjectButton()


# region UI Creation Methods
    def createTitleSection(self):
        # Title Label
        titleLabel = ttk.Label(self.root, text = "GMS2 Object and Sprite Batch Asset Creator", font = ("Arial", 16, "bold"))
        titleLabel.pack(pady = 10)


    # Sprites Directory selection
    def createSpritesSection(self):
        spritesFrame = ttk.Frame(self.root)
        spritesFrame.pack(pady = 10, padx = 20, fill = "x")

        ttk.Label(spritesFrame, text = "Select Sprites Directory:").pack(anchor = "w")

        spriteSelectFrame = ttk.Frame(spritesFrame)
        spriteSelectFrame.pack(fill = "x", pady = 5)

        self.spritesEntry = ttk.Entry(spriteSelectFrame, textvariable = self.spriteDirectory, state = "readonly")
        self.spritesEntry.pack(side = "left", fill = "x", expand = True)

        ttk.Button(spriteSelectFrame, text = "Browse", command = self.selectSpritesDirectory).pack(side = "right", padx = (5, 0))


    # Project Directory selection
    def createProjectSection(self):
        projectFrame = ttk.Frame(self.root) 
        projectFrame.pack(pady = 10, padx = 20, fill = "x")

        ttk.Label(projectFrame, text = "Select Game Maker Project Directory:").pack(anchor = "w")

        projectSelectFrame = ttk.Frame(projectFrame)
        projectSelectFrame.pack(fill = "x", pady = 5)

        self.projectEntry = ttk.Entry(projectSelectFrame, textvariable = self.projectDirectory, state = "readonly")
        self.projectEntry.pack(side = "left", fill = "x", expand = True)

        ttk.Button(projectSelectFrame, text = "Browse", command = self.selectProjectDirectory).pack(side = "right", padx = (5, 0))

        # Object Folder Path selection dropdown
        ttk.Label(projectFrame, text = "Select Object Target Folder: ").pack(anchor = "w", pady = (10, 0))
        self.folderCombobox = ttk.Combobox(projectFrame, state = "readonly", textvariable = self.selectedAssetFolder)
        self.folderCombobox.pack(fill = "x", pady = 5)

        # Object Folder Path selection dropdown
        ttk.Label(projectFrame, text = "Select Sprite Target Folder: ").pack(anchor = "w", pady = (10, 0))
        self.spriteFolderCombobox = ttk.Combobox(projectFrame, state = "readonly", textvariable = self.selectedSpriteFolder)
        self.spriteFolderCombobox.pack(fill = "x", pady = 5)




    def createReplaceSection(self):
        replaceFrame = ttk.Frame(self.root)
        replaceFrame.pack(pady = 10, padx = 20, fill = "x")

        # Text to replace
        ttk.Label(replaceFrame, text = "Sprite Name Prefix: ").pack(anchor = "w")
        self.textToReplace = ttk.Entry(replaceFrame)
        self.textToReplace.pack(fill = "x", pady = (0, 10))
        self.textToReplace.insert(0, "spr") # default value

        # Replacement text
        ttk.Label(replaceFrame, text = "Object Name Prefix: ").pack(anchor = "w")
        self.replaceText = ttk.Entry(replaceFrame)
        self.replaceText.pack(fill = "x", pady = (0, 10))
        self.replaceText.insert(0, "obj")

    def createOriginSection(self):
        originFrame = ttk.Frame(self.root)
        originFrame.pack(pady = 10, padx = 20, fill = "x")

        # Origin selection
        ttk.Label(originFrame, text = "Sprite Origin: ").pack(anchor = "w")

        originOptions = [
            "Top Left",
            "Top Center",
            "Top Right",
            "Middle Left",
            "Middle Center",
            "Middle Right",
            "Bottom Left",
            "Bottom Center",
            "Bottom Right"
        ]

        self.originCombobox = ttk.Combobox(originFrame, state = "readonly", textvariable = self.selectedOrigin, values = originOptions)
        self.originCombobox.pack(fill = "x", pady = 5)
        self.originCombobox.current(0)
        self.selectedOrigin.set("Top Left")

    def createParentObjectSection(self):
        parentFrame = ttk.Frame(self.root)
        parentFrame.pack(pady = 10, padx = 20, fill = "x")

        # Parent Object section
        ttk.Label(parentFrame, text = "Parent Object Name: ").pack(anchor = "w")
        self.parentObjectEntry = ttk.Entry(parentFrame, textvariable = self.parentObjectName)
        self.parentObjectEntry.pack(fill = "x", pady= 5)

        # Add small help label
        helpLabel = ttk.Label(parentFrame, text = "Leave empty for no parent object", font = ("Arial", 8), foreground = "gray")
        helpLabel.pack(anchor = "w")

    def createTagsSection(self):
        tagsFrame = ttk.Frame(self.root)
        tagsFrame.pack(pady = 10, padx = 20, fill = "x")

        # Tags section
        ttk.Label(tagsFrame, text = "Sprite Tags (comma separated): ").pack(anchor = "w")
        self.tagsEntry = ttk.Entry(tagsFrame, textvariable = self.spriteTags)
        self.tagsEntry.pack(fill = "x", pady = 5)

        # Help label
        helpLabel = ttk.Label(tagsFrame, text = "Example: enemy, boss, animated", font = ("Arial", 8), foreground = "gray")
        helpLabel.pack(anchor = "w")

    def createObjectButton(self):
        buttonFrame = ttk.Frame(self.root)
        buttonFrame.pack(pady = 20)

        ttk.Button(self.root, text = "Create Objects", command = self.runObjectCreation).pack(side = "left", padx = (0, 5))
        ttk.Button(self.root, text = "Create Sprites", command = self.runSpriteCreation).pack(side = "left", padx = (0, 5))
        ttk.Button(self.root, text = "Create Both", command = self.runSpriteAndObjectCreation).pack(side = "left")

    # Method for button handler to select sprites directory
    def selectSpritesDirectory(self):
        # Opens file dialog to select sprites directory
        directory = filedialog.askdirectory(title = "Select Sprites Directory")
        if directory:
            self.spriteDirectory.set(directory)

    def resetProjectState(self):
        self.folderPaths = []
        self.selectedAssetFolder.set("")
        self.selectedSpriteFolder.set("")
        self.folderCombobox['values'] = []
        self.yypFilePath = None

    # Method for button handler to select Game Maker Project directory
    def selectProjectDirectory(self):
        directory = filedialog.askdirectory(title = "Select Game Maker Project Directory")
        if directory:
            self.resetProjectState()
            self.projectDirectory.set(directory)
            self.updateFolderDropdown()

    def updateFolderDropdown(self):
        projectPath = self.projectDirectory.get()
        if not projectPath:
            return
        
        self.yypFilePath = self.getYYPfilePath(projectPath)
        if self.yypFilePath:
            self.getProjectFolderPaths(self.yypFilePath)



    # Get the YYP file path from the selected project directory
    def getYYPfilePath(self, projectPath):
        yypFile = [filename for filename in os.listdir(projectPath) if filename.endswith('.yyp')]

        if not yypFile:
           return None

        yypFilePath = os.path.join(projectPath, yypFile[0])
        return yypFilePath

    # Opens .yyp loads it and get's folder array and stores all folder paths in list
    def getProjectFolderPaths(self, yypFilePath):

        # Modified for Async loading
        def onProjectLoaded(result):
            try:
                if isinstance(result, dict) and 'folderPaths' in result:
                    folderPaths = result['folderPaths']
                else:
                    print("No Folders key found in projectData")
                    folderPaths = []
                self.folderPaths = folderPaths
                self.folderCombobox['values'] = self.folderPaths
                self.spriteFolderCombobox['values'] = self.folderPaths
                if self.folderPaths:
                    self.folderCombobox.current(0)
                    self.selectedAssetFolder.set(self.folderPaths[0])
                    self.spriteFolderCombobox.current(0)
                    self.selectedSpriteFolder.set(self.folderPaths[0])

                self.jsonLoader.hideProgressDialog()
            except Exception as e:
                print(f"Error processing folder data {e}")
                self.folderPaths = []
                self.jsonLoader.hideProgressDialog()

        def onError(errorMessage):
            print(f"Error loading project folders: {errorMessage}")
            self.folderPaths = []

        # load asynchronously
        self.jsonLoader.loadJson5WithProgress(yypFilePath, onProjectLoaded, onError)

    # Asset creator getter for selected folder
    def getSelectedFolderPath(self):
        return self.folderCombobox.get()

    # Called on button press and checks all entries for errors
    def runObjectCreation(self):       
        # Get values from entries
        spritesPath = self.spriteDirectory.get()
        projectPath = self.projectDirectory.get()
        textFrom = self.textToReplace.get()
        textTo = self.replaceText.get()

        # You got errors?? We got MASSAGES!
        if not spritesPath:
            messagebox.showerror("Error", "Please select a sprites directory")
            return
        if not projectPath:
            messagebox.showerror("Error", "Please select a Game Maker project directory")
            return
        if not textFrom:
            messagebox.showerror("Error", "Please enter text to replace")
            return
        if not textTo:
            messagebox.showerror("Error", "Please enter replacement text")
            return

        messagebox.showinfo("Successssssss", 
                            f"Ready to Create Objects\n"
                            f"Sprites: {spritesPath}\n"
                            f"Project: {projectPath}\n"
                            f"Replace '{textFrom}' with '{textTo}'")
        
        assetCreator = AssetCreator(self)
        assetCreator.createAssets(ASSET.OBJECT)

    # Called on button press and checks all entries for errors
    def runSpriteCreation(self):       
        # Get values from entries
        spritesPath = self.spriteDirectory.get()
        projectPath = self.projectDirectory.get()

        # You got errors?? We got MASSAGES!
        if not spritesPath:
            messagebox.showerror("Error", "Please select a sprites directory")
            return
        if not projectPath:
            messagebox.showerror("Error", "Please select a Game Maker project directory")
            return

        messagebox.showinfo("Successssssss", 
                            f"Ready to Create Sprites\n"
                            f"Sprites: {spritesPath}\n"
                            f"Project: {projectPath}\n"
        )
        assetCreator = AssetCreator(self)
        assetCreator.createAssets(ASSET.SPRITE)

    # Called on button press and checks all entries for errors
    def runSpriteAndObjectCreation(self):       
        # Get values from entries
        spritesPath = self.spriteDirectory.get()
        projectPath = self.projectDirectory.get()
        textFrom = self.textToReplace.get()
        textTo = self.replaceText.get()

        # You got errors?? We got MASSAGES!
        if not spritesPath:
            messagebox.showerror("Error", "Please select a sprites directory")
            return
        if not projectPath:
            messagebox.showerror("Error", "Please select a Game Maker project directory")
            return
        if not textFrom:
            messagebox.showerror("Error", "Please enter text to replace")
            return
        if not textTo:
            messagebox.showerror("Error", "Please enter replacement text")
            return

        messagebox.showinfo("Successssssss", 
                            f"Ready to Create Objects\n"
                            f"Sprites: {spritesPath}\n"
                            f"Project: {projectPath}\n"
                            f"Replace '{textFrom}' with '{textTo}'")
        
        assetCreator = AssetCreator(self)
        assetCreator.createAssets(ASSET.BOTH)

    def setupDarkTheme(self):
        bgColor = "#2b2b2b"
        fgColor = "#B8C5D1"
        selectBg = "#404040"

        self.root.configure(bg = bgColor)

        # Set default style
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('TLabel', background = bgColor, foreground = fgColor)
        style.configure('TFrame', background = bgColor, foreground = fgColor)
        style.configure('TButton', background = bgColor, foreground = fgColor)
        style.map('TButton', background = [('active', '#505050')])
        style.configure('TEntry', fieldbackground = selectBg, foreground = fgColor, bordercolor = bgColor)
        style.configure('TCombobox', fieldbackground = selectBg, foreground = fgColor, bordercolor = bgColor)

        style.map('TCombobox', 
            fieldbackground = [('readonly', bgColor)],
            selectbackground = [('readonly', bgColor)],
            selectforeground = [('readonly', fgColor)])
        
        # Style the progress bar to keep it green
        style.configure('TProgressbar', 
            background='#00FF00',  # Green progress bar
            troughcolor=bgColor,   # Dark background trough
            borderwidth=1, 
            lightcolor='#00FF00', 
            darkcolor='#00CC00')
    
        # Style the dropdown listbox (the popup part)
        self.root.option_add('*TCombobox*Listbox.Background', '#404040')
        self.root.option_add('*TCombobox*Listbox.Foreground', fgColor)
        self.root.option_add('*TCombobox*Listbox.selectBackground',bgColor)
        self.root.option_add('*TCombobox*Listbox.selectForeground', fgColor)
#endregion