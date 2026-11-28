# End-to-End Verification Runbook (`waw_gauntlet`)

This runbook documents how operators and agents run the automated verification quality gate for **Zombie Gauntlet** and **Classic Mode** across all four stock Call of Duty: World at War Nazi Zombies maps (`nazi_zombie_prototype`, `nazi_zombie_asylum`, `nazi_zombie_sumpf`, `nazi_zombie_factory`).

---

## Quick Commands

### Full hands-off quality gate (`plebdev-ultra`)

Runs offline contract tests, compiles and deploys `mod.ff` + `waw_gauntlet.iwd`, and executes every in-engine Steam/Proton scenario sequentially:

```sh
python3 scripts/verify_e2e.py
```

### Fast offline check (dev laptops without Steam/Proton/WaW)

Runs only the pure Python unit and GSC contract tests:

```sh
python3 scripts/verify_e2e.py --offline-only
```

### Common operator flags

| Command | Purpose |
| --- | --- |
| `python3 scripts/verify_e2e.py --list-stages` | Print all configured gate stages, commands, and script presence, then exit `0`. |
| `python3 scripts/verify_e2e.py --skip-build` | Skip `build-deploy` and reuse already-built `dist/waw_gauntlet/` artifacts. |
| `python3 scripts/verify_e2e.py --only solo-cycle1 solo-cycle2` | Run only the named stage IDs (always executed in canonical gate order). |
| `python3 scripts/verify_e2e.py --include-visual-tour` | Append the optional 14th stage (`bz-visual-tour`, 4-map screenshot capture; requires ImageMagick `import`). |
| `python3 scripts/verify_e2e.py --visual-out-dir /tmp/bz_visuals --include-visual-tour` | Redirect visual tour PNG captures and manifest output (default: `.smoke_logs/bz_coop_and_visuals`). |
| `python3 scripts/verify_e2e.py --continue-on-error` | Keep running remaining stages after a failure so every broken scenario surfaces in one pass (still exits `1`). |
| `python3 scripts/verify_e2e.py --allow-missing-scripts` | Mark not-yet-merged stage scripts as `SKIPPED` instead of failing strict gate mode. |
| `python3 scripts/verify_e2e.py --json-report .smoke_logs/e2e_report.json` | Emit a structured JSON summary with timestamps, durations, exit codes, and diagnostics. |

> **Fail-fast default:** Without `--continue-on-error`, `verify_e2e.py` stops immediately on the first failed stage (such as broken offline tests or a failed linker build) and marks remaining stages `NOT_RUN`.
> **Strict script presence default:** Without `--allow-missing-scripts`, any missing verification script fails the gate cleanly so incomplete branches cannot report a false green.

---

## Stage-by-Stage Gate Breakdown

