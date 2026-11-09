# Splendid Notch

An experimental native Zen Mod (with an optional `userChrome.css` installation) for Zen's **Single Toolbar** layout. It styles the real address bar as a top-center notch with rounded lower corners. Clicking it or pressing Ctrl+L (Cmd+L on macOS) keeps it at the same top-center position and enlarges the field slightly, with native suggestions beneath it.

The notch is hidden until the pointer enters a **28px top-edge strip directly above the notch**, limited to the notch's width rather than the entire content region. It fades in and remains visible while hovered, keyboard-focused, showing suggestions, or reporting an open URL-bar popup. Ctrl+L/Cmd+L reveals it directly. Moving away after finishing interaction fades it out. Adjust `--zen-notch-reveal-distance` in `zen-notch.css` to change the threshold.

The invisible hover strip intercepts pointer events in that narrow area; outside it, the hidden notch lets clicks reach the webpage. The threshold is measured from the window top and may need adjustment with extra title bars/toolbars.

### Docked DevTools

While a docked DevTools iframe/splitter is present, hover still reveals the notch, but the trigger is restricted to the frame gutter directly above it (`--zen-notch-top`, normally about 8px) rather than extending 28px down over toolbox tabs. Move the pointer to the very top edge above the notch to reveal it. The visible notch remains interactive; moving away hides it unless it is in use. **Ctrl+L/Cmd+L** also works and is required if the top gutter has zero height. Closing or undocking DevTools restores the normal 28px trigger. This conservative rule applies window-wide, including when another tab owns the docked toolbox. Custom top offsets must stay within the frame gutter to avoid overlapping DevTools.

## Status and limitations

This is a prototype, not a visually verified or published Zen Mods package. Toolbar selectors were checked against Zen's upstream development source; your installed release may differ.

- On Zen versions supporting CSS anchor positioning, horizontal placement uses the actual rendered sidebar edge and the opposite window gutter to center over the content region. The same rule applies to hover and Ctrl+L, including right-side sidebars. Older versions fall back to `--zen-sidebar-width` or the configurable `--zen-notch-sidebar-width` (250px by default); that fallback may need manual adjustment. Confirm alignment after sidebar resizing in your installed release.
- The notch overlays the page rather than reserving space. The top offset may need adjustment for your title bar, bookmarks toolbar, or window controls.
- Compact mode, fullscreen, popup windows, and toolbar customization retain the native layout. This initial version does not implement an always-visible notch in compact mode.
- Split view uses the combined content region, not the active pane. An additional web/AI sidebar is not compensated for.
- The original address-bar slot has zero reserved height while the notch is active. The input remains in the document for keyboard focus; any remaining navigation buttons retain their own row height. Native spacing returns in modes where the notch is disabled.
- The notch and its inverse corners use `#131313` in dark mode and `#ebebed` in light mode, following Zen's UI color scheme. The corner radius follows Zen's theme; a dedicated two-layer shadow separates the notch from the webpage, including in no-padding mode. Custom frame colors may differ from these fixed background colors.
- Exact centering and appearance need testing in your Zen version before treating this as finished browser integration.

## Install in Zen's Mods list (recommended)

Requires GNU Make and Python 3.8+; no Python packages, downloads, or JavaScript loader are needed by the installer. This is a local installation, not a marketplace publication.

1. Open `about:profiles` and copy the **Root Directory** of your active profile.
2. **Quit all Zen windows using that profile.** Do not restart Zen until installation finishes.
3. From this repository, run:

   ```sh
   make install-mod PROFILE="/absolute/path/to/your/zen/profile"
   ```

4. Restart Zen, select **Single Toolbar**, and open **Settings → Zen Mods**. Look for **Splendid Notch (v0.1.0)** and its configuration button. Make sure mods are enabled globally.

The installer registers the stable ID from `manifest.json` in the profile's `zen-themes.json` and installs `chrome.css`, `preferences.json`, and `readme.md` under `chrome/zen-themes/<id>/`. Zen loads and manages the stylesheet; no `userChrome.css` import is needed for this mode.

### Migration and safety

- If installed with the old `make install`, the native installer removes **only its managed import** from `userChrome.css`, preventing double loading. It leaves the legacy files and unrelated CSS intact.
- Existing mods, their enabled states, and unrelated registry fields are preserved. Reinstallation preserves Splendid Notch's enabled/disabled state and saved settings.
- Before changing an existing registry, the installer saves a timestamped `zen-themes.json.backup-*` beside it and replaces the registry atomically. The selected profile may be a symlink (including symlinked parent directories); the installer resolves it to the real profile first. It refuses malformed registries, unmanaged destination collisions, symlinked managed files/directories inside that profile, and detected active profile locks. Keep Zen closed throughout the operation.
- The installer does not edit `prefs.js`, `user.js`, or Zen's generated `chrome/zen-themes.css`.
- Updates are manual: rerun `make install-mod` with Zen closed. Since this ID is not published, Zen's marketplace update check may report that it cannot find this mod. The **Import Mod** button is not the installation route for this private package.
- Native loading and settings integration are based on upstream Zen's format; they still require verification in your installed browser version.

