# Coding Standards

Documented engineering standards for Call of Duty: World at War (vanilla Steam 1.7) GSC scripts, UI menus, and Python build/verification tooling in `AustinKelsay/waw-zombies-mods`.

---

## 1. WaW 1.7 GSC Scripting

- **No `foreach` syntax:** Vanilla CoD:WaW 1.7 GSC does not support `foreach`. Always use indexed loops (`for ( i = 0; i < arr.size; i++ )`). Enforced by offline tests.
- **`endon()` thread-scope safety:** In WaW 1.7 GSC, `entity endon( "event" )` binds to the **calling thread**, not function scope. Never put `player endon( "disconnect" )` inside a function called synchronously from engine lifecycle threads (`round_start()`, `round_think()`, `main()`). Wrap per-player waits in a dedicated child thread (`level thread ...` or `player thread ...`).
- **Self-`notify` ordering:** Firing `notify( "evt" )` immediately aborts the calling thread if that thread holds a matching `endon( "evt" )`. Always complete state cleanup and emit telemetry **before** firing the terminating `notify`.
- **Era-specific Stock Map parity:** Never assume all four Stock Maps share one `_zombiemode.gsc` or script tree:
  - `nazi_zombie_prototype` (Nacht) lacks `_zombiemode_perks.gsc`, Pack-a-Punch, and Hellhounds.
  - `nazi_zombie_prototype`, `nazi_zombie_asylum`, and `nazi_zombie_sumpf` call `end_game()` directly instead of listening on `level waittill( "end_game" )` (unlike `nazi_zombie_factory`).
  - `nazi_zombie_sumpf` and `nazi_zombie_factory` define local `waw_solo_fov()` patches inside `_patch.ff`.
  - Patch stock scripts minimally at build time via `scripts/build_mod.py` from installed `.ff` / `_patch.ff` archives so stock behavior stays 100% intact.
- **Strict Classic Mode isolation:** Every custom behavior must sit behind an explicit dvar Feature Gate (defaulting to `0` / Classic Mode when unset) and produce zero side effects or HUD artifacts when disabled.
- **HUD discipline:**
  - Use ASCII-safe strings for `SetText()` (WaW's bitmap font renders non-ASCII punctuation like `·` or `ü` inconsistently).
  - Track every created `NewHudElem()` / `NewClientHudElem()` and guarantee destruction on Stage Transition, wipe, and player disconnect with zero leaks.
- **400-FX asset ceiling:** Stay well below WaW's hardcoded 400-FX asset cap across all four Stock Maps (especially Der Riese and Shi No Numa). Do not pull unnecessary FX, weapons, or models into `mod.csv`.
- **Structured telemetry:** Emit deterministic `GAUNTLET_EVENT|<TYPE>|<k=v;...>` lines (or feature-prefixed structured events) via `maps\_gauntlet_log` for automated `console.log` verification.

---

## 2. WaW 1.7 UI Menus (`mod/ui/`)

- Override only the minimal stock menus needed via `mod/ui/patch_menus.txt` rather than recompiling all 40+ stock menus in `ui/menus.txt`.
- Patch stock menus (`main.menu`, `levels.menu`, `xboxlive_lobby.menu`, `systemlink_lobby.menu`) at build time from `tools_root/raw/ui/` and validate balanced braces before linking.
- Any menu reset macro must clear every real persisted dvar (never leave dead/unused dvar names in menu `exec` strings).
- Never attempt `SetDvar( "ui_mapname", ... )` from GSC (forbidden by WaW 1.7 engine); use native `SetUINextLevel()` in GSC and dvar bindings in `.menu` files.

---

## 3. Python Build & Verification Tooling

- **Python 3 standard library only:** Zero third-party `pip` dependencies in `scripts/` and `tests/`.
- **Testable seams:** Separate pure logic (GSC/menu patchers, log parsers, log analyzers, stage planners, diagnosis rules) from `subprocess` / `CoDWaW.exe` execution so every contract runs offline in milliseconds.
- **Offline GSC contract tests:** Execute real `.gsc` source files through `tests/gsc_runtime.py` using independent worked-example literals (no tautological assertions mirroring implementation formulas).
- **Atomic deployments & clean Wine teardown:** Write built `mod.ff` and `.iwd` artifacts atomically via temporary staging files, and always terminate playtest Wine prefixes with `wineserver -k` followed by `wineserver -w` before launching the next scenario.

---

## 4. Workflow & Quality Gates

- Use canonical vocabulary from `GLOSSARY-MAP.md` and each context's `GLOSSARY.md` across issues, branches, scripts, HUD strings, and tests.
- Follow TDD (red → green) for rules, persistence, patchers, and log analyzers.
- Run the full quality gate (`python3 scripts/verify_e2e.py`) on `plebdev-ultra` and a two-axis `/code-review` (Standards + Spec) before merging to `main`.
