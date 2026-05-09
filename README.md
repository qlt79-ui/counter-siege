# COUNTER SIEGE — Tactical FPS
### A Counter-Strike Inspired Game with LAN Multiplayer

---

## REQUIREMENTS
- Python 3.8 or higher  →  https://python.org
- pip packages: `opencv-python`, `numpy`

Install dependencies once:
```
pip install opencv-python numpy
```

---

## HOW TO LAUNCH

### Windows
Double-click `launch.bat`  
*(it auto-installs dependencies if missing)*

### Mac / Linux
```bash
chmod +x launch.sh
./launch.sh
```

### Direct Python
```bash
python3 counter_siege.py
```

---

## LAN MULTIPLAYER

### Hosting a game
1. Run the game → choose **Host LAN Game**
2. Your LAN IP is shown top-left of the screen (e.g. `192.168.1.5`)
3. Share that IP with friends on the same network
4. Port used: **7777** (TCP) — open it in your firewall if needed

### Joining a game
1. Run the game → choose **Join LAN Game**
2. Enter the host's IP address
3. Choose your team and name

### Command-line shortcuts
```bash
# Host
python3 counter_siege.py --host --name YourName --team CT

# Join
python3 counter_siege.py --join 192.168.1.5 --name YourName --team T

# Solo vs bots
python3 counter_siege.py --solo --name YourName --team CT
```

---

## CONTROLS

| Key | Action |
|-----|--------|
| W / A / S / D | Move |
| Mouse | Look / Aim |
| Left Click | Shoot |
| Right Click | ADS (aim down sights) |
| R | Reload |
| E | Plant C4 / Defuse bomb |
| G | Throw best grenade |
| B | Open buy menu |
| 1–5 | Switch weapon slot |
| C | Crouch (reduces spread) |
| Tab | Scoreboard |
| ESC | Quit |

**In buy menu:** Press 1–9 to buy corresponding item

---

## GAME MECHANICS

### Round System
- 30 rounds total, halftime at 15
- **Buy phase** (15 sec) at round start — spend money on weapons/armor
- **Live phase** (115 sec) — fight!
- Bomb planted → 40 second countdown

### Economy
| Event | Reward |
|-------|--------|
| Kill | +$300 |
| Round win | +$3,250 |
| Round loss | +$1,400 |
| Start money | $800 |
| Max money | $16,000 |

### Win Conditions (Terrorists)
- Plant C4 at **A-site** or **B-site** and let it explode
- Eliminate all Counter-Terrorists

### Win Conditions (Counter-Terrorists)
- Defuse the bomb (hold E near bomb for 10 sec)
- Eliminate all Terrorists before bomb plants
- Let the timer run out

### Weapons Available
**Pistols:** Glock-18, USP-S, P250, Desert Eagle  
**Rifles:** AK-47, M4A1-S, SG 553  
**SMGs:** MP5-SD  
**Snipers:** AWP  
**Grenades:** HE Grenade, Flashbang, Smoke Grenade  
**Equipment:** Kevlar, Kevlar + Helmet  
**Melee:** Knife (always available)

### Map
- **A-site** — top-right of map
- **B-site** — bottom-left of map
- Cover boxes scattered throughout
- Color-coded minimap (bottom-right)

---

## NOTES
- Mouse sensitivity can be adjusted in `counter_siege.py` → `self.sensitivity = 0.002`
- Resolution is 1280×720 by default — change `W, H` at top of script
- Bot AI included in Solo mode (4v4 with bots)
- Max 10 players on LAN

---

*Built with Python + OpenCV raycasting engine. No extra game engine required.*
