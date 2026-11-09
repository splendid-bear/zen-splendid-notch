import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from install import BLOCK, IMPORT, OWNER as LEGACY_OWNER
from native_install import update, write_registry


class NativeInstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="zen native test ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile = self.root / "profile"
        self.profile.mkdir()
        self.source = self.root / "source"
        self.source.mkdir()
        self.manifest = dict(id="zen-notch-test", name="Splendid Notch", description="Local mod",
                             version="1.0", author="Local descriptive author")
        (self.source / "manifest.json").write_text(json.dumps(self.manifest))
        self.payload = {"zen-notch.css": b":root { color: red; }\n",
                        "preferences.json": b'[{"id":"notch","type":"checkbox","defaultValue":true}]\n',
                        "README.md": b"# Splendid Notch\n"}
        for name, data in self.payload.items():
            (self.source / name).write_bytes(data)
        self.chrome = self.profile / "chrome"
        self.chrome.mkdir()
        self.user_css = self.chrome / "userChrome.css"
        self.user_css.write_bytes(b"/* unrelated */\r\n")
        self.registry = self.profile / "zen-themes.json"
        self.target = self.chrome / "zen-themes" / self.manifest["id"]
        self.protected = {self.profile / "prefs.js": b"// prefs untouched\n",
                          self.profile / "user.js": b"// user untouched\n",
                          self.chrome / "zen-themes.css": b"/* generated untouched */\n"}
        for path, data in self.protected.items():
            path.write_bytes(data)

    def run_action(self, action="install"):
        update(self.profile, action, self.source)
        for path, data in self.protected.items():
            self.assertEqual(path.read_bytes(), data)

    def read_registry(self):
        return json.loads(self.registry.read_bytes())

    def legacy(self):
        legacy = self.chrome / "zen-notch"
        legacy.mkdir()
        (legacy / ".owner").write_text(LEGACY_OWNER)
        (legacy / "zen-notch.css").write_text("/* old */")
        self.user_css.write_bytes(BLOCK.encode() + b"/* unrelated */\r\n")
        return legacy

    def test_install_shape_uris_preferences_idempotency(self):
        self.run_action()
        registry = self.read_registry()
        self.assertEqual(list(registry), [self.manifest["id"]])
        entry = registry[self.manifest["id"]]
        for key, value in self.manifest.items():
            self.assertEqual(entry[key], value)
        for key, filename in (("style", "chrome.css"), ("preferences", "preferences.json"),
                              ("readme", "readme.md")):
            self.assertEqual(entry[key], (self.target / filename).as_uri())
            self.assertIn("%20", entry[key])
        for destination, source in (("chrome.css", "zen-notch.css"),
                                    ("preferences.json", "preferences.json"), ("readme.md", "README.md")):
            self.assertEqual((self.target / destination).read_bytes(), self.payload[source])
        self.assertTrue(entry["enabled"])
        before = self.registry.read_bytes()
        self.run_action()
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertFalse(list(self.profile.glob("zen-themes.json.backup-*")))
        self.assertEqual(self.user_css.read_bytes(), b"/* unrelated */\r\n")

    def test_preserve_entries_enabled_and_backup(self):
        unrelated = {"another-mod": {"id": "another-mod", "enabled": True, "style": "https://example.test/a"}}
        self.registry.write_text(json.dumps(unrelated))
        original = self.registry.read_bytes()
        self.run_action()
        self.assertIn(original, [p.read_bytes() for p in self.profile.glob("zen-themes.json.backup-*")])
        registry = self.read_registry()
        registry[self.manifest["id"]].update(enabled=False, custom="keep")
        self.registry.write_text(json.dumps(registry))
        self.run_action()
        entry = self.read_registry()[self.manifest["id"]]
        self.assertFalse(entry["enabled"])
        self.assertEqual(entry["custom"], "keep")
        self.run_action("uninstall")
        self.assertEqual(self.read_registry(), unrelated)
        self.assertFalse(self.target.exists())
        self.run_action("uninstall")

    def test_migration_preserves_css_and_legacy_files(self):
        legacy = self.legacy()
        self.run_action()
        self.assertEqual(self.user_css.read_bytes(), b"/* unrelated */\r\n")
        self.assertTrue((legacy / "zen-notch.css").is_file())
        self.run_action()
        self.run_action("uninstall")
        self.assertEqual(self.user_css.read_bytes(), b"/* unrelated */\r\n")

    def test_failed_preflight_keeps_legacy(self):
        self.legacy()
        before = self.user_css.read_bytes()
        for invalid in (b"{", b"[]", b'{"a":null}', b'{"a":{},"a":{}}',
                        b'{"a":{"enabled":"false"}}'):
            with self.subTest(invalid=invalid):
                self.registry.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    self.run_action()
                self.assertEqual(self.registry.read_bytes(), invalid)
                self.assertEqual(self.user_css.read_bytes(), before)
                self.assertFalse(self.target.exists())
        self.registry.unlink()
        (self.source / "preferences.json").unlink()
        with self.assertRaises(OSError):
            self.run_action()
        self.assertEqual(self.user_css.read_bytes(), before)

    def test_registry_failure_restores_legacy(self):
        self.legacy()
        before = self.user_css.read_bytes()
        with patch("native_install.write_registry", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.run_action()
        self.assertEqual(self.user_css.read_bytes(), before)
        self.assertFalse(self.registry.exists())
        self.run_action()

    def test_atomic_registry_failure_preserves_original_and_backup(self):
        self.legacy()
        self.registry.write_bytes(b'{"other": {"id": "other"}}\n')
        original = self.registry.read_bytes()
        old_css = self.user_css.read_bytes()
        replace = os.replace

        def fail_registry(source, destination):
            if destination == self.registry:
                raise OSError("simulated registry replacement failure")
            return replace(source, destination)

        with patch("native_install.os.replace", side_effect=fail_registry):
            with self.assertRaises(OSError):
                self.run_action()
        self.assertEqual(self.registry.read_bytes(), original)
        self.assertEqual(self.user_css.read_bytes(), old_css)
        self.assertEqual([p.read_bytes() for p in self.profile.glob("zen-themes.json.backup-*")],
                         [original])
        self.assertFalse(list(self.profile.glob(".zen-themes.json.*")))

    def test_refuse_unmanaged_import_or_missing_legacy_owner(self):
        for css in (IMPORT, BLOCK, BLOCK + IMPORT):
            self.user_css.write_text(css)
            with self.assertRaises(ValueError):
                self.run_action()
            self.assertEqual(self.user_css.read_text(), css)
            self.assertFalse(self.target.exists())

    def test_unmanaged_collisions_and_changed_entry(self):
        self.target.mkdir(parents=True)
        for action in ("install", "uninstall"):
            with self.assertRaises(ValueError):
                self.run_action(action)
        self.target.rmdir()
        collision = {self.manifest["id"]: {"id": self.manifest["id"], "enabled": False}}
        self.registry.write_text(json.dumps(collision))
        with self.assertRaises(ValueError):
            self.run_action()
        self.assertEqual(self.read_registry(), collision)
        self.registry.unlink()
        self.run_action()
        changed = self.read_registry()
        changed[self.manifest["id"]]["style"] = "https://example.test/user.css"
        self.registry.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            self.run_action("uninstall")
        self.assertEqual(self.read_registry(), changed)
        self.assertTrue((self.target / "chrome.css").exists())

    def test_uninstall_preserves_extra_files_and_ui_removal_rerun(self):
        self.run_action()
        extra = self.target / "notes.txt"
        extra.write_text("keep")
        self.run_action("uninstall")
        self.run_action("uninstall")
        self.assertEqual(extra.read_text(), "keep")
        self.run_action()
        # Simulate Zen UI removal (only test fixture files).
        for path in self.target.iterdir():
            path.unlink()
        self.target.rmdir()
        self.registry.write_text("{}")
        self.run_action("uninstall")
        self.registry.unlink()
        self.run_action("uninstall")
        self.assertFalse(self.registry.exists())

    def test_lock_symlinks_including_broken(self):
        existing = self.root / "existing-lock"
        existing.write_bytes(b"keep")
        for name in ("parent.lock", ".parentlock", "lock"):
            path = self.profile / name
            for destination in (existing, self.root / "missing"):
                path.symlink_to(destination)
                for action in ("install", "uninstall"):
                    with self.assertRaises(ValueError):
                        self.run_action(action)
                self.assertTrue(path.is_symlink())
                path.unlink()
        self.assertEqual(existing.read_bytes(), b"keep")
        self.assertFalse(self.target.exists())

    @unittest.skipUnless(os.name == "posix", "POSIX profile lock links")
    def test_stale_local_lock_link_is_ignored_but_preserved(self):
        path = self.profile / "lock"
        path.symlink_to("local-host:+12345")
        with patch("native_install.socket.gethostname", return_value="local-host"), \
                patch("native_install.socket.getfqdn", return_value="local-host"), \
                patch("native_install.socket.getaddrinfo", return_value=[]), \
                patch("native_install.os.kill", side_effect=ProcessLookupError):
            self.run_action()
            self.run_action("uninstall")
        self.assertTrue(path.is_symlink())
        self.assertEqual(os.readlink(path), "local-host:+12345")

    @unittest.skipUnless(os.name == "posix", "POSIX profile lock links")
    def test_live_or_remote_lock_links_are_refused(self):
        path = self.profile / "lock"
        path.symlink_to("remote-host:+12345")
        with patch("native_install.socket.gethostname", return_value="local-host"), \
                patch("native_install.socket.getfqdn", return_value="local-host"), \
                patch("native_install.socket.getaddrinfo", return_value=[]):
            for action in ("install", "uninstall"):
                with self.assertRaisesRegex(ValueError, "active or unverifiable"):
                    self.run_action(action)
        path.unlink()
        path.symlink_to("local-host:+12345")
        with patch("native_install.socket.gethostname", return_value="local-host"), \
                patch("native_install.socket.getfqdn", return_value="local-host"), \
                patch("native_install.socket.getaddrinfo", return_value=[]), \
                patch("native_install.os.kill", return_value=None):
            with self.assertRaisesRegex(ValueError, "active or unverifiable"):
                self.run_action()
        self.assertFalse(self.target.exists())

    @unittest.skipUnless(os.name == "posix", "POSIX advisory locks")
    def test_persistent_unlocked_files(self):
        for name in (".parentlock", "parent.lock", "lock"):
            path = self.profile / name
            path.write_bytes(b"persistent lock contents")
            inode = path.stat().st_ino
            self.run_action()
            self.run_action("uninstall")
            self.assertEqual(path.stat().st_ino, inode)
            self.assertEqual(path.read_bytes(), b"persistent lock contents")

    @unittest.skipUnless(os.name == "posix", "POSIX advisory locks")
    def test_live_subprocess_locks(self):
        import select
        for name in (".parentlock", "parent.lock", "lock"):
            path = self.profile / name
            path.write_bytes(b"keep")
            original_registry = self.registry.read_bytes() if self.registry.exists() else None
            code = ("import fcntl, sys; f = open(sys.argv[1], 'r+b'); "
                    "fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB); "
                    "print('locked', flush=True); sys.stdin.read()")
            with subprocess.Popen([sys.executable, "-c", code, str(path)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) as process:
                try:
                    self.assertTrue(select.select([process.stdout], [], [], 5)[0], "lock holder timed out")
                    self.assertEqual(process.stdout.readline().strip(), "locked")
                    for action in ("install", "uninstall"):
                        with self.assertRaisesRegex(ValueError, "lock is active"):
                            self.run_action(action)
                    self.assertEqual(self.registry.read_bytes() if self.registry.exists() else None,
                                     original_registry)
                    self.assertFalse(self.target.exists())
                finally:
                    process.kill()
                    process.communicate(timeout=5)
            self.assertEqual(path.read_bytes(), b"keep")
            self.run_action()
            self.run_action("uninstall")

    def lock_probe(self, path):
        code = ("import fcntl, sys\nf = open(sys.argv[1], 'r+b')\n"
                "try:\n fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
                "except BlockingIOError:\n sys.exit(2)\n")
        return subprocess.run([sys.executable, "-c", code, str(path)],
                              capture_output=True, timeout=5).returncode

    @unittest.skipUnless(os.name == "posix", "POSIX advisory locks")
    def test_lock_held_through_operation_and_released_on_error(self):
        path = self.profile / ".parentlock"
        path.touch()

        def checked_write(*args):
            self.assertEqual(self.lock_probe(path), 2)
            write_registry(*args)

        with patch("native_install.write_registry", side_effect=checked_write):
            self.run_action()
            self.run_action("uninstall")
        self.assertEqual(self.lock_probe(path), 0)
        with patch("native_install.write_registry", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                self.run_action()
        self.assertEqual(self.lock_probe(path), 0)

    def test_unverifiable_platform_lock(self):
        path = self.profile / "parent.lock"
        path.write_bytes(b"keep")
        with patch("native_install.fcntl", None):
            for action in ("install", "uninstall"):
                with self.assertRaisesRegex(ValueError, "Cannot verify.*Windows"):
                    self.run_action(action)
        self.assertEqual(path.read_bytes(), b"keep")
        self.assertFalse(self.registry.exists())

    def test_preferences_require_array_of_objects(self):
        self.legacy()
        before = self.user_css.read_bytes()
        for value in ({"id": "notch"}, None, "preferences", [None], [1], [{}, "bad"]):
            with self.subTest(value=value):
                (self.source / "preferences.json").write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "array of objects"):
                    self.run_action()
                self.assertEqual(self.user_css.read_bytes(), before)
                self.assertFalse(self.registry.exists())
                self.assertFalse(self.target.exists())
        (self.source / "preferences.json").write_text("[]")
        self.run_action()

    def test_real_source_smoke(self):
        source = Path(__file__).parent
        manifest = json.loads((source / "manifest.json").read_bytes())
        update(self.profile, "install", source)
        target = self.chrome / "zen-themes" / manifest["id"]
        for destination, filename in (("chrome.css", "zen-notch.css"),
                                      ("preferences.json", "preferences.json"), ("readme.md", "README.md")):
            self.assertEqual((target / destination).read_bytes(), (source / filename).read_bytes())
        self.assertEqual(self.read_registry()[manifest["id"]]["preferences"],
                         (target / "preferences.json").as_uri())
        update(self.profile, "uninstall", source)
        self.assertEqual(self.read_registry(), {})
        self.assertFalse(target.exists())
        for path, data in self.protected.items():
            self.assertEqual(path.read_bytes(), data)

    def test_symlink_profile_and_parent(self):
        for destination in (self.profile, self.root):
            with self.subTest(destination=destination):
                link = self.root / "alias"
                link.symlink_to(destination, target_is_directory=True)
                profile = link if destination == self.profile else link / "profile"
                update(profile, "install", self.source)
                entry = self.read_registry()[self.manifest["id"]]
                self.assertEqual(entry["style"], (self.target / "chrome.css").resolve().as_uri())
                update(profile, "uninstall", self.source)
                self.assertNotIn(self.manifest["id"], self.read_registry())
                self.assertTrue(link.is_symlink())
                link.unlink()

    def test_broken_and_looping_profile_aliases(self):
        for destination in (self.root / "missing", self.root / "alias"):
            link = self.root / "alias"
            link.symlink_to(destination, target_is_directory=True)
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                update(link, "install", self.source)
            self.assertFalse(self.registry.exists())
            link.unlink()

    def test_cli_environment_profile_and_clean_errors(self):
        script = Path(__file__).with_name("native_install.py")
        env = dict(os.environ, PROFILE=str(self.profile))
        result = subprocess.run([sys.executable, str(script), "install"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Splendid Notch installed", result.stdout)
        result = subprocess.run([sys.executable, str(script), "uninstall"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        env["PROFILE"] = str(self.root / "missing")
        result = subprocess.run([sys.executable, str(script), "install"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot resolve PROFILE", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_symlink_destinations(self):
        self.run_action()
        for path in (self.registry, self.user_css, self.target / "chrome.css",
                     self.target / "preferences.json", self.target / "readme.md",
                     self.target / ".zen-notch-owner", self.profile / "prefs.js"):
            data = path.read_bytes()
            path.unlink()
            path.symlink_to(self.root / "missing")
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_action()
            path.unlink()
            path.write_bytes(data)
        for path in (self.target, self.target.parent, self.chrome):
            saved = path.with_name(path.name + "-saved")
            path.rename(saved)
            path.symlink_to(saved, target_is_directory=True)
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_action()
            path.unlink()
            saved.rename(path)

    def test_invalid_manifest_id(self):
        for mod_id in ("../escape", "/absolute", "..", ""):
            self.manifest["id"] = mod_id
            (self.source / "manifest.json").write_text(json.dumps(self.manifest))
            with self.assertRaises(ValueError):
                self.run_action()
            self.assertFalse(self.registry.exists())


if __name__ == "__main__":
    unittest.main()
