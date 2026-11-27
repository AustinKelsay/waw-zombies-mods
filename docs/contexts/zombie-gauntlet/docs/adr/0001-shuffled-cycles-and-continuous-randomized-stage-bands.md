---
status: accepted
---

# Shuffled Cycles and Continuous Randomized Stage Bands

Zombie Gauntlet replaces fixed chronological map loops and per-Stage Round 1 resets with two progression rules designed to maximize run-to-run novelty and late-game pacing while staying 100% pure GSC within WaW 1.7 engine limits:

1. **Shuffled Map Order per Cycle**: Cycle 1 opens on **Nacht der Untoten** (Stage 1) and shuffles the remaining three Stock Maps (Verrückt, Shi No Numa, Der Riese) into Stages 2–4. Every subsequent Cycle (Cycle 2+) shuffles all four Stock Maps with a **no-repeat boundary rule** ensuring Stage 1 of Cycle `N+1` never repeats Stage 4 of Cycle `N`.
2. **Continuous Round Escalation with Randomized Stage Spans**: Instead of resetting to Round 1 on each map in Cycle 1 or repeating fixed round bands, rounds climb continuously across Stages. Each Stage rolls a randomized **Stage Span** of **4–6 rounds** (uniform integer in `[4, 6]`, averaging **5 rounds** per Stage — inspired by Hellhound round spacing), persisted for the active Stage. Every transition after Stage 1 starts at `previous_target_round + 1` with the round-scaled Points Floor and Prep Phase active. The persistent HUD hides the exact Target Round so Stage Transitions preserve Hellhound-style suspense.

## Considered Options

- **Keep fixed chronological order (`Nacht -> Verruckt -> Sumpf -> Der Riese`) and fixed round bands (`1–10` × 4, `10–15` × 4)**: Makes every Run play identically and causes severe early-game drag under unified Enhanced Gauntlet, since players carry Classes, Perks, and Elemental PaP weapons back into Round 1 three extra times during Cycle 1 and must play ~60+ total rounds before reaching Round 15.
- **Shuffle all 4 Stock Maps on Cycle 1 Stage 1**: WaW 1.7 `.menu` scripts cannot run an RNG shuffle before launching the first map in Solo or Co-op Host Setup, so shuffling Stage 1 would require an awkward extra mid-load map redirect on Round 1 in Co-op lobbies. Opening Cycle 1 on Nacht der Untoten provides a clean 4–6 round warm-up and zero extra map reloads, while shuffling Stages 2–4 and all 4 maps in Cycle 2+.
- **Wider Stage Span (`3–7` rounds) or visible exact Target Round**: A 3-round Stage can feel cut short before players finish opening doors, while a 7-round Stage drags on tight maps; `4–6` rounds averages 5 cleanly with tight variance. Hiding the exact Target Round on the HUD keeps each later round tense without cluttering the HUD.

## Consequences

- **Run state persistence**: `maps\_gauntlet_state` persists the active Cycle's shuffled map sequence, the current Stage's `start_round`, and the rolled `target_round` across Solo and lobby-assisted Co-op transitions, clearing all of them on Team Wipe or Run Reset.
- **Cycle 1 post-Stage-1 Prep Phase & scaling**: Because Stage 2 of Cycle 1 now begins around Rounds 5–7 (and Stages 3–4 climb into Rounds 10–20+), high-round start seeding, Points Floor, Hellhound rescheduling, and Prep Phase apply on **every Stage where `start_round > 1`**, not only Cycle 2+.
- **Deterministic testability**: Offline tests and live E2E harnesses (`verify_cycle1.py`, `verify_cycle2.py`, `verify_coop.py`) retain explicit test-only dvar overrides for stage order and target round so CI/E2E runs remain deterministic while normal play uses true runtime randomness.
