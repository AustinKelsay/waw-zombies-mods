# WaW Zombies Mods

Custom Nazi Zombies game modes and modding workspace for Call of Duty: World at War (vanilla Steam 1.7).

## Language

### Game Modes

**Zombie Gauntlet** (short: **Gauntlet**):
A standalone endless Nazi Zombies game mode in which a squad plays through all four stock maps in escalating round-band passes until team wipe.
_Avoid_: Roguelike mode, Campaign mode, World Tour, Circuit

**Classic Mode**:
Standard, unmodified World at War Nazi Zombies gameplay on any individual stock map when Zombie Gauntlet is disabled.
_Avoid_: Vanilla mode, Normal mode, Default mode

### Progression Structure

**Run**:
One complete Zombie Gauntlet attempt from Cycle 1, Stage 1 until all players are downed and eliminated or the host disbands the lobby.
_Avoid_: Match, Session, Game

**Cycle**:
One complete chronological pass through all four stock maps (Nacht der Untoten, Verrückt, Shi No Numa, Der Riese) at a fixed starting and target round band.
_Avoid_: Lap, Loop, Tier, Rotation

**Stage**:
A single map visit within a Cycle, defined by its stock map, starting round, and Target Round.
_Avoid_: Leg, Map run, Level, Round set

**Target Round**:
The round number that a squad must complete to clear the current Stage and trigger a Stage Transition.
_Avoid_: Goal round, Cap round, End round

### Stage Lifecycle & Economy

**Prep Phase**:
A timed grace window at the start of any Cycle 2+ Stage during which zombies do not spawn, allowing players to open doors, acquire weapons, and buy perks before high-round combat begins.
_Avoid_: Grace period, Warmup, Intermission

**Points Floor**:
The minimum points balance guaranteed to each player at the start of a Stage, scaled to that Stage's starting round, applied whenever their carried-over points fall below it.
_Avoid_: Stipend, Starting cash, Bonus points

**Stage Clear**:
The moment the final enemy of a Stage's Target Round is eliminated, locking in player points and initiating a Stage Transition.
_Avoid_: Map win, Level clear, Round cap hit

**Stage Transition**:
The handoff from a cleared Stage to the next Stage in the Run, persisting Run state across maps (automatic level load in Solo, or lobby-assisted handoff with the next map pre-selected in Co-op).
_Avoid_: Map swap, Level change, Map switch

**Run Summary**:
The end-of-Run overlay displayed on team wipe reporting the final Cycle, Stage and map reached, final round, and total rounds cleared across the Run.
_Avoid_: Game over screen, Scoreboard, End card
