#!/usr/bin/env python3
"""Install a local native Zen mod. Close Zen before running this installer."""
import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
import tempfile

try:
    import fcntl
except ImportError:  # Windows has no compatible POSIX advisory lock probe.
    fcntl = None

from install import BLOCK, IMPORT, OWNER as LEGACY_OWNER

OWNER = "zen-notch native installer v1\n"
FILES = {"chrome.css": "zen-notch.css", "preferences.json": "preferences.json",
         "readme.md": "README.md"}


def safe(path):
    """Check before resolving: resolve() would hide symlinked ancestors."""
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Refusing symlink: {part}")


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(data):
    def invalid(value):
        raise ValueError(f"Invalid JSON constant: {value}")
    return json.loads(data, object_pairs_hook=object_pairs, parse_constant=invalid)


def atomic_write(path, data):
    safe(path)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_registry(path, registry, original):
    data = (json.dumps(registry, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if original is not None and load_json(original) == registry:
        return
    if original is not None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        fd, name = tempfile.mkstemp(prefix=f"{path.name}.backup-{stamp}-", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
    atomic_write(path, data)


def stale_local_lock(path):
    """Recognize a dead same-host Firefox-style lock without following it."""
    match = re.fullmatch(r"(.+):\+([1-9][0-9]*)", os.readlink(path))
    if not match:
        return False
    host, pid = match.groups()
    hostname = socket.gethostname()
    local_hosts = {hostname.lower(), socket.getfqdn().lower()}
    try:
        local_hosts.update(
            result[4][0].lower()
            for result in socket.getaddrinfo(hostname, None)
        )
    except OSError:
        return False
    if host.lower() not in local_hosts:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    except OSError:
        pass
    return False


@contextmanager
def profile_locks(profile):
    """Hold existing POSIX locks and ignore only proven-stale local lock links."""
    with ExitStack() as stack:
        for name in ("parent.lock", ".parentlock", "lock"):
            path = profile / name
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                if fcntl is None or not stale_local_lock(path):
                    raise ValueError(f"Refusing active or unverifiable profile lock: {path}")
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"Refusing non-regular profile lock: {path}")
            if fcntl is None:
                raise ValueError(f"Cannot verify existing profile lock on this platform (including "
                                 f"Windows): {path}. Close Zen; lock status must be verified manually.")
            try:
                fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
                stack.callback(os.close, fd)
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError(f"Profile lock changed during inspection: {path}")
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError(f"Profile lock is active or cannot be verified: {path}. "
                                 "Close Zen before proceeding.") from error
        # Closing the descriptors releases the locks on success and on every error path.
        yield


def update(profile: Path, action: str, source: Path = None) -> None:
    if action not in ("install", "uninstall"):
        raise ValueError("Action must be install or uninstall")
    # PROFILE is an explicitly selected trust boundary. Resolve aliases here,
    # then keep rejecting symlinks in managed files beneath the real profile.
    try:
        profile = profile.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"Cannot resolve PROFILE: {profile}: {error}") from error
    safe(profile)
    safe(profile / "prefs.js")
    if not profile.is_dir() or not (profile / "prefs.js").is_file():
        raise ValueError("PROFILE must be an existing Zen profile containing prefs.js")
    with profile_locks(profile):
        _update(profile, action, source)


def _update(profile, action, source):
    safe(source or Path(__file__).parent)
    source = Path(os.path.abspath(source or Path(__file__).parent))
    manifest_path = source / "manifest.json"
    safe(manifest_path)
    manifest = load_json(manifest_path.read_bytes())
    fields = ("id", "name", "description", "version", "author")
    if not isinstance(manifest, dict) or any(
            not isinstance(manifest.get(key), str) or not manifest[key].strip() for key in fields):
        raise ValueError("Manifest requires nonempty string id, name, description, version, author")
    mod_id = manifest["id"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", mod_id) or mod_id in (".", ".."):
        raise ValueError("Manifest id must be a safe, stable directory name")
    chrome = profile / "chrome"
    target = chrome / "zen-themes" / mod_id
    marker = target / ".zen-notch-owner"
    registry_path = profile / "zen-themes.json"
    for path in (chrome, target, marker, registry_path, *(target / name for name in FILES)):
        safe(path)
        if path.exists() and path not in (chrome, target) and not path.is_file():
            raise ValueError(f"Expected a regular file: {path}")
    for path in (chrome, target.parent, target):
        if path.exists() and not path.is_dir():
            raise ValueError(f"Expected a directory: {path}")
    original = registry_path.read_bytes() if registry_path.exists() else None
    registry = load_json(original) if original is not None else {}
    if not isinstance(registry, dict) or any(
            not isinstance(entry, dict) or
            ("id" in entry and entry["id"] != key) or
            ("enabled" in entry and not isinstance(entry["enabled"], bool))
            for key, entry in registry.items()):
        raise ValueError("zen-themes.json must be an object keyed by mod id with object entries")
    owned = marker.is_file() and marker.read_text(encoding="utf-8") == OWNER + mod_id + "\n"
    urls = {"style": (target / "chrome.css").as_uri(),
            "preferences": (target / "preferences.json").as_uri(),
            "readme": (target / "readme.md").as_uri()}
    entry = registry.get(mod_id)
    if target.exists() and not owned:
        raise ValueError(f"Refusing unmanaged mod directory: {target}")
    if entry is not None and (not owned or entry.get("id") != mod_id or
                              any(entry.get(key) != value for key, value in urls.items())):
        raise ValueError("Refusing unmanaged or changed registry entry")

    if action == "uninstall":
        if entry is not None:
            del registry[mod_id]
            write_registry(registry_path, registry, original)
        if owned:
            for name in FILES:
                (target / name).unlink(missing_ok=True)
            # Retain ownership when user extras keep the directory alive, so reruns are safe.
            if set(target.iterdir()) == {marker}:
                marker.unlink()
                target.rmdir()
        print("Splendid Notch uninstalled; unrelated files and preferences left unchanged.")
        return

    # Complete input and migration preflight before changing anything in the profile.
    payload = {}
    for destination, filename in FILES.items():
        safe(source / filename)
        payload[destination] = (source / filename).read_bytes()
    preferences = load_json(payload["preferences.json"])
    if not isinstance(preferences, list) or any(not isinstance(item, dict) for item in preferences):
        raise ValueError("preferences.json must contain an array of objects")
    user_css = chrome / "userChrome.css"
    legacy = chrome / "zen-notch"
    legacy_marker = legacy / ".owner"
    for path in (user_css, legacy, legacy_marker, legacy / "zen-notch.css"):
        safe(path)
    old_css = user_css.read_bytes() if user_css.exists() else b""
    text = old_css.decode("utf-8")
    migrated = text.replace(BLOCK, "")
    if IMPORT in migrated:
        raise ValueError("Found an unmanaged zen-notch import; remove it manually first")
    if migrated != text and not (legacy_marker.is_file() and
                                legacy_marker.read_text(encoding="utf-8") == LEGACY_OWNER):
        raise ValueError("Managed legacy import has no matching ownership marker")

    target.mkdir(parents=True, exist_ok=True)
    for name, data in payload.items():
        atomic_write(target / name, data)
    atomic_write(marker, (OWNER + mod_id + "\n").encode("utf-8"))
    metadata = dict(entry or {})
    metadata.update({key: manifest[key] for key in fields})
    metadata.update(urls)
    metadata.setdefault("enabled", True)
    registry[mod_id] = metadata
    # No native registry activation while the managed legacy import is still present.
    if migrated != text:
        atomic_write(user_css, migrated.encode("utf-8"))
    try:
        write_registry(registry_path, registry, original)
    except (OSError, ValueError):
        if migrated != text:
            atomic_write(user_css, old_css)
        raise
    print(f"{manifest['name']} installed in {target}. Restart Zen.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall"))
    environment_profile = os.environ.get("PROFILE") or None
    parser.add_argument("--profile", required=environment_profile is None,
                        default=environment_profile, type=Path,
                        help="Zen profile root (defaults to the PROFILE environment variable)")
    args = parser.parse_args()
    try:
        update(args.profile, args.action)
    except (OSError, ValueError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