| # | Stage ID | Command | What It Verifies | Issue #1 / #9 Coverage |
| --- | --- | --- | --- | --- |
| 1 | `offline-tests` | `python3 -m unittest discover -s tests -v` | Pure-logic Gauntlet Rules math (Cycles 1–10, Points Floor, Prep Phase, stock zombie HP/speed/spawn decay), host dvar persistence round-trips, `build_mod.py` hook injection & no-`foreach` lint, and log analyzer contracts. | Issue #1 Seam 1; Issue #9 AC #1 |
| 2 | `build-deploy` | `python3 scripts/build_mod.py --deploy` | Extracts era-specific stock map + `_zombiemode.gsc` scripts, injects `gauntlet_enabled`-gated hooks, compiles `dist/waw_gauntlet/mod.ff` via `linker_pc.exe`, packages `waw_gauntlet.iwd`, and deploys to Steam AppData. | Issue #9 AC #1 |
| 3 | `classic-gauntlet-smoke` | `python3 scripts/smoke_verify.py --skip-build --modes 0 1` | Boots all 4 stock maps in **Classic Mode** (`gauntlet_enabled 0`) and **Zombie Gauntlet** (`gauntlet_enabled 1`), asserting `mod.ff` loads with zero 400-FX or script errors and emits `GAUNTLET_EVENT\|MOD_LOADED` (and `GAUNTLET_READY` when enabled). | Issue #9 AC #5 (Classic Mode non-regression) |
| 4 | `solo-cycle1` | `python3 scripts/verify_cycle1.py --skip-build` | Continuous Solo Run across a shuffled 4-map Cycle 1 order + no-repeat Cycle 2 Stage 1 wrap verifying continuous round escalation (`R1 -> R2 -> R3 -> R4 -> R5`), `STAGE_INIT`, `STAGE_CLEAR`, Solo `ChangeLevel` `STAGE_TRANSITION`, and Points Floor carryover. | Issue #105 (GPO-T3) |
| 5 | `solo-cycle2` | `python3 scripts/verify_cycle2.py --skip-build` | Cycle 1→2 (`R9 -> R10`) and Cycle 2→3 (`R14 -> R15`) wraps, high-round zombie health (`950` at R9, `1045` at R10, `1527` at R14, `1679` at R15) and sprint speed without double-scaling, Hellhound round rescheduling on Der Riese, **Points Floor** top-up vs surplus preservation (`8500 > 5000`), and **Prep Phase** spawn hold ordering. | Issue #105 (GPO-T3) |
| 6 | `coop-transition` | `python3 scripts/verify_coop.py --skip-build` | Co-op lobby-assisted **Stage Transition** (`SetUINextLevel` + `exitLevel` + persisted host dvars including dynamic shuffled next map) and squad roster recovery rules (spectators, late joiners, reconnectors). | Issue #105 (GPO-T3) |
| 7 | `team-wipe` | `python3 scripts/verify_wipe.py --skip-build` | Team wipe detection, **Run Summary** telemetry/overlay emission, and complete Run dvar reset (including `gauntlet_cycle_order`, `gauntlet_start_round`, `gauntlet_target_round`) so the next Run begins cleanly at Cycle 1, Stage 1, Round 1. | Issue #9 AC #4; #105 |
| 8 | `hud-menus` | `python3 scripts/verify_hud_menus.py --skip-build` | Persistent Gauntlet corner HUD overlay (`GAUNTLET - C<cycle> S<stage>/4`, hidden Target Round per Gauntlet ADR-0001) and 3-mode Solo / Co-op menu contracts (Classic Mode, Enhanced Mode, unified Zombie Gauntlet per ADR-0006). | Issues #100, #105 |
| 9 | `perk-carryover` | `python3 scripts/verify_perks.py --skip-build` | Cross-map Perk Carryover (Der Riese R9 → Cycle 2 Nacht der Untoten R10 with Juggernog `160` HP and stock perk HUD icons) plus Classic Mode isolation. | ADR-0004, ADR-0006 |
| 10 | `base-zombies-p1` | `python3 scripts/verify_base_zombies_p1.py --skip-build` | Der Riese Enhanced Mode Phase 1 live self-test (4 Stations, Perks + Tier 2 + Apex, 6 Classes, Pack-a-Punch Expansion, down-reset persistence boundary, HUD cleanup) plus Classic Mode (`bz_enabled 0`) isolation. | Issue #18 (P1-T7) |
| 11 | `base-zombies-p2` | `python3 scripts/verify_base_zombies_p2.py --skip-build` | Der Riese Enhanced Mode Phase 2 live self-test (4 zero-FX cloned primaries in Mystery Box + Arsenal + Mule Kick II 4-slot, Wunderwaffe DG-2 Juggernog/Titan 440 HP fix & 3.5s stun, Enhanced Flamethrower melt + % burn DOT, Acid Sprayer slow + 1.5x brittle, Cryo Cannon freeze + 2.5x shatter, War Club Bowie swap + PaP AOE smash, Multi-Crossbow 3 sticky bolts, Blade Boomerang flight/return, Portal Grenade spawn warp & zombie exclusion) plus Classic Mode (`bz_enabled 0`, `bz_elements_enabled 0`) isolation. | Issue #27 (P2-T5) |
| 12 | `bz-coop` | `python3 scripts/verify_bz_coop_and_visuals.py --skip-build --mode coop` | Single-map Enhanced Mode Co-op self-test on Der Riese (build parity telemetry, native Pack-a-Punch console Double PaP, Hellhound scaling/floor checks; requires `xdotool` or `python-xlib`). | Issues #45, #53 |
| 13 | `enhanced-gauntlet` | `python3 scripts/verify_bz_coop_and_visuals.py --skip-build --mode enhanced-gauntlet` | Unified Zombie Gauntlet run (launched with `gauntlet_enabled=1` alone to verify ADR-0006 auto-coupling) through all four Cycle 1 handoffs into Cycle 2 Nacht, verifying Class, War Club + PaP War Club, Perks, Elemental Weapons + PaP tiers, Der Riese stations, and Team Wipe cleanup. | Issues #51, #100, #105 |
| 14 | `bz-visual-tour` *(optional)* | `python3 scripts/verify_bz_coop_and_visuals.py --skip-build --mode visual-tour --capture-visuals <dir>` | Optional 4-map visual tour (40 PNGs: stations in both Verrückt wings and on the other Stock Maps, Elemental Weapons, native PaP II, War Club smash, Portal Grenade, and all 4 open Station menus; enabled via `--include-visual-tour` or `--only bz-visual-tour`; requires ImageMagick `import`). | Issues #52, #53, #60 |

---

## Logs and Reports

