# CS 1.6 Clone

Faithful Counter-Strike 1.6 recreation in Python.

## Install (one-time)
```
pip install opencv-python numpy
```
Sounds (optional): `pip install sounddevice`

## Run
- **Windows:** Double-click `launch.bat`
- **Mac/Linux:** `./launch.sh`
- **Direct:** `python3 cs16_clone.py`

## LAN Multiplayer
- **Host:** Select "Host LAN Game" — your IP shows top-left of screen
- **Join:** Select "Join LAN Game" → enter host IP
- **Port:** 7777 TCP (open in firewall if needed)

## Controls
| Key | Action |
|-----|--------|
| WASD | Move |
| Mouse | Look (infinite turn) |
| Left Click | Shoot |
| Right Click / F | Zoom (AWP scope) |
| R | Reload |
| G | Throw grenade |
| E (hold) | Plant C4 / Defuse bomb |
| B | Buy menu |
| 1–5 | Switch weapon |
| Shift | Walk (silent) |
| Ctrl | Crouch (tighter spread) |
| Tab | Scoreboard |
| ESC | Quit |

## CS 1.6 Mechanics Included
- Textured walls, floor, ceiling (raycasting engine)
- Exact weapon recoil spray patterns (AK-47, M4A1, MP5, FAMAS, SG-552)
- Hitboxes: head / body / legs with CS 1.6 damage multipliers
- Armor absorption (kevlar + helmet)
- 15 weapons: AK, M4, AWP, Scout, FAMAS, SG-552, SG-550, MP5, TMP, MAC-10, Deagle, USP, Glock, P228, Five-SeveN
- Grenades: HE, Flashbang, Smoke, Molotov
- Defuse kit (halves defuse time)
- Economy: win/loss bonus, escalating loss bonus, plant bonus
- Buy phase (15s), live phase (115s), planted countdown (40s)
- Bomb plant (3.2s) / defuse (10s, 5s with kit)
- de_dust2 map layout
- A-site + B-site
- 30 round match with CT/T scoring
- Bot AI (5v5 with bots in solo mode)
- Footstep sounds, gunshot synthesis, bomb ticking
- Damage direction indicators
- Kill feed, scoreboard, minimap
- Flash blindness, smoke vision block, molotov fire damage
- LAN multiplayer (host/join over TCP)
