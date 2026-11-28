# Zombie Gauntlet

Endless multi-map Nazi Zombies progression mode built on Enhanced Mode, in which a squad plays through shuffled passes of all four Stock Maps with continuously climbing rounds until team wipe.

## Language

### Game Mode

**Zombie Gauntlet** (short: **Gauntlet**):
The unified endless Nazi Zombies progression mode combining Enhanced Mode with shuffled four-map Stage transitions and continuously escalating rounds until team wipe.
_Avoid_: Classic Gauntlet, Enhanced Gauntlet, Roguelike mode, Campaign mode, World Tour, Circuit

### Progression Structure

**Run**:
One complete Zombie Gauntlet attempt from Cycle 1, Stage 1 until all players are downed and eliminated or the host disbands the lobby.
_Avoid_: Match, Session, Game

**Cycle**:
One complete pass through all four Stock Maps in a freshly shuffled order (Cycle 1 opens on Nacht der Untoten and shuffles Stages 2–4; Cycle 2+ shuffles all four maps without repeating the previous Cycle's final map first).
_Avoid_: Lap, Loop, Tier, Rotation

**Stage**:
A single map visit within a Cycle, defined by its Stock Map, continuous starting round, and randomized Stage Span.
_Avoid_: Leg, Map run, Level, Round set

**Stage Span**:
The randomized number of rounds a Stage lasts before triggering a Stage Transition (4–6 rounds, averaging 5), kept hidden on the HUD for suspense.
_Avoid_: Stage length, Round band, Stage duration

**Target Round**:
The hidden round number (derived from the Stage's starting round and Stage Span) that a squad must complete to clear the current Stage and trigger a Stage Transition.
_Avoid_: Goal round, Cap round, End round

### Stage Lifecycle & Economy

**Prep Phase**:
A timed grace window at the start of any Stage after Stage 1 during which zombies do not spawn, allowing players to open doors, acquire weapons, and buy perks before high-round combat begins.
_Avoid_: Grace period, Warmup, Intermission

**Points Floor**:
The minimum points balance guaranteed to each player at the start of a Stage, scaled to that Stage's starting round, applied whenever their carried-over points fall below it.
_Avoid_: Stipend, Starting cash, Bonus points

**Stage Clear**:
The moment the final enemy of a Stage's Target Round is eliminated, locking in player points and active perks and initiating a Stage Transition.
_Avoid_: Map win, Level clear, Round cap hit

**Stage Transition**:
The handoff from a cleared Stage to the next Stage in the Run, persisting Run state across maps (automatic level load in Solo, or lobby-assisted handoff with the next map pre-selected in Co-op).
_Avoid_: Map swap, Level change, Map switch

**Run Summary**:
The end-of-Run overlay displayed on team wipe reporting the final Cycle, Stage and map reached, final round, and total rounds cleared across the Run.
_Avoid_: Game over screen, Scoreboard, End card
