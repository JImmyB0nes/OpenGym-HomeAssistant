"""HACS/hassfest conformity checks for the openGym integration.

These are the structural rules HACS and hassfest actually enforce, run as
plain unittests (no HA install needed):

- manifest: required keys, semver version, valid enums, real dependencies,
  https docs/issue tracker, domain == folder
- hacs.json: valid JSON, name, HA minimum version
- brand: icon.png + dark_icon.png present, sizes as hassfest's brand_images
  check demands (hacs/default fails new additions on its warnings)
- translations: en+de parse, every _attr_translation_key in code exists
- services.yaml: exactly the services registered in code
- version coherence: manifest version == card CARD_VERSION == git tag

Run:  python3 -m unittest test_hacs_conform -v
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

import stub_ha

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "opengym"

VALID_INTEGRATION_TYPES = {
    "app", "device", "entity", "hardware", "hub", "service", "system",
}
VALID_IOT_CLASSES = {
    "assumed_state", "calculated", "cloud_push", "cloud_polling",
    "local_polling", "local_push",
}


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((COMP / "manifest.json").read_text())

    def test_required_keys(self):
        for key in ("domain", "name", "codeowners", "config_flow",
                    "documentation", "issue_tracker", "version"):
            self.assertIn(key, self.manifest, f"manifest missing {key}")

    def test_domain_matches_folder(self):
        self.assertEqual(self.manifest["domain"], COMP.name)

    def test_version_is_semver_without_v(self):
        self.assertRegex(self.manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_urls_https(self):
        for key in ("documentation", "issue_tracker"):
            self.assertTrue(self.manifest[key].startswith("https://"), key)

    def test_codeowners_format(self):
        for owner in self.manifest["codeowners"]:
            self.assertRegex(owner, r"^@[\w-]+(/[\w-]+)?$")

    def test_valid_enums(self):
        self.assertIn(self.manifest.get("integration_type", "service"),
                      VALID_INTEGRATION_TYPES)
        self.assertIn(self.manifest.get("iot_class", "polling"),
                      VALID_IOT_CLASSES)

    def test_dependencies_are_known_ha_domains(self):
        # hassfest rejects unknown/built-in-misuse dependencies.
        known = {"frontend", "http", "websocket_api", "webhook", "calendar",
                 "sensor", "binary_sensor", "update", "diagnostics", "button",
                 "repairs"}
        for dep in self.manifest.get("dependencies", []):
            self.assertIn(dep, known, f"suspicious dependency {dep}")

    def test_config_flow_file_exists(self):
        if self.manifest.get("config_flow"):
            self.assertTrue((COMP / "config_flow.py").exists())

    def test_no_unknown_manifest_keys(self):
        allowed = {"domain", "name", "codeowners", "config_flow", "dependencies",
                   "after_dependencies", "documentation", "integration_type",
                   "iot_class", "issue_tracker", "requirements", "version",
                   "single_config_entry", "quality_scale", "categories", "dhcp", "zeroconf",
                   "homekit", "ssdp", "usb"}
        unknown = set(self.manifest) - allowed
        self.assertEqual(unknown, set(), f"unknown manifest keys: {unknown}")


class TestHacs(unittest.TestCase):
    def test_hacs_json(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual(hacs.get("name"), "openGym")
        self.assertTrue(hacs.get("render_readme"))
        # HA minimum must be a real version string
        self.assertRegex(hacs["homeassistant"], r"^\d{4}\.\d+\.\d+$")

    def test_brand_icons(self):
        brand = COMP / "brand"
        self.assertTrue((brand / "icon.png").exists())
        self.assertTrue((brand / "dark_icon.png").exists())

    def test_brand_image_sizes(self):
        # Mirrors hassfest brand_images.py: icon 256x256, icon@2x 512x512,
        # logo shortest side 128-256, logo@2x 256-512; dark_ variants alike.
        import struct
        allowed = {f"{d}{k}{s}.png" for d in ("", "dark_")
                   for k in ("icon", "logo") for s in ("", "@2x")}
        for path in sorted((COMP / "brand").iterdir()):
            self.assertIn(path.name, allowed, f"unexpected brand file {path.name}")
            head = path.read_bytes()[:24]
            self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n", path.name)
            w, h = struct.unpack(">II", head[16:24])
            base = path.name.removeprefix("dark_")
            if base.startswith("icon"):
                n = 512 if "@2x" in base else 256
                self.assertEqual((w, h), (n, n), path.name)
            else:
                lo, hi = (256, 512) if "@2x" in base else (128, 256)
                self.assertTrue(lo <= min(w, h) <= hi, f"{path.name} {w}x{h}")
            if "@2x" in base:
                self.assertTrue((COMP / "brand" / path.name.replace("@2x", "")).exists())


class TestTranslations(unittest.TestCase):
    def setUp(self):
        self.en = json.loads((COMP / "translations" / "en.json").read_text())
        self.de = json.loads((COMP / "translations" / "de.json").read_text())

    def test_config_flow_translated(self):
        for lang, d in (("en", self.en), ("de", self.de)):
            self.assertIn("config", d, f"{lang}: config_flow integration needs config strings")
            self.assertIn("step", d["config"])

    def test_de_and_en_key_parity(self):
        def keys(d, path=()):
            out = set()
            for k, v in d.items():
                if isinstance(v, dict):
                    out |= keys(v, path + (k,))
                else:
                    out.add(path + (k,))
            return out
        self.assertEqual(keys(self.en), keys(self.de))

    def test_every_translation_key_declared(self):
        entity_keys = (set(self.en["entity"]["sensor"])
                       | set(self.en["entity"]["binary_sensor"])
                       | set(self.en["entity"]["calendar"])
                       | set(self.en["entity"]["update"])
                       | set(self.en["entity"]["button"]))
        src = "\n".join((COMP / f).read_text() for f in
                        ("sensor.py", "binary_sensor.py", "calendar.py", "update.py",
                         "button.py"))
        declared = set(re.findall(r'_attr_translation_key\s*=\s*"([^"]+)"', src))
        # entities that hand their key to a base class: (coordinator, entry, "key", "Name")
        declared |= set(re.findall(
            r'super\(\)\.__init__\(\s*coordinator,\s*entry,\s*"([^"]+)",\s*"', src))
        # STATIC_SENSORS tuples: ("key", "Name", "kind") — key is the translation key
        sensor_src = (COMP / "sensor.py").read_text()
        block = re.search(r"STATIC_SENSORS\s*=\s*\((.*?)\n\)", sensor_src, re.S).group(1)
        declared |= set(re.findall(r'\(\s*"([^"]+)"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*\)', block))
        # muscle slugs live in const.MUSCLES — parse statically (no HA import).
        const_src = (COMP / "const.py").read_text()
        mus = re.search(r"MUSCLES[^=]*=\s*\{(.*?)\n\}", const_src, re.S).group(1)
        for slug in re.findall(r'"([\w-]+)":', mus):
            declared.add(f"muscle_{slug.replace('-', '_')}")
            declared.add(f"muscle_{slug.replace('-', '_')}_recovering")
            declared.add(f"weekly_sets_{slug.replace('-', '_')}")
        declared |= {"rest_day", "active_workout", "worked_out_today",
                     "worked_out_this_week", "training_plan", "workout_history",
                     "instance_update"}
        missing = declared - entity_keys
        self.assertEqual(missing, set(), f"translation keys not in en.json: {missing}")


    def test_new_entities_translated(self):
        for key in ("live_progress", "rest_timer", "coach_status", "watch_paired",
                    "watch_heart_rate", "watch_hr_zone"):
            self.assertIn(key, self.en["entity"]["sensor"])
        for key in ("day_done", "nudge_pending"):
            self.assertIn(key, self.en["entity"]["binary_sensor"])
        for key in ("coach_accept", "coach_reject"):
            self.assertIn(key, self.en["entity"]["button"])

    def test_exceptions_translated(self):
        src = "\n".join(p.read_text() for p in COMP.glob("*.py"))
        used = set(re.findall(r'translation_key="([a-z_]+)"', src))
        used -= {"connection_error", "webhook_delivery_failed"}  # issues
        used |= {f"plan_{k}" for k in ("same_day", "nothing_planned", "note_future", "note_tag")}
        self.assertEqual(used - set(self.en["exceptions"]), set())

    def test_fixable_issue_has_fix_flow(self):
        for d in (self.en, self.de):
            issue = d["issues"]["webhook_delivery_failed"]
            self.assertIn("confirm", issue["fix_flow"]["step"])
            self.assertNotIn("description", issue)

    def test_every_service_translated(self):
        import yaml
        services = yaml.safe_load((COMP / "services.yaml").read_text())
        for d in (self.en, self.de):
            for name, spec in services.items():
                self.assertIn("name", d["services"][name])
                self.assertIn("description", d["services"][name])
                for field in spec.get("fields") or {}:
                    self.assertIn(field, d["services"][name].get("fields", {}),
                                  f"{name}.{field} untranslated")


class TestServices(unittest.TestCase):
    def test_services_yaml_matches_registered(self):
        import yaml  # stdlib-free; skip gracefully if absent
        services = yaml.safe_load((COMP / "services.yaml").read_text())
        const = (COMP / "const.py").read_text()
        registered = set(re.findall(r'SERVICE_\w+\s*=\s*"([^"]+)"', const))
        self.assertEqual(set(services), registered)

    def test_service_fields_have_descriptions_or_selectors(self):
        import yaml
        services = yaml.safe_load((COMP / "services.yaml").read_text())
        for name, spec in services.items():
            for field, fspec in (spec.get("fields") or {}).items():
                self.assertTrue(fspec.get("selector") or fspec.get("text"),
                                f"{name}.{field} needs a selector")


class TestVersionCoherence(unittest.TestCase):
    def test_card_version_matches_manifest(self):
        js = (COMP / "frontend" / "opengym-muscle-card.js").read_text()
        card = re.search(r'CARD_VERSION = "([^"]+)"', js).group(1)
        manifest = json.loads((COMP / "manifest.json").read_text())["version"]
        self.assertEqual(card, manifest)

    def test_tag_matches_manifest(self):
        try:
            tag = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=ROOT, capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            self.skipTest("git not available")
        if not tag:
            self.skipTest("no tags yet")
        manifest = json.loads((COMP / "manifest.json").read_text())["version"]
        # The manifest may be bumped ahead of the latest tag (release pending),
        # but must never lag behind it.
        def _v(s):
            return tuple(int(x) for x in re.findall(r"\d+", s)[:3])
        self.assertGreaterEqual(_v(manifest), _v(tag.lstrip("v")))


if __name__ == "__main__":
    unittest.main()
