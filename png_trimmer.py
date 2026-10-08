import os

from PIL import Image


def alphaBounds(image):
    # Box of the non transparent pixels as (left, top, right, bottom), or None
    # when every pixel is transparent. Images with no transparency return the
    # full canvas.
    if image.mode == "RGBA":
        return image.getchannel("A").getbbox()

    if image.mode in ("LA", "PA") or "transparency" in image.info:
        return image.convert("RGBA").getchannel("A").getbbox()

    return (0, 0, image.width, image.height)


def unionBounds(boxes):
    boxes = [box for box in boxes if box]
    if not boxes:
        return None

    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes)
    )


def padBounds(box, padding, width, height):
    # Grows the box by padding on every side without leaving the canvas
    return (
        max(0, box[0] - padding),
        max(0, box[1] - padding),
        min(width, box[2] + padding),
        min(height, box[3] + padding)
    )


def outputPathFor(sourcePath, outputDir):
    if not outputDir:
        return sourcePath
    return os.path.join(outputDir, os.path.basename(sourcePath))


def trimFiles(paths, outputDir = None, padding = 0, sharedBounds = False, log = print):
    # Trims the transparent border off each png.
    #   outputDir    None overwrites the source files in place.
    #   padding      transparent pixels kept around the trimmed box.
    #   sharedBounds one box covering every image is used for all of them, so
    #                animation frames stay lined up with each other.
    # Returns a dict with the lists trimmed, unchanged, empty and failed.
    result = {"trimmed": [], "unchanged": [], "empty": [], "failed": []}

    if outputDir:
        os.makedirs(outputDir, exist_ok = True)

    bounds = {}
    for path in paths:
        try:
            with Image.open(path) as image:
                bounds[path] = (alphaBounds(image), image.width, image.height)
        except Exception as error:
            result["failed"].append((path, str(error)))
            log("Failed: " + os.path.basename(path) + " - " + str(error))

    shared = None
    if sharedBounds:
        shared = unionBounds([box for box, width, height in bounds.values()])
        if shared:
            log("Shared bounds: " + str(shared))

    for path in paths:
        if path not in bounds:
            continue

        name = os.path.basename(path)
        box, width, height = bounds[path]

        if box is None:
            result["empty"].append(path)
            log("Skipped (fully transparent): " + name)
            continue

        if shared:
            box = shared
        box = padBounds(box, padding, width, height)
        destination = outputPathFor(path, outputDir)

        try:
            with Image.open(path) as image:
                image.load()
                if box == (0, 0, width, height):
                    if destination != path:
                        image.save(destination)
                    result["unchanged"].append(path)
                    log("Nothing to trim: " + name)
                    continue

                trimmed = image.crop(box)
                trimmed.save(destination)
        except Exception as error:
            result["failed"].append((path, str(error)))
            log("Failed: " + name + " - " + str(error))
            continue

        result["trimmed"].append(path)
        log(name + ": " + str(width) + "x" + str(height) + " -> " +
            str(box[2] - box[0]) + "x" + str(box[3] - box[1]) +
            " (offset " + str(box[0]) + ", " + str(box[1]) + ")")

    return result
