"""Exact rendering and provenance on synthetic coloured pages."""

import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pymupdf as fitz
from pdf_fixtures import IsolatedTestCase, build_coloured_pages

from reviewer_mcp import crops
from reviewer_mcp.store import fingerprint


class TestCrops(IsolatedTestCase):
    def test_full_pages_and_selected_content_with_rotation_and_cropbox(self):
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        for cropped in (False, True):
            width, height = (200, 120) if cropped else (300, 240)
            for rotation in (0, 90, 180, 270):
                with self.subTest(cropped=cropped, rotation=rotation):
                    pdf = build_coloured_pages(self.tmp_path / f"{cropped}-{rotation}.pdf", rotation, cropped)
                    full = fitz.Pixmap(crops.crop_png(pdf, 1, None, width))
                    self.assertEqual((full.width, full.height),
                                     (height, width) if rotation % 180 else (width, height))
                    with fitz.open(pdf) as doc:
                        matrix = doc[0].rotation_matrix
                        for index, (x, y) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                            centre = fitz.Point((x + .5) * width / 2, (y + .5) * height / 2) * matrix
                            self.assertEqual(full.pixel(int(centre.x), int(centre.y)), colors[index])
                    # Asymmetric interior rectangle: never include another quadrant or a page margin.
                    bbox = (10., 8., width / 2 - 10, height / 2 - 8)
                    image = fitz.Pixmap(crops.crop_png(pdf, 1, bbox, 160))
                    self.assertEqual(max(image.width, image.height), 160)
                    self.assertEqual(image.width > image.height, rotation % 180 == 0)
                    for x, y in ((1, 1), (image.width // 2, image.height // 2), (image.width - 2, image.height - 2)):
                        self.assertEqual(image.pixel(x, y), colors[0])
                    info = crops.describe_region(pdf, 1, bbox)
                    self.assertEqual(info["requested_bounds"], list(bbox))
                    self.assertEqual(info["effective_bounds"], list(bbox))
                    self.assertFalse(info["clipped"])
                    self.assertEqual(info["geometry"]["rotation"], rotation)

    def test_clipping_and_invalid_regions(self):
        pdf = build_coloured_pages(self.tmp_path / "clip.pdf", 90, True)
        bbox = (-10., -5., 80., 40.)
        info = crops.describe_region(pdf, 1, bbox)
        self.assertTrue(info["clipped"])
        self.assertEqual(info["effective_bounds"], [0, 0, 80, 40])
        pix = fitz.Pixmap(crops.crop_png(pdf, 1, bbox, 160))
        self.assertEqual((pix.width, pix.height), (80, 160))
        self.assertEqual(pix.pixel(40, 80), (255, 0, 0))
        for invalid in ((210, 0, 220, 10), (20, 20, 10, 30), (10, 10, 10, 20),
                        (0, float("inf"), 10, 20), (0, 0, float("nan"), 20)):
            with self.subTest(bounds=invalid):
                info = crops.describe_region(pdf, 1, invalid)
                self.assertFalse(info["available"])
                self.assertIsNone(info["effective_bounds"])
                self.assertTrue(info["reason"])
                with self.assertRaises(ValueError):
                    crops.crop_png(pdf, 1, invalid, 160)

    def test_invalid_pages_and_size(self):
        pdf = build_coloured_pages(self.tmp_path / "page.pdf")
        for page in (0, -1, 2, True, 1.5):
            with self.assertRaisesRegex(ValueError, "Page must"):
                crops.crop_png(pdf, page, None, 100)
        for size in (0, -1, True, float("inf"), 1.5):
            with self.assertRaisesRegex(ValueError, "max_side"):
                crops.crop_png(pdf, 1, None, size)


class TestImageCache(IsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.pdf = build_coloured_pages(self.tmp_path / "colors.pdf", 90, True)
        self.run_dir = self.tmp_path / "run"

    def render(self, *, bbox=None, size=200, pdf=None, run_dir=None, asset_id="page:1", region=None):
        pdf = pdf or self.pdf
        return crops.cached_png(
            pdf, 1, bbox, size, run_dir=run_dir or self.run_dir,
            document_id=fingerprint(pdf), asset_id=asset_id,
            region=region or crops.describe_region(pdf, 1, bbox),
        )

    def slot(self):
        files = list(self.run_dir.rglob("*.png"))
        self.assertEqual(len(files), 1)
        return files[0]

    def test_repeated_and_concurrent_requests_render_once(self):
        with mock.patch.object(crops, "crop_png", wraps=crops.crop_png) as render:
            with ThreadPoolExecutor(6) as pool:
                images = list(pool.map(lambda _: self.render(), range(12)))
            self.assertEqual(render.call_count, 1)
        self.assertTrue(all(image == images[0] for image in images))
        self.assertEqual(self.slot().read_bytes(), images[0])
        self.assertEqual(fitz.Pixmap(images[0]).pixel(90, 50), (255, 0, 0))
        self.assertEqual(crops._png_metadata(images[0])["document_id"], fingerprint(self.pdf))

    def test_bounds_settings_asset_geometry_and_version_are_matched(self):
        with mock.patch.object(crops, "crop_png", wraps=crops.crop_png) as render:
            self.render()
            selected = self.render(bbox=(10, 8, 80, 40))
            self.assertEqual(fitz.Pixmap(selected).pixel(10, 10), (255, 0, 0))
            resized = self.render(bbox=(10, 8, 80, 40), size=100)
            self.assertEqual(max(fitz.Pixmap(resized).width, fitz.Pixmap(resized).height), 100)
            self.render(asset_id="segment:2/figure:1")
            # Simulate stale geometry metadata while retaining the same fingerprint.
            region = crops.describe_region(self.pdf, 1, None)
            region["geometry"]["rotation"] = 180
            self.render(region=region)
            with mock.patch.object(crops, "RENDERER_VERSION", 2):
                self.render(region=region)
                self.render(region=region)
            self.assertEqual(render.call_count, 6)

    def test_documents_and_run_directories_are_isolated(self):
        other = build_coloured_pages(self.tmp_path / "other.pdf", 0, True)
        with mock.patch.object(crops, "crop_png", wraps=crops.crop_png) as render:
            first = self.render()
            second = self.render(pdf=other)
            self.render(run_dir=self.tmp_path / "other-run")
            self.assertEqual(self.render(), first)
            self.assertEqual(self.render(pdf=other), second)
            self.assertEqual(render.call_count, 3)
        self.assertNotEqual(fingerprint(self.pdf), fingerprint(other))
        self.assertEqual(len(list((self.run_dir / "images").iterdir())), 2)

    def test_new_process_reuses_persisted_png(self):
        self.render()
        script = '''
from pathlib import Path
from unittest.mock import patch
import sys
from reviewer_mcp import crops
from reviewer_mcp.store import fingerprint
pdf, run = map(Path, sys.argv[1:])
with patch.object(crops, "crop_png", side_effect=AssertionError("must reuse persisted PNG")):
    data = crops.cached_png(pdf, 1, None, 200, run_dir=run, document_id=fingerprint(pdf),
                            asset_id="page:1", region=crops.describe_region(pdf, 1, None))
    assert data.startswith(b"\\x89PNG")
'''
        result = subprocess.run([sys.executable, "-c", script, str(self.pdf), str(self.run_dir)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_render_or_atomic_write_preserves_valid_output(self):
        original = self.render()
        slot = self.slot()
        with mock.patch.object(crops, "crop_png", side_effect=RuntimeError("render failed")):
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                self.render(size=100)
        self.assertEqual(slot.read_bytes(), original)
        with mock.patch.object(crops.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(crops.ImagePersistenceError) as error:
                self.render(size=100)
            self.assertEqual(str(error.exception.__cause__), "replace failed")
        self.assertEqual(slot.read_bytes(), original)
        with mock.patch.object(crops.os, "fsync", side_effect=OSError("write failed")):
            with self.assertRaises(crops.ImagePersistenceError) as error:
                self.render(size=100)
            self.assertEqual(str(error.exception.__cause__), "write failed")
        self.assertEqual(slot.read_bytes(), original)
        self.assertEqual(list(self.run_dir.rglob("*.tmp")), [])
        with mock.patch.object(crops, "crop_png", side_effect=AssertionError("cache should survive")):
            self.assertEqual(self.render(), original)
        with mock.patch.object(crops.os, "replace", side_effect=OSError("new entry failed")):
            with self.assertRaises(OSError):
                self.render(asset_id="segment:2/figure:1")
        self.assertEqual(list(self.run_dir.rglob("*.png")), [slot])

    def test_render_failure_and_invalid_render_never_create_successful_entry(self):
        for outcome in (RuntimeError("failed"), b"not a PNG"):
            with mock.patch.object(crops, "crop_png", side_effect=outcome if isinstance(outcome, Exception) else None,
                                   return_value=outcome):
                with self.assertRaises((RuntimeError, ValueError)):
                    self.render()
            self.assertFalse(self.run_dir.exists())
        self.render()
        self.slot()

    def test_incomplete_corrupt_or_missing_metadata_is_a_cache_miss(self):
        original = self.render()
        slot = self.slot()
        no_metadata = crops.crop_png(self.pdf, 1, None, 200)
        corrupt = bytearray(original)
        corrupt[50] ^= 1
        # Includes a CRC-correct but undecodable IDAT payload.
        broken_pixels = bytearray(no_metadata)
        start = broken_pixels.index(b"IDAT")
        size = crops.struct.unpack_from(">I", broken_pixels, start - 4)[0]
        broken_pixels[start + 4:start + 4 + size] = b"x" * size
        checksum = crops.zlib.crc32(broken_pixels[start:start + 4 + size])
        crops.struct.pack_into(">I", broken_pixels, start + 4 + size, checksum)
        for invalid in (b"", original[:40], original[:-12], bytes(corrupt), no_metadata, bytes(broken_pixels)):
            with self.subTest(length=len(invalid)):
                slot.write_bytes(invalid)
                with mock.patch.object(crops, "crop_png", wraps=crops.crop_png) as render:
                    repaired = self.render()
                    self.assertEqual(render.call_count, 1)
                self.assertEqual(repaired, original)

    def test_failed_replacement_exposes_only_the_complete_previous_entry(self):
        original = self.render()
        slot = self.slot()
        real_replace = crops.os.replace

        def inspect_before_replace(source, destination):
            self.assertEqual(slot.read_bytes(), original)
            self.assertIsNotNone(crops._png_metadata(source.read_bytes()))
            real_replace(source, destination)

        with mock.patch.object(crops.os, "replace", side_effect=inspect_before_replace):
            changed = self.render(size=100)
        self.assertEqual(slot.read_bytes(), changed)
        self.assertNotEqual(changed, original)


if __name__ == "__main__":
    unittest.main()