### Native settings

The settings panel contains only toggles for always-visible mode, disabling shadows, and disabling animation. Sizing, spacing, and colors use the built-in stylesheet defaults rather than exposing CSS values as settings. Reduced-motion preferences always disable animation. Always-visible mode deliberately occupies the notch area even when DevTools is open; leave auto-hide enabled if that overlaps toolbox controls.

To uninstall, use Zen's **Remove** action, or quit Zen and run:

```sh
make uninstall-mod PROFILE="/absolute/path/to/your/zen/profile"
```

The command preserves unrelated files and saved preferences. It does not restore the old legacy import. After native installation, do not run `make install` unless you first remove the native mod; the two install modes should not be active together.

## Legacy CSS installation

This mode does not add a Mods-list entry or settings panel. It remains available for development.

1. In Zen, open `about:profiles` and find the **Root Directory** of the profile in use (not Local Directory).
2. Open `about:config` and set `toolkit.legacyUserProfileCustomizations.stylesheets` to `true`.
3. Close Zen, then run from this repository, replacing the example path:

   ```sh
   make install PROFILE="/absolute/path/to/your/zen/profile"
   ```

4. Restart Zen with **Single Toolbar** selected.

The installer adds a managed import at the start of `chrome/userChrome.css` (after an existing charset declaration) and copies the stylesheet to `chrome/zen-notch/zen-notch.css`. Existing CSS is preserved; repeat installation updates the mod without duplicating the import. It refuses unmanaged destination directories and symlinked targets. It does not edit `prefs.js` or `user.js`.

## Legacy CSS uninstall

Close Zen and run:

```sh
make uninstall PROFILE="/absolute/path/to/your/zen/profile"
```

Restart Zen. Only the managed import and installed mod files are removed; other CSS and extra files are retained. The stylesheet preference is intentionally left unchanged because other mods may need it. An empty `userChrome.css` may remain after uninstall.

## Customize

For native installation, prefer the mod's configuration panel; saved settings override matching stylesheet defaults. For legacy installation, edit the variables at the top of `zen-notch.css`, then run `make install` again and restart Zen:

| Variable | Default | Purpose |
| --- | --- | --- |
| `--zen-notch-width` | `840px` | Maximum notch width |
| `--zen-notch-height` | `68px` | Idle field height |
| `--zen-notch-focused-width` | `1000px` | Maximum focused notch width |
| `--zen-notch-focused-height` | `80px` | Focused field height |
| `--zen-notch-padding-inline` | `24px` | Input content padding on each side, idle and focused |
| `--zen-notch-radius` | Zen content-container radius, or `14px` | Bottom corner radius |
| `--zen-notch-shoulder-radius` | `18px` | Inverse top-corner radius |
| `--zen-notch-top` | Zen element separation, or `8px` | Offset from window top |
| `--zen-notch-sidebar-width` | Zen sidebar width, or `250px` | Sidebar compensation; override if misaligned |
| `--zen-notch-color-light` | `#ebebed` | Light-mode background |
| `--zen-notch-color-dark` | `#131313` | Dark-mode background |
| `--zen-notch-background` | Light/dark color variables | Shared notch and inverse-corner background |
| `--zen-notch-shadow` | Two-layer shadow, stronger in dark mode | Visible side/bottom shadow; use `none` to disable |
| `--zen-notch-animation-duration` | `220ms` | Expand/collapse duration |
| `--zen-notch-animation-easing` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | Expand/collapse easing |

The notch animates its width and input height while staying centered. The suggestions list retains native content-driven height (it does not animate to/from `auto`). Reduced-motion preferences disable the transition. Rounded lower corners and concave top shoulders are retained in focused/open states. The shoulders use the same light/dark background as the notch.

## Validation

```sh
make test
```

Tests cover legacy/native installer round trips, the real native package, registry and stylesheet preservation, migration, enabled-state preservation, backups, corrupt registries, unmanaged collisions, symlinks, persistent and active profile locks, and files added after installation. They do not validate browser rendering or the live settings UI.

Manual browser checks still required: page-relative alignment, sidebar resizing and right-side layout, clicking the field, Ctrl+L, Escape, suggestions, site permissions, narrow windows, fullscreen video, and compact mode.
