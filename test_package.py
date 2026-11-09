"""Validate the native settings contract without requiring a running Zen."""
import json
from pathlib import Path
import unittest
from uuid import UUID

ROOT = Path(__file__).parent


class PackageTests(unittest.TestCase):
    def test_manifest_has_stable_uuid(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(str(UUID(manifest["id"])), manifest["id"])
        self.assertEqual(manifest["name"], "Splendid Notch")

    def test_every_setting_has_a_css_consumer(self):
        prefs = json.loads((ROOT / "preferences.json").read_text())
        css = (ROOT / "zen-notch.css").read_text()
        properties = [pref["property"] for pref in prefs]
        self.assertEqual(
            properties,
            [
                "zen.notch.always-visible",
                "zen.notch.disable-shadow",
                "zen.notch.disable-animation",
            ],
        )
        self.assertEqual(len(properties), len(set(properties)))
        for pref in prefs:
            with self.subTest(property=pref["property"]):
                self.assertTrue(pref["property"].startswith("zen.notch."))
                self.assertTrue(pref["label"])
                self.assertEqual(pref["type"], "checkbox")
                self.assertIsInstance(pref["defaultValue"], bool)
                self.assertIn('-moz-pref("' + pref["property"] + '")', css)


if __name__ == "__main__":
    unittest.main()
