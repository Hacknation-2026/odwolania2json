import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
import pymupdf

from src.augment import (
    DistortionConfig,
    adjust_brightness,
    adjust_contrast,
    add_salt_and_pepper_noise,
    add_scanner_streaks,
    apply_bad_fit_to_page,
    apply_orientation,
    apply_paper_tint,
    apply_shadow_gradient,
    apply_skew,
    augment_case,
    augment_dataset,
    augment_pdf,
    get_preset_config,
    get_unicode_font_path,
    inject_ocr_noise,
)


def extract_pdf_text(pdf_path: Path) -> str:
    """Text layer of a PDF (build_dataset.py was superseded by backend/app/train_classifier.py)."""
    with pymupdf.open(pdf_path) as document:
        return "\n\n".join(page.get_text("text", sort=True).strip() for page in document)


def create_test_pdf(path: Path, pages_text: list[str]) -> None:
    doc = pymupdf.open()
    font_path = get_unicode_font_path()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)
        if font_path:
            page.insert_font(fontname="dejavu", fontfile=font_path)
            page.insert_text((72, 100), text, fontname="dejavu", fontsize=12)
        else:
            page.insert_text((72, 100), text, fontsize=12)
    doc.save(path)
    doc.close()


class AugmentationTests(unittest.TestCase):
    def setUp(self) -> None:
        # Create a sample test image (white canvas with dark rectangle simulating text)
        self.img = Image.new("RGB", (200, 300), color=(255, 255, 255))
        arr = np.array(self.img)
        arr[50:150, 40:160] = (20, 20, 20)
        self.img = Image.fromarray(arr)

    def test_adjust_brightness_and_contrast(self) -> None:
        darker = adjust_brightness(self.img, 0.5)
        brighter = adjust_brightness(self.img, 1.5)
        self.assertLess(np.mean(np.array(darker)), np.mean(np.array(self.img)))
        self.assertGreater(np.mean(np.array(brighter)), np.mean(np.array(self.img)))

        high_contrast = adjust_contrast(self.img, 2.0)
        self.assertEqual(high_contrast.size, self.img.size)

    def test_apply_skew(self) -> None:
        skewed = apply_skew(self.img, 2.5)
        self.assertEqual(skewed.size, self.img.size)
        self.assertEqual(skewed.mode, "RGB")

    def test_apply_orientation(self) -> None:
        flip_180 = apply_orientation(self.img, "flip_180")
        self.assertEqual(flip_180.size, self.img.size)

        rot_cw = apply_orientation(self.img, "rot_90_cw")
        self.assertEqual(rot_cw.size, (300, 200))

    def test_noise_and_streaks(self) -> None:
        import random
        rng = random.Random(42)
        noisy = add_salt_and_pepper_noise(self.img, 0.02, rng)
        self.assertEqual(noisy.size, self.img.size)

        streaked = add_scanner_streaks(self.img, 2, rng)
        self.assertEqual(streaked.size, self.img.size)

    def test_paper_tint_and_shadow(self) -> None:
        import random
        rng = random.Random(42)
        tinted = apply_paper_tint(self.img, rng)
        self.assertEqual(tinted.size, self.img.size)

        shadowed = apply_shadow_gradient(self.img, rng)
        self.assertEqual(shadowed.size, self.img.size)

    def test_inject_ocr_noise(self) -> None:
        import random
        rng = random.Random(42)
        original = "Zażółć gęślą jaźń oraz Pełnomocnictwo numer 10"
        noisy = inject_ocr_noise(original, error_rate=0.5, rng=rng)
        self.assertNotEqual(original, noisy)
        self.assertTrue(len(noisy) > 0)

    def test_augment_pdf_creates_valid_searchable_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_pdf = temp_path / "sample.pdf"
            out_pdf = temp_path / "sample_distorted.pdf"

            sample_text = "ODWOŁANIE do Prezesa Krajowej Izby Odwoławczej w Warszawie."
            create_test_pdf(src_pdf, [sample_text])

            config = DistortionConfig(
                render_dpi=100,
                prob_flip_180=0.0,
                prob_rotate_90=0.0,
                preserve_text_layer=True,
                prob_ocr_noise=0.0,
            )
            meta = augment_pdf(src_pdf, out_pdf, config=config, seed=123)

            self.assertTrue(out_pdf.is_file())
            self.assertEqual(len(meta["pages"]), 1)

            # Check that extract_pdf_text can extract text from the augmented PDF
            extracted = extract_pdf_text(out_pdf)
            self.assertIn("ODWOŁANIE", extracted)
            self.assertIn("Krajowej Izby Odwoławczej", extracted)

    def test_augment_case_preserves_structure_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            case_dir = temp_path / "case_01"
            case_dir.mkdir()

            pdf_path = case_dir / "odwolanie.pdf"
            json_path = case_dir / "odwolanie.json"
            create_test_pdf(pdf_path, ["Treść odwołania"])
            json_data = {"tytul": "Testowe zamówienie publiczne", "kwota": 1000}
            json_path.write_text(json.dumps(json_data), encoding="utf-8")

            out_case_dir = temp_path / "case_01_aug1"
            config = DistortionConfig(render_dpi=100, prob_flip_180=0.0, prob_rotate_90=0.0)
            created = augment_case(case_dir, out_case_dir, config=config, seed=42)

            self.assertEqual(len(created), 2)
            self.assertTrue((out_case_dir / "odwolanie.pdf").is_file())
            self.assertTrue((out_case_dir / "odwolanie.json").is_file())

            # Verify JSON label was cleanly copied
            loaded_json = json.loads((out_case_dir / "odwolanie.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded_json, json_data)

    def test_presets(self) -> None:
        mild = get_preset_config("mild")
        realistic = get_preset_config("realistic")
        severe = get_preset_config("severe")

        self.assertGreater(mild.brightness_min, realistic.brightness_min)
        self.assertGreater(severe.max_skew_deg, realistic.max_skew_deg)
        self.assertGreater(severe.prob_bad_fit, realistic.prob_bad_fit)
        self.assertGreater(realistic.prob_bad_fit, mild.prob_bad_fit)

    def test_apply_bad_fit_to_page(self) -> None:
        import random
        rng = random.Random(42)
        shrunk, meta = apply_bad_fit_to_page(
            self.img,
            scale=0.8,
            offset_mode="center",
            border_style="scanner_gray",
            add_edge_line=True,
            rng=rng,
        )
        self.assertEqual(shrunk.size, self.img.size)
        self.assertEqual(meta["scale"], 0.8)
        self.assertGreater(meta["dx_ratio"], 0.0)
        self.assertGreater(meta["dy_ratio"], 0.0)

    def test_augment_pdf_with_bad_fit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_pdf = temp_path / "sample.pdf"
            out_pdf = temp_path / "sample_bad_fit.pdf"

            sample_text = "ODWOŁANIE do Krajowej Izby Odwoławczej z pomniejszonym marginesem."
            create_test_pdf(src_pdf, [sample_text])

            config = DistortionConfig(
                render_dpi=100,
                prob_bad_fit=1.0,
                bad_fit_scale_min=0.75,
                bad_fit_scale_max=0.75,
                prob_flip_180=0.0,
                prob_rotate_90=0.0,
                prob_skew=0.0,
                preserve_text_layer=True,
                prob_ocr_noise=0.0,
            )
            meta = augment_pdf(src_pdf, out_pdf, config=config, seed=42)

            self.assertTrue(out_pdf.is_file())
            self.assertIn("bad_fit", meta["pages"][0])
            self.assertEqual(meta["pages"][0]["bad_fit"]["scale"], 0.75)

            # Check text is still extractable
            extracted = extract_pdf_text(out_pdf)
            self.assertIn("ODWOŁANIE", extracted)
            self.assertIn("Krajowej Izby Odwoławczej", extracted)


if __name__ == "__main__":
    unittest.main()
