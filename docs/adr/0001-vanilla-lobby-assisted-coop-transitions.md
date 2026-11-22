---
status: accepted
---

# Vanilla lobby-assisted Stage Transitions in Co-op

In Solo play, Zombie Gauntlet performs an automatic direct level load (`ChangeLevel`) after a brief Stage Clear banner. In vanilla Steam 1.7 Co-op, we persist Run state in host server dvars and execute a lobby-assisted Stage Transition (`SetUINextLevel` + `exitLevel(false)`) that returns the connected party together to the Co-op lobby with the next stock map pre-selected for the host to launch.

## Considered Options

- **In-game `ChangeLevel()` in Co-op via third-party binary hooks (LinkerMod / T4M)**: Would allow uninterrupted in-game map loading in Co-op, but requires every player to patch their game binaries with third-party DLLs, violating our vanilla Steam 1.7 target.
- **Dedicated server with external rotation daemon**: Adds server hosting overhead and still disrupts standard Co-op listen-server play with friends.
- **Native lobby-assisted handoff (`SetUINextLevel` + `exitLevel(false)`)**: Matches Treyarch's own Co-op Campaign implementation in `raw/maps/_endmission.gsc`, keeps the party intact, persists host server dvars in process memory, and requires zero third-party binaries.

## Consequences

- Friends only need the standard mod folder—no DLL patches or custom server infrastructure.
- Co-op players experience a brief lobby hop between Stages where the host confirms launch (with the next map already queued).
- Host-process memory holds active Run state; if the host exits the lobby or closes the game, the Run ends and resets cleanly.
