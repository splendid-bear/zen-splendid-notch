#!/usr/bin/env python3
"""Install an owned stylesheet and import without replacing user configuration."""
import argparse
from pathlib import Path
import sys

IMPORT = '@import url("zen-notch/zen-notch.css");'
MARKER = "/* Managed by zen-notch/install.py */"
BLOCK = f"{MARKER}\n{IMPORT}\n"
OWNER = "zen-notch installer v1\n"


def update(profile: Path, action: str) -> None:
    if not profile.is_dir() or not (profile / "prefs.js").is_file():
        raise ValueError("PROFILE must be an existing Zen profile containing prefs.js")
    chrome = profile / "chrome"
    target = chrome / "zen-notch"
    user_css = chrome / "userChrome.css"
    stylesheet = target / "zen-notch.css"
    owner = target / ".owner"
    for path in (chrome, target, user_css, stylesheet, owner):
        if path.is_symlink():
            raise ValueError(f"Refusing to modify symlink: {path}")
    text = user_css.read_bytes().decode("utf-8") if user_css.exists() else ""
    owned = owner.is_file() and owner.read_text(encoding="utf-8") == OWNER
    if target.exists() and not owned:
        raise ValueError(f"Refusing to overwrite an unmanaged directory: {target}")
    if IMPORT in text and BLOCK not in text:
        raise ValueError("Found an unmanaged zen-notch import; remove it manually first")

    if action == "install":
        # Imports must precede existing style rules and @namespace declarations.
        # A leading @charset must remain first when present.
        if BLOCK not in text:
            offset = 1 if text.startswith("\ufeff") else 0
            if text[offset:].lower().startswith("@charset "):
                end = text.find(";", offset)
                if end == -1:
                    raise ValueError("Malformed @charset in userChrome.css")
                offset = end + 1
                if text[offset:offset + 2] == "\r\n":
                    offset += 2
                elif text[offset:offset + 1] == "\n":
                    offset += 1
                else:
                    raise ValueError("Place @charset on its own line before installing")
            text = text[:offset] + BLOCK + text[offset:]
        target.mkdir(parents=True, exist_ok=True)
        owner.write_text(OWNER, encoding="utf-8")
        stylesheet.write_bytes(Path(__file__).with_name("zen-notch.css").read_bytes())
        user_css.write_bytes(text.encode("utf-8"))
        print(f"Installed in {chrome}")
        print("Set toolkit.legacyUserProfileCustomizations.stylesheets=true in about:config, then restart Zen.")
    else:
        if BLOCK in text:
            user_css.write_bytes(text.replace(BLOCK, "").encode("utf-8"))
        if owned:
            stylesheet.unlink(missing_ok=True)
            owner.unlink()
            # Never recursively remove a directory that may contain user files.
            if not any(target.iterdir()):
                target.rmdir()
        print("Uninstalled Splendid Notch. Restart Zen. Your stylesheet preference was left unchanged.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("--profile", required=True, type=Path)
    args = parser.parse_args()
    try:
        update(args.profile.expanduser(), args.action)
    except (OSError, ValueError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