- **Per-scenario engine logs (gitignored):** saved automatically under `.smoke_logs/` at repo root:
  - `.smoke_logs/<map>_gauntlet0.console.log` and `.smoke_logs/<map>_gauntlet1.console.log` (smoke verification)
  - `.smoke_logs/cycle1_solo_4map.console.log` (Solo Cycle 1 4-map run)
  - `.smoke_logs/cycle2_s1_c1_to_c2_wrap.console.log`, `cycle2_s2_surplus_preservation.console.log`, `cycle2_s3_c2_to_c3_wrap.console.log` (Cycle 2+ scaling, surplus, and Prep Phase)
  - Additional per-scenario logs written by `verify_coop.py`, `verify_wipe.py`, and `verify_hud_menus.py`
- **Live WaW console log inside the playtest Proton prefix:**
  - `~/Games/waw-zombies-dev/playtest/pfx/drive_c/users/steamuser/AppData/Local/Activision/CoDWaW/mods/waw_gauntlet/console.log`
  - Fallback before mod mount: `.../CoDWaW/main/console.log`
- **Structured JSON reports (`--json-report <path>`):**
  - Schema v1 containing `status`, `exit_code`, `started_at`, `finished_at`, `total_duration_s`, `options`, `summary` (`total`, `passed`, `failed`, `skipped`, `not_run`), and per-stage entries (`stage_id`, `status`, `exit_code`, `duration_s`, `command`, `failure_reason`, `skip_reason`, `hints`, `output_tail`).

---

## Troubleshooting Checklist (`plebdev-ultra`)

### 1. Stale Wine / Proton processes or `mod.ff` locked by open WaW
- **Symptom:** `PermissionError`, `Text file busy`, `sharing violation`, or WaW failing to pick up a rebuilt `mod.ff` / `waw_gauntlet.iwd`.
- **Fix:** Close any running Steam World at War window and terminate lingering playtest Wine servers before re-running:
  ```sh
  pkill -f CoDWaW.exe || true
  WINEPREFIX="$HOME/Games/waw-zombies-dev/playtest/pfx" \
    "$HOME/.local/share/Steam/steamapps/common/Proton - Experimental/files/bin/wineserver" -k || true
  ```

### 2. `Xvfb` or `xfwm4` missing / X11 display locks exhausted
- **Symptom:** `FileNotFoundError: 'Xvfb'`, `Timed out waiting for Xvfb socket`, or `No free X11 display found in :110-:159`.
- **Fix:** Confirm both binaries are on `PATH` (`command -v Xvfb xfwm4`). If a previous crash left stale locks in `/tmp`, clean orphaned display locks (`rm -f /tmp/.X1[1-5][0-9]-lock /tmp/.X11-unix/X1[1-5][0-9]` when no Xvfb is running).

### 3. Missing playtest Proton prefix or uninitialized WaW profile
- **Symptom:** `Playtest AppData folder missing` or `Proton launcher not found`.
- **Fix:** Verify `plebdev-ultra` paths or set environment overrides (`WAW_STEAM_ROOT`, `WAW_DEV_ROOT`, `WAW_PROTON`). Ensure `~/Games/waw-zombies-dev/playtest` has a valid initialized WaW profile so first-run profile modals never block automated launches. On machines without Steam/Proton, run `python3 scripts/verify_e2e.py --offline-only`.

### 4. Safe Mode modal hang (`__CoDWaW` sentinel)
- **Symptom:** Scenario times out waiting for `GAUNTLET_EVENT|MOD_LOADED` with an empty or truncated `console.log`.
- **Fix:** The harnesses automatically delete `__CoDWaW` before launch, but if an interactive crash left one behind in another prefix, remove `<AppData>/CoDWaW/__CoDWaW` and inspect `.smoke_logs/*.console.log`.

### 5. `Exceeded limit of 400 'fx' assets`
- **Symptom:** Engine aborts loading a stock map (especially Der Riese or Shi No Numa) with a 400-FX error.
- **Fix:** Check `mod/mod.csv`. Per ADR-0003, `waw_gauntlet` must remain strictly script, UI menu, and localized-string only — never include custom FX, weapons, or models globally.

### 6. WaW 1.7 `foreach` GSC syntax trap
- **Symptom:** `script compile error` / `bad syntax` on map load, or `test_no_foreach_in_tracked_gauntlet_gsc_files` fails during `offline-tests`.
- **Fix:** Vanilla CoD:WaW 1.7 GSC does **not** support `foreach`. Replace any `foreach ( item in arr )` with an indexed `for ( i = 0; i < arr.size; i++ )` loop.

### 7. Incremental integration before all tickets merge
- **Symptom:** Strict gate fails with `Required verification script not found: scripts/verify_<name>.py`.
- **Fix:** During branch integration before Tickets #6/#7/#8 are all present, run with `--allow-missing-scripts` to verify all currently available stages; remove the flag for the final pre-ship quality gate.
