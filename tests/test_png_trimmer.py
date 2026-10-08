import os
import shutil
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import png_trimmer


def makePng(path, size, box, mode = "RGBA"):
    # Transparent canvas with an opaque red rectangle covering box
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), box)
    if mode == "P":
        image = image.convert("P")
        image.info["transparency"] = image.getpixel((0, 0))
    image.save(path)


class TestPngTrimmer(unittest.TestCase):

    def setUp(self):
        self.sourceDir = tempfile.mkdtemp()
        self.outputDir = os.path.join(self.sourceDir, "trimmed")

    def tearDown(self):
        shutil.rmtree(self.sourceDir, ignore_errors = True)

    def path(self, name):
        return os.path.join(self.sourceDir, name)

    def sizeOf(self, path):
        with Image.open(path) as image:
            return image.size

    def test_trims_to_opaque_pixels(self):
        makePng(self.path("a.png"), (64, 64), (10, 20, 30, 50))
        result = png_trimmer.trimFiles([self.path("a.png")], self.outputDir, log = lambda m: None)

        self.assertEqual(result["trimmed"], [self.path("a.png")])
        self.assertEqual(self.sizeOf(os.path.join(self.outputDir, "a.png")), (20, 30))
        self.assertEqual(self.sizeOf(self.path("a.png")), (64, 64))

    def test_padding_is_clamped_to_canvas(self):
        makePng(self.path("a.png"), (64, 64), (2, 20, 30, 50))
        png_trimmer.trimFiles([self.path("a.png")], self.outputDir, padding = 4, log = lambda m: None)

        self.assertEqual(self.sizeOf(os.path.join(self.outputDir, "a.png")), (34, 38))

    def test_shared_bounds_gives_every_file_the_same_size(self):
        makePng(self.path("f0.png"), (64, 64), (10, 10, 20, 20))
        makePng(self.path("f1.png"), (64, 64), (30, 40, 50, 60))
        png_trimmer.trimFiles([self.path("f0.png"), self.path("f1.png")], self.outputDir,
                              sharedBounds = True, log = lambda m: None)

        self.assertEqual(self.sizeOf(os.path.join(self.outputDir, "f0.png")), (40, 50))
        self.assertEqual(self.sizeOf(os.path.join(self.outputDir, "f1.png")), (40, 50))

    def test_fully_transparent_file_is_skipped(self):
        Image.new("RGBA", (16, 16), (0, 0, 0, 0)).save(self.path("empty.png"))
        result = png_trimmer.trimFiles([self.path("empty.png")], self.outputDir, log = lambda m: None)

        self.assertEqual(result["empty"], [self.path("empty.png")])
        self.assertFalse(os.path.exists(os.path.join(self.outputDir, "empty.png")))

    def test_no_transparency_is_copied_unchanged(self):
        Image.new("RGB", (16, 16), (255, 0, 0)).save(self.path("solid.png"))
        result = png_trimmer.trimFiles([self.path("solid.png")], self.outputDir, log = lambda m: None)

        self.assertEqual(result["unchanged"], [self.path("solid.png")])
        self.assertEqual(self.sizeOf(os.path.join(self.outputDir, "solid.png")), (16, 16))

    def test_overwrite_in_place(self):
        makePng(self.path("a.png"), (64, 64), (10, 20, 30, 50))
        png_trimmer.trimFiles([self.path("a.png")], None, log = lambda m: None)

        self.assertEqual(self.sizeOf(self.path("a.png")), (20, 30))

    def test_indexed_png_keeps_palette_mode(self):
        makePng(self.path("p.png"), (32, 32), (4, 4, 12, 20), mode = "P")
        png_trimmer.trimFiles([self.path("p.png")], self.outputDir, log = lambda m: None)

        with Image.open(os.path.join(self.outputDir, "p.png")) as image:
            self.assertEqual(image.mode, "P")
            self.assertEqual(image.size, (8, 16))

    def test_unreadable_file_is_reported(self):
        with open(self.path("bad.png"), "w") as handle:
            handle.write("not a png")
        result = png_trimmer.trimFiles([self.path("bad.png")], self.outputDir, log = lambda m: None)

        self.assertEqual(len(result["failed"]), 1)


if __name__ == "__main__":
    unittest.main()
