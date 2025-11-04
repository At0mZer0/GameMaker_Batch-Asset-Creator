import json5
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time

class AsyncJsonLoader:

    def __init__(self, parentWindow):
        self.parentWindow = parentWindow
        self.progressWindow = None
        self.qtyProgress = None
        self.progressBar = None
        self.statusLabel = None
        self.cancelled = False

    def loadJson5WithProgress(self, filePath, callback, errorCallback, progressCallback = None, processFolders = True):
        self.progressCallback = progressCallback
        self.processFolders = processFolders
        self.showProgressDialog()

        thread = threading.Thread(target = self.loadJson5Worker, args = (filePath, callback, errorCallback), daemon = True)
        thread.start()

    def showProgressDialog(self):
        # Create and show the progress dialog
        self.progressWindow = tk.Toplevel(self.parentWindow)
        self.progressWindow.title("Loading...")
        self.progressWindow.geometry("400x250")
        self.progressWindow.resizable(False, False)

        # Center the dialog
        self.progressWindow.transient(self.parentWindow) ## makes child of the parent window
        self.progressWindow.grab_set() # makes sure that any user input is directed to this window before they can interact with the main window

        # Create the progress bar
        frame = ttk.Frame(self.progressWindow)
        frame.pack(expand = True, fill = 'both', padx = 20, pady = 20)

        self.statusLabel = ttk.Label(frame, text = "Reading file...")
        self.statusLabel.pack(pady = (0, 10))

        self.qtyProgress = tk.DoubleVar()
        self.progressBar = ttk.Progressbar(frame, variable = self.qtyProgress, maximum = 100, mode = 'determinate')
        self.progressBar.pack(fill = 'x', pady = (0, 10))
        self.qtyProgress.set(0) # Animate the progress bar

        self.counterLabel = ttk.Label(frame, text = "")
        self.counterLabel.pack(pady = (5, 10))

        # Cancel butt
        cancelBtn = ttk.Button(frame, text = "Cancel", command = self.cancelLoading)
        cancelBtn.pack()

        self.cancelled = False

        self.keepDialogResponsive()

    def keepDialogResponsive(self):
        if self.progressWindow and not self.cancelled:
            self.progressWindow.update_idletasks() # Process pending GUI events
            self.parentWindow.after(50, self.keepDialogResponsive) # Check again in 50ms

    def cancelLoading(self):
        self.cancelled = True
        self.hideProgressDialog()

    def hideProgressDialog(self):
        if self.progressWindow:
            self.progressWindow.destroy()
            self.progressWindow = None
    
    def updateProgress(self, message, progress = None, counter = None, mode = None):
        if self.progressWindow and not self.cancelled:
            # Schedule UI update on main thread
            self.parentWindow.after(0, self.updateProgressUI, message, progress, counter, mode)
    
    def updateProgressUI(self, message, progress, counter, mode = None): 
        if self.statusLabel:
            self.statusLabel.config(text = message)
        if mode == "indeterminate":
            if self.progressBar:
                self.progressBar.config(mode = "indeterminate")
                self.progressBar.start(10)

        elif progress is not None and self.progressBar:
            self.progressBar.stop()
            self.progressBar.config(mode = 'determinate')
            self.qtyProgress.set(progress)
        
        if counter and self.counterLabel:
            self.counterLabel.config(text = counter)
    
    def loadJson5Worker(self, filePath, callback, errorCallback):
        try:
            if self.cancelled:
                return
            # Update Status - 10% progress for starting
            self.updateProgress("Reading file...", mode = "indeterminate")

            # Read File Content
            with open(filePath, 'r', encoding = 'utf-8') as file:
                content = file.read()
            
            if self.cancelled:
                return
            
            fileSize = len(content)
            self.updateProgress(f"Parsing JSON5 ({fileSize:,} characters)...")

            self.updateProgress(f"Parsing JSON5...")
            startTime = time.time()

            # Parse in chunks to allow progress updates
            result = json5.loads(content)

            if self.cancelled:
                return
            
            elapsed = time.time() - startTime
            self.updateProgress(f"Parsing complete ({elapsed: .1f}s)")
            time.sleep(0.5) 

            if 'Folders' in result:
                # Phase 2: Folder processing (0 - 100) Background thread
                self.processFoldersInBackground(result, callback, errorCallback)
            else:
                # Normal completion for non folder files
                self.parentWindow.after(0, self.onSuccess, result, callback)
    
        except Exception as e:
            if not self.cancelled:
                self.parentWindow.after(0, self.onError, str(e), errorCallback)

    def processFoldersInBackground(self, projectData, callback, errorCallback):
        # Process folders in background thread to avoid UI blocking/ provides realtime progress updates for each folder processed
        try:
            if self.cancelled:
                return
            
            folderPaths = []
            totalFolders = 0

            if 'Folders' in projectData:
                totalFolders = len(projectData['Folders'])

                # Start folder processing phase
                self.updateProgress("Starting folder processing...", 0, f"0 / {totalFolders}")
                time.sleep(0.2)

                # Process each folder
                for i, folder in enumerate(projectData['Folders']):
                    if self.cancelled:
                        return
                    
                    if 'folderPath' in folder:
                        folderPaths.append(folder['folderPath'])
                    else:
                        print(f"No folderPath key in folder {i}")
                    
                    # Update progress for each folder
                    progress = ((i + 1) / totalFolders) * 100
                    counter = f"{i + 1} / {totalFolders}"
                    folderName = folder.get('folderPath', 'Unknown')
                    self.updateProgress(f"Processing: {folderName}", progress, counter)

                    time.sleep(0.01)
            else:
                print( "No folders key found in project")
            
            # Final Completion
            self.updateProgress("Folder processing complete!", 100, f"{totalFolders} / {totalFolders} folders")
            time.sleep(0.5)

            result = {
                'projectData' : projectData, 
                'folderPaths' : folderPaths
            }

            self.parentWindow.after(0, self.onSuccess, result, callback)

        except Exception as e:
            if not self.cancelled:
                self.parentWindow.after(0, self.onError, str(e), errorCallback)

    
    def onSuccess(self, result, callback):
        # self.hideProgressDialog()
        if callback:
            callback(result)
    
    def onError(self, errorMessage, errorCallback):
        self.hideProgressDialog()
        if errorCallback:
            errorCallback(errorMessage)
        else:
            messagebox.showerror("Error", f"Failed to load JSON5 file: {errorMessage}")
