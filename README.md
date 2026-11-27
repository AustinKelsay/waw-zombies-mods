# WaW Zombies Mods (`waw_gauntlet`)

Unified vanilla Steam 1.7 Call of Duty: World at War Nazi Zombies mod package and automated build/verification tooling for **Zombie Gauntlet** alongside untouched **Classic Mode**.

See [GLOSSARY.md](GLOSSARY.md) for canonical terminology, [docs/adr/](docs/adr/) for architectural decisions, and [docs/art/](docs/art/) for the Council-locked **North Star Art Direction** (Sheets 01–11 covering all custom 3D weapons, stations, traps, PaP finishes, Phase 3 Companion rig, and 2D HUD icons).

## Prerequisites (`plebdev-ultra`)

- **Steam CoD:WaW (AppID `10090`, vanilla 1.7.1263)** installed at:
  `~/.local/share/Steam/steamapps/common/Call of Duty World at War`
- **Proton Experimental** installed at:
  `~/.local/share/Steam/steamapps/common/Proton - Experimental/proton`
- **Treyarch WaW Mod Tools build copy** + Wine/Proton build prefix + isolated playtest prefix at:
  - `~/Games/waw-zombies-dev/game` (Mod Tools + `bin/linker_pc.exe`)
  - `~/Games/waw-zombies-dev/compatdata` (linker/converter Proton prefix)
  - `~/Games/waw-zombies-dev/playtest` (isolated CoD:WaW playtest Proton prefix with an initialized profile)
- **Headless X11 tooling** for automated verification: `Xvfb`, `xfwm4`, and `xdotool` (or `python-xlib`) for the default 13-stage E2E gate (`bz-coop` / `enhanced-gauntlet`), plus ImageMagick's `import` when running the optional `--include-visual-tour` / `bz-visual-tour` screenshot stage (`python3` standard library otherwise; no extra pip packages required).

Environment overrides supported by `scripts/open_tool.sh`, `scripts/build_mod.py`, and `scripts/smoke_verify.py`:
`WAW_STEAM_ROOT`, `WAW_DEV_ROOT`, `WAW_PROTON`.

## Quick Start

### 1. Build and deploy `waw_gauntlet`

Compiles `dist/waw_gauntlet/mod.ff` via Treyarch's `linker_pc.exe` under Proton Experimental, packages `dist/waw_gauntlet/waw_gauntlet.iwd` (matching Treyarch Launcher's dual `mod.ff` + `<mod>.iwd` layout so stock map `.gsc` overrides take precedence over `<map>.ff`), and installs both into Steam's Proton prefix (`mods/waw_gauntlet/`):

```sh
python3 scripts/build_mod.py --deploy
```

Omit `--deploy` to build locally into `dist/waw_gauntlet/` without touching Steam's mods folder.

### 2. Automated in-engine smoke verification (all 4 stock maps)

Builds `mod.ff`, deploys it to both Steam's prefix and the isolated playtest prefix, launches real `CoDWaW.exe` under a headless `Xvfb` display for all four stock Nazi Zombies maps (`nazi_zombie_prototype`, `nazi_zombie_asylum`, `nazi_zombie_sumpf`, `nazi_zombie_factory`), and asserts each loads cleanly without 400-FX or script errors while emitting `GAUNTLET_EVENT|MOD_LOADED`:

```sh
python3 scripts/smoke_verify.py
```

Verify both Classic Mode (`0`) and Gauntlet Mode (`1`) boot cleanly:

```sh
python3 scripts/smoke_verify.py --modes 0 1
```

Per-map engine console logs are saved under `.smoke_logs/` (gitignored). The command exits `0` only if every assertion passes on every requested map.

### 3. Full end-to-end verification gate

Run the complete 13-stage default quality gate (offline contract tests, `mod.ff` + `waw_gauntlet.iwd` build/deploy, Classic & Gauntlet 4-map smoke, Solo Cycle 1/2+, Co-op transition, team wipe, HUD/menu checks, Perk Carryover, Base Zombies Phase 1 & Phase 2, Base Zombies Co-op self-test, and Enhanced Gauntlet carryover):

```sh
python3 scripts/verify_e2e.py
```

Add `--include-visual-tour` (requires ImageMagick `import`) to also run the optional 14th stage capturing the 4-map visual tour:

```sh
python3 scripts/verify_e2e.py --include-visual-tour
```

On dev laptops without Steam/Proton/WaW, run the offline suite only:

```sh
python3 scripts/verify_e2e.py --offline-only
```

See [docs/verification.md](docs/verification.md) for stage details, flags (`--skip-build`, `--only`, `--include-visual-tour`, `--visual-out-dir`, `--continue-on-error`, `--json-report`), log locations, and `plebdev-ultra` troubleshooting.

### 4. Manual Steam launch

Close World at War before rebuilding an active mod so the game reloads `mod.ff`. Then launch directly via Steam:

```sh
# Classic Mode (default: gauntlet_enabled 0)
steam -applaunch 10090 +set fs_game mods/waw_gauntlet +map nazi_zombie_prototype

# Zombie Gauntlet enabled
steam -applaunch 10090 +set fs_game mods/waw_gauntlet +set gauntlet_enabled 1 +map nazi_zombie_prototype
```

Or open **Mods** in the main menu, load `waw_gauntlet`, and start any stock Nazi Zombies map.

## Mod Layout & Architecture

- `mod/mod.csv`: Unified fastfile manifest (script-only; adds zero custom FX, weapons, or models to stay well under WaW's 400-FX limit).
- `mod/maps/_gauntlet_log.gsc`: Structured engine telemetry logger emitting `GAUNTLET_EVENT|<TYPE>|<k1=v1;k2=v2;...>` lines into `console.log` (`+set logfile 2`).
- `mod/maps/_gauntlet_bootstrap.gsc`: Unified mode gate (`gauntlet_enabled`, defaulting to `0`) and pre/post `_zombiemode::main` hook seam.
- **Stock-safe 4-map hooking**: Each of the four stock Nazi Zombies maps ships its own era-specific `maps/_zombiemode.gsc` (Nacht der Untoten lacks perks/dogs/DLC3 scripts; Verrückt lacks DLC2/DLC3 scripts; Shi No Numa and Der Riese have distinct weapon/blocker scripts and local `waw_solo_fov()` patches). At build time, `scripts/build_mod.py` extracts each map's installed stock entry script (`maps/nazi_zombie_<map>.gsc`) from its `.ff` fastfile and injects minimal pre/post hooks around `maps\_zombiemode::main(...)`, leaving each map's stock/patched `_zombiemode.gsc` 100% intact in Classic Mode.

## Authoring Tools Helper

Run Treyarch Mod Tools directly via `scripts/open_tool.sh`:

```sh
./scripts/open_tool.sh linker -language english -compress -cleanup -nopause -moddir waw_gauntlet mod </dev/null
./scripts/open_tool.sh converter -nopause
./scripts/open_tool.sh radiant
```
