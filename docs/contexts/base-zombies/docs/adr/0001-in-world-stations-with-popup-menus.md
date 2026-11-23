---
status: accepted
---

# In-World Physical Stations with Clickable Menu Popups

Players purchase new Standard Perks, Perk Tier 2 upgrades, Apex Perks, Classes, Companions, and Special/Elemental Weapons at three physical in-world Stations spawned at curated landmarks on each Stock Map (plus native/spawned Pack-a-Punch), where pressing `Use` opens a clean clickable WaW `.menu` shop popup.

## Considered Options

- **Individual vending machines for every perk and class**: Stock `.d3dbsp` maps cannot add new geometry, and spawning 15+ separate machines crowds playable corridors and risks hitting WaW's entity and 400-FX limits.
- **Anywhere-anytime pause-menu shop**: Removes Zombies' core spatial risk-reward of navigating the map and holding a position to buy upgrades.
- **Three curated Stations with clickable `.menu` popups**: Preserves authentic Zombies map navigation and risk-reward, avoids tedious multi-tap cycling prompts, and works cleanly across Solo and Co-op on all four Stock Maps.

## Consequences

- Each Stock Map (starting with Der Riese as primary testbed) defines curated walkable landmark coordinates for the Specialty Perk Station, Class Altar, and Arsenal & Squad Station (plus a spawned Pack-a-Punch Station on Nacht der Untoten, Verrückt, and Shi No Numa).
- Station UIs use native WaW 1.7 `scriptMenuResponse` handlers so purchases validate points and state server-side in both Solo and Co-op.
