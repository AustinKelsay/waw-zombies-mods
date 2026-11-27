# WaW Zombies Mods

Call of Duty: World at War (vanilla Steam 1.7) Nazi Zombies modding workspace, build tooling, modular Base Experience enhancements, and custom game modes.

## Agent skills

### Issue tracker

GitHub Issues in `AustinKelsay/waw-zombies-mods` via the `gh` CLI (native sub-issues, native `blocked_by` dependencies, and `/wayfinder` map/ticket labels). See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) plus `/wayfinder` labels (`wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`). See `docs/agents/triage-labels.md`.

### Domain docs & Art Direction

Multi-context layout anchored by `GLOSSARY-MAP.md` (`Shared Platform` root `GLOSSARY.md`, `Base Zombies` under `docs/contexts/base-zombies/`, `Zombie Gauntlet` under `docs/contexts/zombie-gauntlet/`, and system-wide ADRs under `docs/adr/`). See `docs/agents/domain.md`.

Canonical visual targets, mesh/material budgets, and WaW 1.7 rendering/HUD contracts live in `docs/art/` (`README.md`, `NORTHSTAR_SPEC.md`, `NORTHSTAR_EXPANSION_SPEC.md`, Sheets `01`–`11`) and are governed by `docs/contexts/base-zombies/docs/adr/0007-northstar-art-direction-and-visual-asset-contracts.md`. Read them before authoring or updating any custom 3D model, texture, PaP finish, trap prop, companion rig, or 2D HUD icon.

### Coding standards & verification

- Coding standards for WaW 1.7 GSC, `.menu` UI, and Python tooling: `CODING_STANDARDS.md`.
- End-to-end build, deploy, and live `CoDWaW.exe` verification runbook (`plebdev-ultra`, `/home/plebdev/Work/waw-zombies-mods`): `docs/verification.md`.
- Offline check (any machine): `python3 scripts/verify_e2e.py --offline-only`
- Full live gate (`plebdev-ultra`): `python3 scripts/verify_e2e.py`
