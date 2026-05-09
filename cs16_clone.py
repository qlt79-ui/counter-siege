#!/usr/bin/env python3
"""
CS 1.6 CLONE — Counter-Siege 1.6
Faithful recreation of Counter-Strike 1.6 mechanics and visual style.

Install deps (one-time):
    pip install opencv-python numpy

Controls:
  WASD=move  Shift=walk  Ctrl=crouch  Space=jump
  Mouse=look  LMB=shoot  RMB=zoom(AWP)
  R=reload  G=grenade  E=plant/defuse
  B=buy  1-5=weapons  Tab=scoreboard  ESC=quit
"""

import cv2, numpy as np, math, time, random, socket, threading
import struct, json, argparse, sys, os, platform
from collections import defaultdict, deque

try:
    import sounddevice as sd
    AUDIO = True
except:
    AUDIO = False

W, H     = 1280, 720
HALF_H   = H // 2
FOV      = math.pi / 3
MAX_DEPTH= 24
PORT     = 7777
PI2      = math.pi * 2
TEX_SIZE = 64

PAL = dict(
    sky      =(130,100, 60), sky2    =( 80, 55, 30),
    fl_light =( 55, 50, 45), fl_dark =( 38, 34, 30),
    white    =(255,255,255), green   =(  0,200, 80),
    red      =(  0, 50,220), yellow  =(  0,220,220),
    gray     =(150,150,150), dgray   =( 60, 60, 60),
    ct_blue  =(210,130, 30), t_gold  =( 20,150,220),
    bomb_red =(  0,  0,255), bomb_grn=(  0,255,  0),
    xhair    =( 40,255, 40), orange  =(  0,165,255),
    black    =(  0,  0,  0),
)

# ── Procedural textures ──
def _make_tex(bgr, var=18, seed=0):
    rng = np.random.default_rng(seed)
    t = np.zeros((TEX_SIZE,TEX_SIZE,3),dtype=np.uint8)
    n = rng.integers(-var,var+1,(TEX_SIZE,TEX_SIZE)).astype(np.int16)
    for i,c in enumerate(bgr):
        t[:,:,i] = np.clip(c+n,0,255)
    return t

def _make_brick(bgr,mortar,seed=0):
    t = _make_tex(bgr,12,seed)
    for y in range(0,TEX_SIZE,16):
        t[y:y+2,:]=mortar
    for row in range(TEX_SIZE//16):
        off=0 if row%2==0 else 32
        for x in range(off,TEX_SIZE,32):
            t[row*16:(row+1)*16,x:x+2]=mortar
    return t

def _make_concrete(bgr,seed=0):
    t=_make_tex(bgr,25,seed)
    rng=np.random.default_rng(seed+99)
    for _ in range(3):
        x=int(rng.integers(5,TEX_SIZE-5))
        for dy in range(20):
            xx=np.clip(x+int(rng.integers(-1,2)),0,TEX_SIZE-1)
            t[dy,xx]=[max(0,bgr[i]-40) for i in range(3)]
    return t

def _make_wood(bgr,seed=0):
    t=_make_tex(bgr,8,seed)
    for x in range(0,TEX_SIZE,4):
        s=int(np.random.default_rng(seed+x).integers(-20,20))
        t[:,x:x+3]=[np.clip(bgr[i]+s,0,255) for i in range(3)]
    return t

def _make_metal(bgr,seed=0):
    t=_make_tex(bgr,10,seed)
    for y in range(0,TEX_SIZE,8):
        t[y,:]=[min(255,c+30) for c in bgr]
    return t

def _floor_tile(c1,c2):
    t=np.zeros((TEX_SIZE,TEX_SIZE,3),dtype=np.uint8)
    for y in range(TEX_SIZE):
        for x in range(TEX_SIZE):
            t[y,x]=c1 if (x//8+y//8)%2==0 else c2
    return t

TEXTURES = {
    1: _make_brick((80,90,160),(40,40,60),seed=1),
    2: _make_concrete((55,75,55),seed=2),
    3: _make_concrete((65,45,45),seed=3),
    4: _make_wood((45,65,80),seed=4),
    5: _make_metal((70,70,80),seed=5),
    6: _make_brick((100,110,130),(50,55,65),seed=6),
    'fl': _floor_tile((52,48,42),(44,40,35)),
    'ceil': _make_tex((55,55,65),8,seed=7),
}

# ── de_dust2 layout ──
DUST2_RAW = [
    "##################################################",
    "#TT.......####.......................####.....CC##",
    "#TT.......#..#.......................#..#.....CC##",
    "#.........#..########.....########..#...........#",
    "#.........#..#......#.....#......#..#...........#",
    "#.........####......#.....#......####...........#",
    "#...c..c............#.....#.................c...#",
    "#...c..c............#######.................c...#",
    "#...........####................................#",
    "#...........#..#................................#",
    "#...........#..#................................#",
    "#...........####....####..............#######..#",
    "#...................#..#...............#.....#..#",
    "#...................#..#...............#.....#..#",
    "#...................####...............#######..#",
    "#......c....c..................................##",
    "#......c....c.....bbbbb...............AAAAAAA.##",
    "#....................bbb...............AAAAAAA.##",
    "#...bbbbb..................................AAA.##",
    "##################################################",
]
_MW = max(len(r) for r in DUST2_RAW)
DUST2 = [r.ljust(_MW,'#') for r in DUST2_RAW]
MAP_ROWS = len(DUST2); MAP_COLS = _MW

WALL_CH = {'#':1,'A':2,'B':3,'c':4,'p':5,'m':6}
OPEN_CH  = set('.TtCcaAbB ')

SITE_A = (43,16,3.0)
SITE_B = (6,18,3.0)
T_SPAWNS  = [(1,1),(2,1),(1,2),(2,2),(3,1)]
CT_SPAWNS = [(45,1),(46,1),(45,2),(46,2),(44,1)]

# ── Spray patterns (radians) ──
def _sp(pairs): return [(math.radians(h),math.radians(v)) for h,v in pairs]
SPRAY = {
    'ak47': _sp([(0,0),(0,-1.2),(0.4,-2),(-0.3,-2.8),(0.6,-3.2),(0.9,-3),
                 (0.5,-2.5),(-0.2,-2),(-0.6,-1.5),(0.3,-1),(0.4,-0.8),
                 (0.2,-0.5),(-0.1,-0.3),(0.1,-0.2),(0,-0.1)]),
    'm4a1': _sp([(0,0),(0,-0.8),(0.2,-1.5),(-0.2,-2),(0.3,-2.2),(0.5,-2),
                 (0.2,-1.8),(-0.1,-1.5),(-0.3,-1.2),(0.1,-0.9),(0.2,-0.7),
                 (0.1,-0.4),(0,-0.2),(0.1,-0.1),(0,0)]),
    'mp5':  _sp([(0,0),(0.1,-0.5),(-0.1,-0.8),(0.2,-1),(-0.2,-0.8),
                 (0.1,-0.6),(0,-0.4),(0.1,-0.3),(-0.1,-0.2),(0,-0.1)]),
    'famas':_sp([(0,0),(0,-0.9),(0.3,-1.5),(-0.3,-1.8),(0.4,-1.5),
                 (0.2,-1.2),(-0.1,-0.9),(0.1,-0.6),(0,-0.3),(0,-0.1)]),
    'sg552':_sp([(0,0),(0,-1),(0.5,-1.8),(-0.4,-2.2),(0.6,-2),(0.4,-1.5),
                 (-0.2,-1.2),(0.2,-0.9),(0.1,-0.6),(0,-0.3)]),
}

WEAPONS = {
    'knife':    dict(name='Knife',      dmg=62,  rof=0.5,  reload=0,   mag=0, ammo=0,   price=0,    spread=0,     auto=False,slot=2,pen=0,  hs=3.0),
    'glock':    dict(name='Glock',      dmg=25,  rof=0.15, reload=2.2, mag=20,ammo=120, price=200,  spread=0.025, auto=False,slot=1,pen=0.5,hs=1.4),
    'usp':      dict(name='USP',        dmg=34,  rof=0.15, reload=2.2, mag=12,ammo=100, price=500,  spread=0.02,  auto=False,slot=1,pen=0.5,hs=1.6),
    'p228':     dict(name='P228',       dmg=32,  rof=0.2,  reload=2.7, mag=13,ammo=52,  price=600,  spread=0.03,  auto=False,slot=1,pen=0.8,hs=1.5),
    'deagle':   dict(name='Deagle',     dmg=54,  rof=0.4,  reload=2.2, mag=7, ammo=35,  price=650,  spread=0.04,  auto=False,slot=1,pen=0.9,hs=1.9),
    'fiveseven':dict(name='Five-SeveN', dmg=20,  rof=0.15, reload=2.7, mag=20,ammo=100, price=750,  spread=0.025, auto=False,slot=1,pen=1.0,hs=1.5),
    'ak47':     dict(name='AK-47',      dmg=36,  rof=0.1,  reload=2.5, mag=30,ammo=90,  price=2500, spread=0.04,  auto=True, slot=0,pen=2.0,hs=2.5),
    'm4a1':     dict(name='M4A1',       dmg=33,  rof=0.09, reload=3.0, mag=30,ammo=90,  price=3100, spread=0.035, auto=True, slot=0,pen=1.5,hs=2.0),
    'famas':    dict(name='FAMAS',      dmg=30,  rof=0.09, reload=3.3, mag=25,ammo=90,  price=2250, spread=0.04,  auto=True, slot=0,pen=1.5,hs=2.0),
    'sg552':    dict(name='SG-552',     dmg=33,  rof=0.09, reload=3.0, mag=30,ammo=90,  price=3500, spread=0.035, auto=True, slot=0,pen=1.5,hs=2.0),
    'awp':      dict(name='AWP',        dmg=115, rof=1.35, reload=3.7, mag=10,ammo=30,  price=4750, spread=0.002, auto=False,slot=0,pen=3.0,hs=1.0),
    'scout':    dict(name='Scout',      dmg=75,  rof=1.3,  reload=3.0, mag=10,ammo=90,  price=2750, spread=0.005, auto=False,slot=0,pen=2.5,hs=1.0),
    'sg550':    dict(name='SG-550',     dmg=70,  rof=0.45, reload=3.3, mag=30,ammo=90,  price=4200, spread=0.005, auto=False,slot=0,pen=2.5,hs=1.5),
    'mp5':      dict(name='MP5',        dmg=26,  rof=0.08, reload=2.1, mag=30,ammo=120, price=1500, spread=0.04,  auto=True, slot=0,pen=0.8,hs=1.5),
    'tmp':      dict(name='TMP',        dmg=20,  rof=0.07, reload=1.8, mag=30,ammo=120, price=1250, spread=0.05,  auto=True, slot=0,pen=0.6,hs=1.5),
    'mac10':    dict(name='MAC-10',     dmg=29,  rof=0.07, reload=2.6, mag=30,ammo=120, price=1400, spread=0.06,  auto=True, slot=0,pen=0.7,hs=1.5),
    'henade':   dict(name='HE Grenade', dmg=98,  rof=1.0,  reload=0,   mag=1, ammo=1,   price=300,  spread=0,     auto=False,slot=3,pen=0,  hs=1.0),
    'flash':    dict(name='Flashbang',  dmg=0,   rof=1.0,  reload=0,   mag=1, ammo=2,   price=200,  spread=0,     auto=False,slot=3,pen=0,  hs=1.0),
    'smoke':    dict(name='Smoke',      dmg=0,   rof=1.0,  reload=0,   mag=1, ammo=1,   price=300,  spread=0,     auto=False,slot=3,pen=0,  hs=1.0),
    'molotov':  dict(name='Molotov',    dmg=40,  rof=1.0,  reload=0,   mag=1, ammo=1,   price=400,  spread=0,     auto=False,slot=3,pen=0,  hs=1.0),
    'vest':     dict(name='Kevlar',     dmg=0,   rof=0,    reload=0,   mag=0, ammo=0,   price=650,  spread=0,     auto=False,slot=4,pen=0,  hs=1.0),
    'vesthelm': dict(name='K+Helm',     dmg=0,   rof=0,    reload=0,   mag=0, ammo=0,   price=1000, spread=0,     auto=False,slot=4,pen=0,  hs=1.0),
    'defkit':   dict(name='Defuse Kit', dmg=0,   rof=0,    reload=0,   mag=0, ammo=0,   price=200,  spread=0,     auto=False,slot=4,pen=0,  hs=1.0),
}
T_BUY  = ['ak47','sg552','mp5','mac10','tmp','deagle','p228','glock','henade','flash','smoke','molotov','vest','vesthelm']
CT_BUY = ['m4a1','famas','sg550','scout','awp','mp5','tmp','usp','fiveseven','p228','deagle','henade','flash','smoke','defkit','vest','vesthelm']

# ── Sound synthesis ──
SR = 44100
def _env(w,a=0.003,d=0.04,s=0.5,r=0.12):
    n=len(w); env=np.ones(n)
    ai=int(SR*a); di=int(SR*d); ri=int(SR*r)
    if ai>0: env[:ai]=np.linspace(0,1,ai)
    if di>0 and ai+di<n: env[ai:ai+di]=np.linspace(1,s,di)
    if ri>0 and n-ri>=0: env[max(0,n-ri):]=np.linspace(s,0,min(ri,n))
    return (w*env).astype(np.int16)

def _noise(dur,amp=0.5):
    return (np.random.uniform(-1,1,int(SR*dur))*amp*32767).astype(np.int16)

def _sine(freq,dur,amp=0.4):
    t=np.linspace(0,dur,int(SR*dur),False)
    return (np.sin(2*np.pi*freq*t)*amp*32767).astype(np.int16)

SOUNDS={}
if AUDIO:
    try:
        def _rifle(): return _env(np.concatenate([_noise(0.003,0.9),_noise(0.08,0.7),_noise(0.15,0.3)]),0.001,0.03,0.4,0.15)
        def _pistol(): return _env(np.concatenate([_noise(0.002,0.8),_noise(0.05,0.6)]),0.001,0.02,0.3,0.10)
        def _awp(): n=_env(np.concatenate([_noise(0.003,1.0),_noise(0.12,0.8),_noise(0.25,0.35)]),0.001,0.04,0.5,0.25); return n
        def _smg(): return _env(np.concatenate([_noise(0.002,0.6),_noise(0.04,0.5)]),0.001,0.015,0.3,0.08)
        SOUNDS={
            'ak47':_rifle(),'m4a1':_rifle(),'famas':_rifle(),'sg552':_rifle(),'sg550':_rifle(),'scout':_rifle(),
            'awp':_awp(),'mp5':_smg(),'tmp':_smg(),'mac10':_smg(),
            'glock':_pistol(),'usp':_pistol(),'p228':_pistol(),'deagle':_pistol(),'fiveseven':_pistol(),
            'footstep':_env(_noise(0.04,0.25),0.002,0.01,0.4,0.03),
            'reload':_env(_noise(0.05,0.4),0.001,0.005,0.5,0.03),
            'plant_beep':_env(_sine(880,0.08,0.5),0.002,0.01,0.8,0.02),
            'bomb_tick':_env(_sine(1200,0.04,0.6),0.001,0.005,0.8,0.01),
            'explosion':(_noise(0.6,1.0)*np.exp(-np.linspace(0,8,int(SR*0.6)))).astype(np.int16),
            'nade_bounce':_env(_noise(0.02,0.3),0.001,0.005,0.3,0.01),
        }
    except: AUDIO=False

def play_snd(name,vol=1.0):
    if not AUDIO or name not in SOUNDS: return
    try:
        w=(SOUNDS[name]*min(1.0,vol)).clip(-32767,32767).astype(np.int16)
        sd.play(w,SR,blocking=False)
    except: pass

# ── Game Map ──
class GameMap:
    def __init__(self):
        self.grid=[]
        for row in DUST2:
            r=[]
            for ch in row:
                r.append(WALL_CH.get(ch,0) if ch not in OPEN_CH else 0)
            self.grid.append(r)
        self.rows=len(self.grid)
        self.cols=max(len(r) for r in self.grid)
        for r in self.grid:
            while len(r)<self.cols: r.append(1)

    def is_wall(self,x,y):
        c,r=int(x),int(y)
        if c<0 or r<0 or c>=self.cols or r>=self.rows: return True
        return self.grid[r][c]!=0

    def wall_type(self,x,y):
        c,r=int(x),int(y)
        if c<0 or r<0 or c>=self.cols or r>=self.rows: return 1
        return self.grid[r][c]

    def near_site(self,px,py,site):
        sx,sy,sr=site
        return math.hypot(px-sx,py-sy)<sr

# ── Raycaster with textures ──
class Raycaster:
    def __init__(self,gmap):
        self.map=gmap
        self._fl=TEXTURES['fl']
        self._cl=TEXTURES['ceil']

    def render(self,px,py,angle,frame):
        gmap=self.map
        cos_a=math.cos(angle); sin_a=math.sin(angle)
        z_buf=np.full(W,float(MAX_DEPTH),dtype=np.float32)

        # Floor/ceiling cast
        for y in range(HALF_H,H):
            row_dist=max(0.001,(0.5*H)/(y-HALF_H+0.001))
            fx=px+row_dist*(cos_a-0.5*(2*math.cos(angle-FOV/2)))
            fy=py+row_dist*(sin_a-0.5*(2*math.sin(angle-FOV/2)))
            sx=row_dist*2*math.cos(angle-FOV/2)/W
            sy=row_dist*2*math.sin(angle-FOV/2)/W
            bright=np.clip(1.0-row_dist/MAX_DEPTH,0.18,1.0).astype(np.float32)
            bright_c=bright*0.65
            for x in range(W):
                tx=int(fx*TEX_SIZE)%TEX_SIZE
                ty=int(fy*TEX_SIZE)%TEX_SIZE
                frame[y,x]=(self._fl[ty,tx]*bright).clip(0,255).astype(np.uint8)
                frame[H-1-y,x]=(self._cl[ty,tx]*bright_c).clip(0,255).astype(np.uint8)
                fx+=sx; fy+=sy

        # Sky
        sky_h=HALF_H//3*2
        st=np.array(PAL['sky'],dtype=np.float32)
        sb=np.array(PAL['sky2'],dtype=np.float32)
        for y in range(sky_h):
            t=y/max(sky_h,1)
            frame[y,:]=(st*(1-t)+sb*t).astype(np.uint8)

        # Walls
        ray=angle-FOV/2; dray=FOV/W
        for col in range(W):
            ca=math.cos(ray); sa=math.sin(ray)
            if abs(ca)<1e-9: ca=1e-9
            if abs(sa)<1e-9: sa=1e-9
            mx,my=int(px),int(py)
            dxa=abs(1/ca); dya=abs(1/sa)
            smx=1 if ca>0 else -1; smy=1 if sa>0 else -1
            sdx=(mx+1-px)*dxa if ca>0 else (px-mx)*dxa
            sdy=(my+1-py)*dya if sa>0 else (py-my)*dya
            side=0; dist=0.0; wtype=1; wx=0.0
            for _ in range(MAX_DEPTH*4):
                if sdx<sdy: sdx+=dxa; mx+=smx; side=0
                else:       sdy+=dya; my+=smy; side=1
                if gmap.is_wall(mx,my):
                    wtype=gmap.wall_type(mx,my)
                    if side==0: dist=(mx-px+(1-smx)/2)/ca; wx=py+dist*sa
                    else:       dist=(my-py+(1-smy)/2)/sa; wx=px+dist*ca
                    break
            dist=max(0.01,dist*math.cos(ray-angle))
            z_buf[col]=dist
            wh=min(H,int(H/dist))
            top=max(0,HALF_H-wh//2); bot=min(H,HALF_H+wh//2)
            tex=TEXTURES.get(wtype,TEXTURES[1])
            tx=int((wx%1.0)*TEX_SIZE)%TEX_SIZE
            if (side==0 and ca<0) or (side==1 and sa>0): tx=TEX_SIZE-tx-1
            bright=max(0.15,1.0-dist/MAX_DEPTH)
            if side==1: bright*=0.68
            ch=bot-top
            if ch>0:
                tc=tex[:,tx].astype(np.float32)
                idx=(np.arange(ch)*TEX_SIZE/ch).astype(int).clip(0,TEX_SIZE-1)
                frame[top:bot,col]=(tc[idx]*bright).clip(0,255).astype(np.uint8)
            ray+=dray
        return z_buf

# ── Player ──
class Player:
    def __init__(self,pid,name,team,spawn):
        self.pid=pid; self.name=name; self.team=team
        sx,sy=spawn
        self.x=float(sx)+0.5; self.y=float(sy)+0.5
        self.angle=0.0 if team=='T' else math.pi
        self.hp=100; self.armor=0; self.helmet=False
        self.alive=True; self.money=800
        self.kills=0; self.deaths=0; self.assists=0; self.score=0
        self.defkit=False
        self.vel_x=0.0; self.vel_y=0.0
        self.on_ground=True; self.crouching=False; self.walking=False
        self.stamina=1.0
        self.weapons={'knife':dict(WEAPONS['knife'])}
        if team=='T': self.weapons['glock']=dict(WEAPONS['glock'])
        else:          self.weapons['usp']=dict(WEAPONS['usp'])
        self.slot='glock' if team=='T' else 'usp'
        self.reload_end=0.0; self.last_shot=0.0
        self.shot_count=0; self.recoil_h=0.0; self.recoil_v=0.0
        self.has_bomb=False
        self.is_planting=False; self.plant_start=0.0
        self.is_defusing=False; self.defuse_start=0.0
        self.flash_alpha=0.0; self.flash_decay=0.5
        self.zoomed=False
        self.dmg_indicators=[]
        self._last_step=0.0

    @property
    def weapon(self): return self.weapons.get(self.slot,WEAPONS['knife'])

    def switch_slot(self,name):
        if name in self.weapons:
            self.slot=name; self.shot_count=0; self.recoil_h=self.recoil_v=0

    def effective_spread(self):
        w=self.weapon; base=w.get('spread',0.05)
        spd=math.hypot(self.vel_x,self.vel_y)
        return max(0,base+spd*0.12+(0 if self.on_ground else 0.08)
                   +(-base*0.3 if self.crouching else 0)
                   +(-base*0.1 if self.walking and spd<0.03 else 0))

    def take_damage(self,dmg,hitbox='body'):
        if not self.alive: return 0
        if self.armor>0:
            if hitbox=='head' and self.helmet: absorbed=min(self.armor,int(dmg*0.5))
            elif hitbox!='head':              absorbed=min(self.armor,int(dmg*0.5))
            else:                             absorbed=0
            self.armor=max(0,self.armor-absorbed); dmg=max(1,dmg-absorbed)
        self.hp-=dmg
        if self.hp<=0: self.hp=0; self.alive=False
        return dmg

    def respawn(self,spawn):
        sx,sy=spawn; self.x=float(sx)+0.5; self.y=float(sy)+0.5
        self.angle=0.0 if self.team=='T' else math.pi
        self.hp=100; self.armor=0; self.helmet=False; self.alive=True
        self.vel_x=self.vel_y=0; self.on_ground=True
        self.is_planting=self.is_defusing=False
        self.flash_alpha=0; self.recoil_h=self.recoil_v=0
        self.shot_count=0; self.zoomed=False; self.dmg_indicators.clear()

# ── Projectile ──
class Projectile:
    G=9.8
    def __init__(self,kind,owner,team,x,y,vx,vy):
        self.kind=kind; self.owner=owner; self.team=team
        self.x=x; self.y=y; self.z=1.0
        self.vx=vx; self.vy=vy; self.vz=2.5
        self.bounces=0; self.born=time.time(); self.detonated=False
        self.fuse={'henade':3.0,'flash':1.5,'smoke':1.0,'molotov':1.5}.get(kind,3.0)

    def update(self,dt,gmap):
        if self.detonated: return
        if time.time()-self.born>=self.fuse: self.detonated=True; return
        self.vz-=self.G*dt
        nx=self.x+self.vx*dt; ny=self.y+self.vy*dt
        self.z=max(0,self.z+self.vz*dt)
        if gmap.is_wall(nx,self.y): self.vx*=-0.5; play_snd('nade_bounce',0.4)
        else: self.x=nx
        if gmap.is_wall(self.x,ny): self.vy*=-0.5; play_snd('nade_bounce',0.4)
        else: self.y=ny
        if self.z<=0:
            self.z=0; self.vz*=-0.4; self.vx*=0.7; self.vy*=0.7
            self.bounces+=1
            if self.bounces>4: self.vx=self.vy=0

# ── Area Effect ──
class AreaEffect:
    def __init__(self,kind,x,y,ttl):
        self.kind=kind; self.x=x; self.y=y; self.ttl=ttl
        self.born=time.time()
        self.radius=2.5 if kind=='smoke' else 1.2
    @property
    def alive(self): return time.time()-self.born<self.ttl
    @property
    def age(self): return time.time()-self.born

# ── Game State ──
class GameState:
    def __init__(self):
        self.map=GameMap(); self.rc=Raycaster(self.map)
        self.players={}; self.local_pid=0
        self.round_num=1; self.max_rounds=30
        self.t_score=0; self.ct_score=0
        self.phase='buy'; self.round_start=time.time()
        self.BUY_TIME=15.0; self.ROUND_TIME=115.0
        self.PLANT_TIME=40.0; self.DEFUSE_TIME=10.0
        self.bomb_planted=False; self.bomb_defused=False; self.bomb_exploded=False
        self.bomb_x=0.0; self.bomb_y=0.0; self.bomb_plant_time=0.0
        self.projectiles=[]; self.area_effects=[]
        self.kill_feed=deque(maxlen=8); self.chat=deque(maxlen=6)
        self.hit_markers=[]; self.dmg_numbers=[]
        self.show_buy=False; self.show_score=False
        self.announce=''; self.announce_t=0.0; self.winner=None
        self.t_losses=0; self.ct_losses=0
        self._last_tick=0.0

    def add_player(self,pid,name,team):
        spawns=T_SPAWNS if team=='T' else CT_SPAWNS
        idx=len([p for p in self.players.values() if p.team==team])
        spawn=spawns[idx%len(spawns)]
        p=Player(pid,name,team,spawn)
        self.players[pid]=p
        return p

    def local(self): return self.players.get(self.local_pid)

    def time_left(self):
        now=time.time()
        if self.phase=='buy':     return max(0,self.BUY_TIME-(now-self.round_start))
        elif self.phase=='live':  return max(0,self.ROUND_TIME-(now-self.round_start))
        elif self.phase=='planted':return max(0,self.PLANT_TIME-(now-self.bomb_plant_time))
        return 0

    def say(self,msg): self.announce=msg; self.announce_t=time.time()

    def end_round(self,winner,reason):
        if self.phase=='ended': return
        self.phase='ended'; self.winner=winner
        msgs={'elim_t':'Terrorists Eliminated — CT Win!','elim_ct':'CTs Eliminated — T Win!',
              'time':'Time Up — CT Win!','bomb':'BOMB EXPLODED — T Win!','defuse':'Bomb Defused — CT Win!'}
        self.say(msgs.get(reason,f'{winner} wins'))
        WIN=3250; LOSS=[1400,1900,2400,2900,3400]
        if winner=='T': self.t_score+=1; self.ct_losses+=1; self.t_losses=0
        else:           self.ct_score+=1; self.t_losses+=1;  self.ct_losses=0
        for p in self.players.values():
            if p.team==winner: p.money=min(16000,p.money+WIN)
            else:
                lc=self.ct_losses if winner=='T' else self.t_losses
                p.money=min(16000,p.money+LOSS[min(lc-1,4)])
            if self.bomb_planted and winner=='T' and p.team=='T':
                p.money=min(16000,p.money+800)
            p.score=p.kills*2-p.deaths+p.assists

    def check_round(self):
        if self.phase=='ended': return
        t_alive=[p for p in self.players.values() if p.team=='T' and p.alive]
        ct_alive=[p for p in self.players.values() if p.team=='CT' and p.alive]
        t_total=[p for p in self.players.values() if p.team=='T']
        ct_total=[p for p in self.players.values() if p.team=='CT']
        if self.bomb_exploded:   self.end_round('T','bomb')
        elif self.bomb_defused:  self.end_round('CT','defuse')
        elif self.phase=='live' and self.time_left()<=0: self.end_round('CT','time')
        elif t_total and not t_alive and not self.bomb_planted: self.end_round('CT','elim_t')
        elif ct_total and not ct_alive: self.end_round('T','elim_ct')

    def new_round(self):
        self.round_num+=1; self.phase='buy'; self.round_start=time.time()
        self.bomb_planted=self.bomb_defused=self.bomb_exploded=False
        self.bomb_plant_time=0.0; self.winner=None
        self.projectiles.clear(); self.area_effects.clear()
        self.hit_markers.clear(); self.dmg_numbers.clear()
        ti=ci=0
        for p in self.players.values():
            if p.team=='T': spawn=T_SPAWNS[ti%len(T_SPAWNS)]; ti+=1
            else:            spawn=CT_SPAWNS[ci%len(CT_SPAWNS)]; ci+=1
            p.respawn(spawn)
            for wn,wd in p.weapons.items():
                proto=WEAPONS.get(wn,{})
                wd['ammo']=proto.get('ammo',wd.get('ammo',0))
                wd['mag']=proto.get('mag',wd.get('mag',0))
        bomb_given=False
        for p in self.players.values():
            if p.team=='T' and p.alive and not bomb_given:
                p.has_bomb=True; bomb_given=True
            else: p.has_bomb=False

    def update_physics(self,dt,local_pid):
        for proj in list(self.projectiles):
            proj.update(dt,self.map)
            if proj.detonated:
                self._detonate(proj,local_pid)
                self.projectiles.remove(proj)
        self.area_effects=[e for e in self.area_effects if e.alive]
        for eff in self.area_effects:
            if eff.kind=='fire':
                for p in self.players.values():
                    if not p.alive: continue
                    if math.hypot(p.x-eff.x,p.y-eff.y)<eff.radius:
                        p.take_damage(int(8*dt),'body')
        if self.bomb_planted and not self.bomb_defused:
            tl=self.time_left()
            if tl>0:
                interval=max(0.18,tl/18)
                now=time.time()
                if now-self._last_tick>interval:
                    self._last_tick=now; play_snd('bomb_tick',0.9)
            if tl<=0 and not self.bomb_exploded:
                self.bomb_exploded=True
                play_snd('explosion',1.0)
                for p in self.players.values():
                    if not p.alive: continue
                    d=math.hypot(p.x-self.bomb_x,p.y-self.bomb_y)
                    if d<5.0: p.take_damage(int(500*(1-d/5.0)),'body')
                self.check_round()

    def _detonate(self,proj,local_pid):
        px,py=proj.x,proj.y; kind=proj.kind
        if kind=='henade':
            play_snd('explosion',1.0)
            for p in self.players.values():
                if not p.alive: continue
                d=math.hypot(p.x-px,p.y-py)
                if d<4.0:
                    dmg=int(WEAPONS['henade']['dmg']*(1-d/4.0))
                    if dmg>0:
                        p.take_damage(dmg,'body')
                        if not p.alive:
                            att=self.players.get(proj.owner)
                            if att: att.kills+=1; p.deaths+=1; self.kill_feed.appendleft((att.name,p.name,'HE',time.time()))
            self.check_round()
        elif kind=='flash':
            for p in self.players.values():
                if not p.alive: continue
                d=math.hypot(p.x-px,p.y-py)
                if d<6.0 and p.pid==local_pid:
                    p.flash_alpha=min(1.0,(1.0-d/6.0)*1.2); p.flash_decay=0.65
        elif kind=='smoke':  self.area_effects.append(AreaEffect('smoke',px,py,18.0))
        elif kind=='molotov':self.area_effects.append(AreaEffect('fire',px,py,7.0))

# ── HUD ──
class HUD:
    def __init__(self,gs): self.gs=gs

    def draw(self,frame,lp):
        gs=self.gs; now=time.time(); H_,W_=frame.shape[:2]
        # Bottom bar
        cv2.rectangle(frame,(0,H_-56),(W_,H_),(12,12,12),-1)
        cv2.line(frame,(0,H_-56),(W_,H_-56),(50,50,50),1)
        # HP
        hc=PAL['green'] if lp.hp>60 else PAL['yellow'] if lp.hp>30 else PAL['red']
        cv2.putText(frame,str(lp.hp),(20,H_-10),cv2.FONT_HERSHEY_SIMPLEX,1.1,hc,2)
        cv2.putText(frame,'HP',(78,H_-12),cv2.FONT_HERSHEY_SIMPLEX,0.38,PAL['gray'],1)
        # HP bar
        cv2.rectangle(frame,(20,H_-8),(20+120,H_-3),(30,30,30),-1)
        cv2.rectangle(frame,(20,H_-8),(20+int(120*lp.hp/100),H_-3),hc,-1)
        # Armor
        ac=PAL['ct_blue'] if lp.helmet else PAL['gray']
        cv2.putText(frame,str(lp.armor),(150,H_-10),cv2.FONT_HERSHEY_SIMPLEX,0.8,ac,2)
        cv2.putText(frame,'AR',(200,H_-12),cv2.FONT_HERSHEY_SIMPLEX,0.38,PAL['gray'],1)
        if lp.helmet: cv2.putText(frame,'[H]',(225,H_-12),cv2.FONT_HERSHEY_SIMPLEX,0.34,ac,1)
        # Money
        cv2.putText(frame,f'${lp.money}',(W_//2-50,H_-10),cv2.FONT_HERSHEY_SIMPLEX,0.85,PAL['green'],2)
        # Ammo
        w=lp.weapon; reloading=lp.reload_end>now
        if lp.slot!='knife':
            if reloading:
                prog=max(0,1-(lp.reload_end-now)/WEAPONS.get(lp.slot,{}).get('reload',2.2))
                cv2.putText(frame,f'RELOADING {int(prog*100)}%',(W_-260,H_-32),cv2.FONT_HERSHEY_SIMPLEX,0.45,PAL['yellow'],1)
            else:
                cv2.putText(frame,f'{w.get("mag",0)}',(W_-220,H_-10),cv2.FONT_HERSHEY_SIMPLEX,1.0,PAL['white'],2)
                cv2.putText(frame,'/',(W_-175,H_-10),cv2.FONT_HERSHEY_SIMPLEX,0.6,PAL['gray'],1)
                cv2.putText(frame,f'{w.get("ammo",0)}',(W_-160,H_-10),cv2.FONT_HERSHEY_SIMPLEX,0.8,PAL['gray'],1)
            cv2.putText(frame,w.get('name',''),(W_-220,H_-38),cv2.FONT_HERSHEY_SIMPLEX,0.36,PAL['gray'],1)
        # Weapon strip
        wx=270
        for wn,wd in lp.weapons.items():
            cur=wn==lp.slot
            col=PAL['yellow'] if cur else PAL['dgray']
            cv2.putText(frame,wd.get('name',wn),(wx,H_-38),cv2.FONT_HERSHEY_SIMPLEX,0.3,col,1)
            if cur:
                ts=cv2.getTextSize(wd.get('name',wn),cv2.FONT_HERSHEY_SIMPLEX,0.3,1)[0]
                cv2.line(frame,(wx,H_-34),(wx+ts[0],H_-34),col,1)
            wx+=88
        # Top bar
        cv2.rectangle(frame,(W_//2-130,0),(W_//2+130,52),(12,12,12),-1)
        cv2.putText(frame,str(gs.ct_score),(W_//2-110,40),cv2.FONT_HERSHEY_SIMPLEX,1.4,PAL['ct_blue'],2)
        cv2.putText(frame,':',(W_//2-28,38),cv2.FONT_HERSHEY_SIMPLEX,1.0,PAL['white'],2)
        cv2.putText(frame,str(gs.t_score),(W_//2+12,40),cv2.FONT_HERSHEY_SIMPLEX,1.4,PAL['t_gold'],2)
        tl=gs.time_left(); mins=int(tl)//60; secs=int(tl)%60
        tc=PAL['red'] if tl<10 else PAL['white']
        cv2.putText(frame,f'{mins:02d}:{secs:02d}',(W_//2-28,18),cv2.FONT_HERSHEY_SIMPLEX,0.52,tc,1)
        cv2.putText(frame,f'RD {gs.round_num}/{gs.max_rounds}',(W_//2-30,50),cv2.FONT_HERSHEY_SIMPLEX,0.28,PAL['gray'],1)
        # Phase
        phase_txt={'buy':'BUY PHASE','planted':'!! BOMB PLANTED !!','ended':'ROUND OVER','halftime':'HALFTIME'}.get(gs.phase,'')
        if phase_txt:
            pc=PAL['bomb_red'] if gs.phase=='planted' else PAL['yellow']
            cv2.putText(frame,phase_txt,(W_//2-95,70),cv2.FONT_HERSHEY_SIMPLEX,0.5,pc,1)
        # Bomb bar
        if gs.bomb_planted and not gs.bomb_defused:
            prog=gs.time_left()/gs.PLANT_TIME
            bx,by=W_//2-160,78
            cv2.rectangle(frame,(bx,by),(bx+320,by+14),(50,0,0),-1)
            cv2.rectangle(frame,(bx,by),(bx+int(320*max(0,prog)),by+14),PAL['bomb_red'],-1)
            cv2.putText(frame,'C4',(bx-32,by+11),cv2.FONT_HERSHEY_SIMPLEX,0.42,PAL['bomb_red'],1)
        # Defuse/plant progress
        if lp.is_defusing:
            prog=(now-lp.defuse_start)/(gs.DEFUSE_TIME*(0.5 if lp.defkit else 1.0))
            self._progress(frame,'DEFUSING BOMB',prog,PAL['green'],H_//2+70)
        if lp.is_planting:
            prog=(now-lp.plant_start)/3.2
            self._progress(frame,'PLANTING C4',prog,PAL['bomb_red'],H_//2+70)
        # Kill feed
        ky=96
        for killer,victim,weapon,born in list(gs.kill_feed):
            if now-born>6: continue
            txt=f'{killer} [{weapon}] {victim}'
            cv2.putText(frame,txt,(W_-315,ky),cv2.FONT_HERSHEY_SIMPLEX,0.34,PAL['white'],1)
            ky+=17
        # Round announce
        if gs.announce and now-gs.announce_t<4.5:
            txt=gs.announce
            ts=cv2.getTextSize(txt,cv2.FONT_HERSHEY_SIMPLEX,0.9,2)[0]
            tx=(W_-ts[0])//2; ty=H_//2-85
            cv2.rectangle(frame,(tx-10,ty-30),(tx+ts[0]+10,ty+8),(0,0,0),-1)
            cv2.putText(frame,txt,(tx,ty),cv2.FONT_HERSHEY_SIMPLEX,0.9,PAL['yellow'],2)
        # Interaction prompts
        if gs.bomb_planted and lp.team=='CT' and not gs.bomb_defused:
            if math.hypot(lp.x-gs.bomb_x,lp.y-gs.bomb_y)<1.8:
                cv2.putText(frame,'[E] DEFUSE BOMB',(W_//2-88,H_//2+50),cv2.FONT_HERSHEY_SIMPLEX,0.7,PAL['green'],2)
        if lp.has_bomb and not gs.bomb_planted and lp.team=='T':
            na=gs.map.near_site(lp.x,lp.y,SITE_A); nb=gs.map.near_site(lp.x,lp.y,SITE_B)
            if na or nb:
                site='A' if na else 'B'
                cv2.putText(frame,f'[E] PLANT C4 ({site}-SITE)',(W_//2-115,H_//2+50),cv2.FONT_HERSHEY_SIMPLEX,0.7,PAL['bomb_red'],2)
        # Buy hint
        if gs.phase=='buy':
            cv2.putText(frame,'[B] Buy Menu',(10,H_-70),cv2.FONT_HERSHEY_SIMPLEX,0.42,PAL['yellow'],1)
        # Damage indicators
        for ang,born in list(lp.dmg_indicators):
            if now-born>1.0: lp.dmg_indicators.remove((ang,born)); continue
            alpha=1.0-(now-born)
            r=78; cx=W_//2; cy=H_//2
            rel=((ang-lp.angle+math.pi)%PI2)-math.pi
            sx=int(cx+math.sin(rel)*r); sy=int(cy-math.cos(rel)*r)
            col=tuple(int(c*alpha) for c in PAL['red'])
            cv2.arrowedLine(frame,(cx,cy),(sx,sy),col,2,tipLength=0.3)
        # Hit markers
        for born,is_kill in list(gs.hit_markers):
            if now-born>0.3: gs.hit_markers.remove((born,is_kill)); continue
            c=PAL['red'] if is_kill else PAL['white']
            s=10; cx=W_//2; cy=H_//2
            cv2.line(frame,(cx-s,cy-s),(cx+s,cy+s),c,2)
            cv2.line(frame,(cx+s,cy-s),(cx-s,cy+s),c,2)
        # Team alive
        ta=sum(1 for p in gs.players.values() if p.team=='T'  and p.alive)
        ca=sum(1 for p in gs.players.values() if p.team=='CT' and p.alive)
        cv2.putText(frame,f'T:{ta}',(W_-75,H_-72),cv2.FONT_HERSHEY_SIMPLEX,0.42,PAL['t_gold'],1)
        cv2.putText(frame,f'CT:{ca}',(W_-75,H_-57),cv2.FONT_HERSHEY_SIMPLEX,0.42,PAL['ct_blue'],1)
        # Controls
        cv2.putText(frame,'WASD=move Shift=walk Ctrl=crouch R=reload G=nade E=interact B=buy 1-5=weapon Tab=score',
                    (5,H_-3),cv2.FONT_HERSHEY_SIMPLEX,0.25,PAL['dgray'],1)

    def _progress(self,frame,label,prog,col,y):
        W_=frame.shape[1]; cx=W_//2
        cv2.rectangle(frame,(cx-100,y),(cx+100,y+14),(30,30,30),-1)
        cv2.rectangle(frame,(cx-100,y),(cx-100+int(200*max(0,min(1,prog))),y+14),col,-1)
        cv2.putText(frame,label,(cx-65,y+11),cv2.FONT_HERSHEY_SIMPLEX,0.46,PAL['white'],1)

    def draw_crosshair(self,frame,lp):
        H_,W_=frame.shape[:2]; cx=W_//2; cy=H_//2
        if lp.zoomed and lp.slot in('awp','scout','sg550'):
            cv2.line(frame,(cx-22,cy),(cx+22,cy),PAL['xhair'],1)
            cv2.line(frame,(cx,cy-22),(cx,cy+22),PAL['xhair'],1)
            cv2.circle(frame,(cx,cy),22,PAL['xhair'],1)
            return
        spread=lp.effective_spread()
        gap=max(3,int(spread*280)); ln=max(4,12-gap//2)
        c=PAL['xhair']
        cv2.line(frame,(cx-gap-ln,cy),(cx-gap,cy),c,1)
        cv2.line(frame,(cx+gap,cy),(cx+gap+ln,cy),c,1)
        cv2.line(frame,(cx,cy-gap-ln),(cx,cy-gap),c,1)
        cv2.line(frame,(cx,cy+gap),(cx,cy+gap+ln),c,1)
        cv2.circle(frame,(cx,cy),1,c,-1)

    def draw_buy(self,frame,lp):
        H_,W_=frame.shape[:2]
        ov=frame.copy(); cv2.rectangle(ov,(55,35),(W_-55,H_-55),(5,8,18),-1)
        cv2.addWeighted(ov,0.9,frame,0.1,0,frame)
        cv2.rectangle(frame,(55,35),(W_-55,H_-55),(50,60,120),2)
        cv2.putText(frame,'BUY MENU',(W_//2-90,75),cv2.FONT_HERSHEY_SIMPLEX,1.0,PAL['yellow'],2)
        cv2.putText(frame,f'Cash: ${lp.money}',(W_//2-60,105),cv2.FONT_HERSHEY_SIMPLEX,0.6,PAL['green'],1)
        avail=T_BUY if lp.team=='T' else CT_BUY
        COLS=4; iw=(W_-140)//COLS; ih=46; sy=125
        for i,wname in enumerate(avail):
            if wname not in WEAPONS: continue
            wd=WEAPONS[wname]; ci=i%COLS; ri=i//COLS
            x=70+ci*iw; y=sy+ri*ih
            owned=(wname in lp.weapons or (wname=='vest' and lp.armor>0)
                   or (wname=='vesthelm' and lp.helmet) or (wname=='defkit' and lp.defkit))
            can=lp.money>=wd['price'] and not owned
            cv2.rectangle(frame,(x,y),(x+iw-6,y+ih-4),(15,35,15) if can else (30,10,10),-1)
            cv2.rectangle(frame,(x,y),(x+iw-6,y+ih-4),PAL['green'] if can else (40,40,60),1)
            nc=PAL['white'] if can else PAL['gray']
            cv2.putText(frame,f'[{i+1}]{wd["name"]}',(x+3,y+17),cv2.FONT_HERSHEY_SIMPLEX,0.36,nc,1)
            cv2.putText(frame,f'${wd["price"]}',(x+3,y+34),cv2.FONT_HERSHEY_SIMPLEX,0.36,PAL['green'] if can else PAL['red'],1)
            if wd.get('dmg',0): cv2.putText(frame,f'D:{wd["dmg"]}',(x+iw-62,y+34),cv2.FONT_HERSHEY_SIMPLEX,0.28,PAL['gray'],1)
            if owned: cv2.putText(frame,'OWNED',(x+iw-62,y+17),cv2.FONT_HERSHEY_SIMPLEX,0.28,PAL['yellow'],1)
        cv2.putText(frame,'[1-9] select  [B] close',(W_//2-130,H_-65),cv2.FONT_HERSHEY_SIMPLEX,0.38,PAL['gray'],1)

    def draw_scoreboard(self,frame):
        H_,W_=frame.shape[:2]
        ov=frame.copy(); cv2.rectangle(ov,(75,35),(W_-75,H_-35),(5,5,15),-1)
        cv2.addWeighted(ov,0.88,frame,0.12,0,frame)
        cv2.rectangle(frame,(75,35),(W_-75,H_-35),(50,60,100),2)
        cv2.putText(frame,'SCOREBOARD',(W_//2-90,78),cv2.FONT_HERSHEY_SIMPLEX,1.0,PAL['white'],2)
        cv2.putText(frame,f'CT {self.gs.ct_score}  :  {self.gs.t_score} T',(W_//2-80,108),cv2.FONT_HERSHEY_SIMPLEX,0.75,PAL['white'],2)
        hx=95; hy=138
        for hdr,hp in [('Player',hx),('K',hx+210),('D',hx+252),('A',hx+292),('$',hx+332)]:
            cv2.putText(frame,hdr,(hp,hy),cv2.FONT_HERSHEY_SIMPLEX,0.4,PAL['gray'],1)
        cy=160
        for team,label,tc in [('CT','── COUNTER-TERRORISTS ──',PAL['ct_blue']),('T','── TERRORISTS ──',PAL['t_gold'])]:
            cv2.putText(frame,label,(hx,cy),cv2.FONT_HERSHEY_SIMPLEX,0.46,tc,1); cy+=20
            for p in sorted(self.gs.players.values(),key=lambda x:-x.score):
                if p.team!=team: continue
                nc=PAL['yellow'] if p.pid==self.gs.local_pid else PAL['white']
                cv2.putText(frame,f'{"●" if p.alive else "○"} {p.name[:14]}',(hx,cy),cv2.FONT_HERSHEY_SIMPLEX,0.4,nc,1)
                for val,xp in [(p.kills,hx+210),(p.deaths,hx+252),(p.assists,hx+292)]:
                    cv2.putText(frame,str(val),(xp,cy),cv2.FONT_HERSHEY_SIMPLEX,0.4,nc,1)
                cv2.putText(frame,f'${p.money}',(hx+332,cy),cv2.FONT_HERSHEY_SIMPLEX,0.36,PAL['green'],1)
                cy+=20
            cy+=6

    def draw_dead(self,frame,gs):
        H_,W_=frame.shape[:2]; frame[:] =(8,4,4)
        cv2.putText(frame,'YOU WERE KILLED',(W_//2-165,H_//2-30),cv2.FONT_HERSHEY_SIMPLEX,1.4,PAL['red'],3)
        cv2.putText(frame,'Waiting for next round...',(W_//2-155,H_//2+22),cv2.FONT_HERSHEY_SIMPLEX,0.65,PAL['gray'],1)
        if gs.winner:
            wt='Terrorists' if gs.winner=='T' else 'Counter-Terrorists'
            cv2.putText(frame,f'{wt} win the round!',(W_//2-175,H_//2+62),cv2.FONT_HERSHEY_SIMPLEX,0.7,PAL['yellow'],2)

    def draw_minimap(self,frame,lp,gs):
        sz=138; mx=W-sz-4; my=H-sz-58
        scale=sz/max(gs.map.cols,gs.map.rows)
        cv2.rectangle(frame,(mx-2,my-2),(mx+sz+2,my+sz+2),(10,10,10),-1)
        cv2.rectangle(frame,(mx-2,my-2),(mx+sz+2,my+sz+2),(45,45,45),1)
        wcols={1:(68,73,88),2:(28,68,28),3:(68,28,28),4:(53,43,33),5:(58,58,68),6:(78,83,93)}
        for r,row in enumerate(gs.map.grid):
            for c,cell in enumerate(row):
                if cell>0:
                    col=wcols.get(cell,(68,68,78))
                    x1=mx+int(c*scale); y1=my+int(r*scale)
                    x2=mx+int((c+1)*scale); y2=my+int((r+1)*scale)
                    if x2>x1 and y2>y1: cv2.rectangle(frame,(x1,y1),(x2,y2),col,-1)
        for site,label in [(SITE_A,'A'),(SITE_B,'B')]:
            ax=mx+int(site[0]*scale); ay=my+int(site[1]*scale)
            cv2.putText(frame,label,(ax,ay),cv2.FONT_HERSHEY_SIMPLEX,0.28,PAL['white'],1)
        for pid,p in gs.players.items():
            if not p.alive: continue
            px_=mx+int(p.x*scale); py_=my+int(p.y*scale)
            col=PAL['ct_blue'] if p.team=='CT' else PAL['t_gold']
            sz2=4 if pid==gs.local_pid else 2
            cv2.circle(frame,(px_,py_),sz2,col,-1)
            if pid==gs.local_pid:
                ex=int(px_+math.cos(p.angle)*9); ey=int(py_+math.sin(p.angle)*9)
                cv2.line(frame,(px_,py_),(ex,ey),PAL['white'],1)
        if gs.bomb_planted:
            bpx=mx+int(gs.bomb_x*scale); bpy=my+int(gs.bomb_y*scale)
            blink=int(time.time()*5)%2
            cv2.circle(frame,(bpx,bpy),5,PAL['bomb_red'] if blink else PAL['yellow'],2)

# ── Input ──
class Input:
    HOLD=0.1
    def __init__(self):
        self.mouse_dx=0.0; self.last_mouse=None
        self.lmb=False; self.rmb=False; self.fire_edge=False
        self.sensitivity=0.0025; self.key_time={}

    def mouse_cb(self,event,x,y,flags,param):
        if event==cv2.EVENT_MOUSEMOVE:
            if self.last_mouse is not None:
                dx=x-self.last_mouse[0]
                if abs(dx)<250: self.mouse_dx+=dx*self.sensitivity
            self.last_mouse=(x,y)
        elif event==cv2.EVENT_LBUTTONDOWN: self.lmb=True;  self.fire_edge=True
        elif event==cv2.EVENT_LBUTTONUP:   self.lmb=False
        elif event==cv2.EVENT_RBUTTONDOWN: self.rmb=True
        elif event==cv2.EVENT_RBUTTONUP:   self.rmb=False

    def press(self,key,now): self.key_time[key]=now
    def held(self,key,now):  return (now-self.key_time.get(key,0))<self.HOLD

    def warp(self):
        try:
            if platform.system()=='Windows':
                import ctypes; ctypes.windll.user32.SetCursorPos(W//2,H//2)
                self.last_mouse=None
            elif platform.system()=='Linux':
                os.system(f'xdotool mousemove {W//2} {H//2} 2>/dev/null &')
                self.last_mouse=None
        except: pass

# ── Main Game ──
class CS16:
    def __init__(self,mode,host_ip=None,name='Player',team='CT'):
        self.gs=GameState(); self.hud=HUD(self.gs)
        self.inp=Input(); self.mode=mode; self.name=name; self.team=team
        self.net=None; self.running=True
        self._semi=False; self._last_step=0.0
        self._bot_state={}

        if mode in('solo','host'):
            p=self.gs.add_player(0,name,team)
            self.gs.local_pid=0
            if team=='T': p.has_bomb=True
            if mode=='solo': self._spawn_bots()

        elif mode=='join':
            self._connect(host_ip)

    def _spawn_bots(self):
        bnames={'CT':['HeatoN','f0rest','Zehn','neo'],'T':['GeT_RiGhT','simple','coldzera','GuardiaN','NiKo']}
        pt=self.team; et='CT' if pt=='T' else 'T'
        pid=1
        for n in bnames[pt][:4]:
            bp=self.gs.add_player(pid,n,pt); pid+=1
        for n in bnames[et][:5]:
            bp=self.gs.add_player(pid,n,et)
            if et=='T' and pid==5: bp.has_bomb=True
            pid+=1
        for pid2 in self.gs.players:
            if pid2!=0: self._bot_state[pid2]={'last_shoot':0.0,'plant_start':0.0}

    def _connect(self,ip):
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        s.connect((ip,PORT)); self.net=s; self._nbuf=b''
        threading.Thread(target=self._recv_loop,daemon=True).start()
        self._send({'type':'join','name':self.name,'team':self.team})
        time.sleep(0.5)

    def _send(self,msg):
        if not self.net: return
        d=json.dumps(msg).encode()
        try: self.net.sendall(struct.pack('!I',len(d))+d)
        except: pass

    def _recv_loop(self):
        buf=b''
        while self.running:
            try:
                chunk=self.net.recv(8192)
                if not chunk: break
                buf+=chunk
                while len(buf)>=4:
                    ml=struct.unpack('!I',buf[:4])[0]
                    if len(buf)<4+ml: break
                    msg=json.loads(buf[4:4+ml]); buf=buf[4+ml:]
                    self._handle_net(msg)
            except: break

    def _handle_net(self,msg):
        gs=self.gs; t=msg.get('type')
        if t=='welcome': gs.local_pid=msg['pid']
        elif t=='state':
            for spid,pd in msg.get('players',{}).items():
                pid=int(spid)
                if pid not in gs.players:
                    sp=T_SPAWNS if pd['team']=='T' else CT_SPAWNS
                    gs.players[pid]=Player(pid,pd['name'],pd['team'],sp[0])
                p=gs.players[pid]
                p.x=pd['x']; p.y=pd['y']; p.angle=pd['angle']
                p.hp=pd['hp']; p.alive=pd['alive']
            gs.phase=msg.get('phase',gs.phase)

    def _move(self,lp,dt,now):
        lp.angle+=self.inp.mouse_dx; self.inp.mouse_dx=0
        if lp.crouching: mspd=0.034
        elif lp.walking: mspd=0.030
        else:            mspd=0.060
        if lp.slot=='awp' and not lp.zoomed: mspd*=0.85
        mspd*=lp.stamina
        inp=self.inp
        fwd=int(inp.held(ord('w'),now) or inp.held(ord('W'),now))
        bck=int(inp.held(ord('s'),now) or inp.held(ord('S'),now))
        lft=int(inp.held(ord('a'),now) or inp.held(ord('A'),now))
        rgt=int(inp.held(ord('d'),now) or inp.held(ord('D'),now))
        mx=math.cos(lp.angle)*(fwd-bck)+math.cos(lp.angle+math.pi/2)*(rgt-lft)
        my=math.sin(lp.angle)*(fwd-bck)+math.sin(lp.angle+math.pi/2)*(rgt-lft)
        mag=math.hypot(mx,my)
        if mag>0: mx/=mag; my/=mag
        accel=min(1,14*dt)
        lp.vel_x+=(mx*mspd-lp.vel_x)*accel
        lp.vel_y+=(my*mspd-lp.vel_y)*accel
        gmap=self.gs.map
        nx=lp.x+lp.vel_x; ny=lp.y+lp.vel_y
        if not gmap.is_wall(nx,lp.y): lp.x=nx
        else: lp.vel_x=0
        if not gmap.is_wall(lp.x,ny): lp.y=ny
        else: lp.vel_y=0
        spd=math.hypot(lp.vel_x,lp.vel_y)
        step_int=0.33 if lp.crouching else 0.26 if not lp.walking else 0.35
        if spd>0.006 and now-self._last_step>step_int:
            self._last_step=now
            play_snd('footstep',0.08 if lp.walking else 0.28 if lp.crouching else 0.38)
        if lp.on_ground: lp.stamina=min(1.0,lp.stamina+dt*0.9)

    def _shoot(self,lp,gs,now):
        if not lp.alive or gs.phase not in('live','planted'): return
        if lp.reload_end>now: return
        wd=lp.weapon; wname=lp.slot
        if now-lp.last_shot<wd.get('rof',0.1): return
        if not wd.get('auto',False):
            if not self._semi: return
            self._semi=False
        if wname=='knife':
            lp.last_shot=now; lp.recoil_v=0.2
            for pid,p in gs.players.items():
                if pid==gs.local_pid or not p.alive or p.team==lp.team: continue
                if math.hypot(p.x-lp.x,p.y-lp.y)<1.6:
                    p.take_damage(wd['dmg'],'body')
                    self._reg_kill(lp,p,'knife',now)
            return
        if wd.get('mag',0)<=0: self._reload(lp,now); return
        wd['mag']-=1; lp.last_shot=now
        play_snd(wname,0.55)
        # Spray + spread
        sh=sv=0.0
        sp=SPRAY.get(wname)
        if sp and lp.shot_count<len(sp): sh,sv=sp[lp.shot_count]
        lp.shot_count+=1
        spread=lp.effective_spread()
        fire_angle=lp.angle+sh+random.gauss(0,spread)+lp.recoil_h
        lp.recoil_h+=sh*0.28; lp.recoil_v=min(1.0,lp.recoil_v+abs(sv)*0.5+0.22)
        # Hitscan
        hit_pid=None; hit_dist=MAX_DEPTH; hit_box='body'
        for pid,p in gs.players.items():
            if pid==gs.local_pid or not p.alive or p.team==lp.team: continue
            dx=p.x-lp.x; dy=p.y-lp.y; dist=math.hypot(dx,dy)
            if dist>MAX_DEPTH: continue
            ang_to=math.atan2(dy,dx)
            ang_diff=abs(((ang_to-fire_angle+math.pi)%PI2)-math.pi)
            tol=max(0.04,0.22/max(dist,0.5))
            if ang_diff>tol: continue
            blocked=False
            steps=max(1,int(dist*8))
            for st in range(1,steps):
                if gs.map.is_wall(lp.x+dx/dist*st/8,lp.y+dy/dist*st/8): blocked=True; break
            if blocked: continue
            if dist<hit_dist:
                hit_dist=dist; hit_pid=pid
                r=random.random()
                hit_box='head' if r<0.15 else('legs' if r>0.85 else 'body')
        if hit_pid is not None:
            target=gs.players[hit_pid]
            hs={'head':wd.get('hs',1.5),'body':1.0,'legs':0.75}.get(hit_box,1.0)
            dmg=int(wd['dmg']*hs)
            target.take_damage(dmg,hit_box)
            gs.hit_markers.append((now,not target.alive))
            if not target.alive:
                lp.money=min(16000,lp.money+300)
                self._reg_kill(lp,target,wname,now)
            elif target.pid==gs.local_pid:
                target.dmg_indicators.append((math.atan2(lp.y-target.y,lp.x-target.x),now))
        if wd['mag']==0: self._reload(lp,now)

    def _reload(self,lp,now):
        wn=lp.slot; wd=lp.weapon; proto=WEAPONS.get(wn,{})
        if proto.get('mag',0)==0 or wd.get('ammo',0)==0: return
        rd=proto.get('reload',2.2); lp.reload_end=now+rd
        lp.shot_count=0; lp.recoil_h=0; play_snd('reload',0.45)
        need=proto['mag']-wd['mag']; give=min(need,wd['ammo'])
        wd['mag']+=give; wd['ammo']-=give

    def _reg_kill(self,killer,victim,weapon,now):
        if not victim.alive:
            killer.kills+=1; victim.deaths+=1
            self.gs.kill_feed.appendleft((killer.name,victim.name,weapon,now))
            self.gs.check_round()

    def _throw(self,lp,gs,gname,now):
        wd=lp.weapons.get(gname)
        if not wd or wd.get('mag',0)<=0: return
        wd['mag']-=1; spd=6.0
        gs.projectiles.append(Projectile(gname,lp.pid,lp.team,lp.x,lp.y,
                                          math.cos(lp.angle)*spd,math.sin(lp.angle)*spd))

    def _interact(self,lp,gs,now):
        if lp.has_bomb and not gs.bomb_planted and lp.team=='T':
            near=gs.map.near_site(lp.x,lp.y,SITE_A) or gs.map.near_site(lp.x,lp.y,SITE_B)
            if near:
                if not lp.is_planting: lp.is_planting=True; lp.plant_start=now; return
                if now-lp.plant_start>=3.2:
                    lp.is_planting=False; gs.bomb_planted=True
                    gs.bomb_x=lp.x; gs.bomb_y=lp.y; gs.bomb_plant_time=now
                    gs.phase='planted'; lp.has_bomb=False
                    gs.say('*** BOMB PLANTED ***'); play_snd('plant_beep',1.0)
                    if self.net: self._send({'type':'plant'})
                return
            else: lp.is_planting=False
        else: lp.is_planting=False
        if gs.bomb_planted and not gs.bomb_defused and lp.team=='CT':
            if math.hypot(lp.x-gs.bomb_x,lp.y-gs.bomb_y)<1.8:
                dt2=gs.DEFUSE_TIME*(0.5 if lp.defkit else 1.0)
                if not lp.is_defusing: lp.is_defusing=True; lp.defuse_start=now; return
                if now-lp.defuse_start>=dt2:
                    lp.is_defusing=False; gs.bomb_defused=True
                    gs.say('BOMB DEFUSED!'); gs.check_round()
                    if self.net: self._send({'type':'defuse'})
                return
            else: lp.is_defusing=False
        else: lp.is_defusing=False

    def _buy(self,lp,item,gs):
        if gs.phase!='buy': return
        wd=WEAPONS.get(item)
        if not wd or lp.money<wd['price']: return
        if item=='vest':     lp.armor=100; lp.money-=wd['price']
        elif item=='vesthelm': lp.armor=100; lp.helmet=True; lp.money-=wd['price']
        elif item=='defkit':
            if lp.team=='CT': lp.defkit=True; lp.money-=wd['price']
        elif item not in lp.weapons:
            lp.weapons[item]=dict(wd); lp.money-=wd['price']; lp.switch_slot(item)
        if self.net: self._send({'type':'buy','item':item})

    def _bots(self,gs,now,dt):
        for pid,p in list(gs.players.items()):
            if pid==0 or not p.alive: continue
            st=self._bot_state.get(pid); 
            if st is None: continue
            enemies=[e for e in gs.players.values() if e.team!=p.team and e.alive]
            if not enemies: continue
            tgt=min(enemies,key=lambda e:math.hypot(e.x-p.x,e.y-p.y))
            dist=math.hypot(tgt.x-p.x,tgt.y-p.y)
            want=math.atan2(tgt.y-p.y,tgt.x-p.x)
            diff=((want-p.angle+math.pi)%PI2)-math.pi
            p.angle+=diff*min(1.0,dt*3.5)
            if dist>2.8:
                spd=0.045; nx=p.x+math.cos(p.angle)*spd; ny=p.y+math.sin(p.angle)*spd
                if not gs.map.is_wall(nx,p.y): p.x=nx
                if not gs.map.is_wall(p.x,ny): p.y=ny
            rof=p.weapon.get('rof',0.12)
            if dist<13 and now-st['last_shoot']>rof+random.uniform(0,0.45):
                st['last_shoot']=now
                acc=max(0.08,0.72-dist*0.055)
                if random.random()<acc:
                    hbox='head' if random.random()<0.12 else 'body'
                    hs={'head':p.weapon.get('hs',1.5),'body':1.0}.get(hbox,1.0)
                    dmg=int(p.weapon['dmg']*hs)
                    play_snd(p.slot,0.25)
                    tgt.take_damage(dmg,hbox)
                    if not tgt.alive: self._reg_kill(p,tgt,p.slot,now)
                    elif tgt.pid==gs.local_pid:
                        tgt.dmg_indicators.append((math.atan2(p.y-tgt.y,p.x-tgt.x),now))
            if p.team=='T' and p.has_bomb and not gs.bomb_planted and gs.phase=='live':
                if gs.map.near_site(p.x,p.y,SITE_A,3.5):
                    if now-st.get('plant_start',0)>7:
                        gs.bomb_planted=True; gs.bomb_x=p.x; gs.bomb_y=p.y
                        gs.bomb_plant_time=now; gs.phase='planted'
                        p.has_bomb=False; gs.say('*** BOMB PLANTED ***')
                        play_snd('plant_beep',1.0); st['plant_start']=now

    def _draw_weapon(self,frame,lp,now):
        wn=lp.slot; rv=int(lp.recoil_v*65); swx=int(math.sin(now*1.8)*1.5)
        bx=W-275+swx; by=H-105+rv
        def box(x,y,w,h,c,bc=None):
            cv2.rectangle(frame,(x,y),(x+w,y+h),c,-1)
            if bc: cv2.rectangle(frame,(x,y),(x+w,y+h),bc,1)
        if wn=='knife':
            pts=np.array([[bx+58,by+28],[bx+88,by-12],[bx+96,by-16],[bx+91,by+4]],np.int32)
            cv2.fillPoly(frame,[pts],(88,88,108))
            cv2.polylines(frame,[pts],True,(118,118,138),1)
        elif wn in('awp','scout','sg550'):
            box(bx,by+8,188,16,(53,53,63),(78,78,88))
            box(bx+42,by,58,26,(63,63,73),(83,83,93))
            box(bx+58,by-8,28,10,(48,48,58))
            cv2.rectangle(frame,(bx+60,by-6),(bx+86,by+2),(0,200,200),1)
            if lp.zoomed: cv2.putText(frame,'[ SCOPE ]',(bx+38,by-18),cv2.FONT_HERSHEY_SIMPLEX,0.3,(0,200,200),1)
        elif wn in('ak47','m4a1','famas','sg552'):
            box(bx,by+10,158,19,(48,63,53),(68,83,68))
            box(bx+18,by+5,78,29,(53,68,58),(73,88,73))
            box(bx+28,by+30,28,19,(43,53,48))
            box(bx+103,by+8,53,7,(38,48,43))
        elif wn in('mp5','mac10','tmp'):
            box(bx+8,by+12,118,17,(53,53,63),(68,68,78))
            box(bx+22,by+8,58,24,(58,58,68))
            box(bx+32,by+29,23,17,(48,48,58))
        else:
            box(bx+22,by+10,78,15,(63,63,78),(83,83,98))
            box(bx+28,by+5,48,25,(68,68,83))
            box(bx+38,by+27,20,21,(58,58,73))
        if lp.recoil_v>0.45:
            fx=bx+(183 if wn in('awp','scout','sg550') else 160 if wn in('ak47','m4a1','famas','sg552') else 128 if wn in('mp5','mac10','tmp') else 102)
            fy=by+17; r2=random.randint(5,14)
            cv2.circle(frame,(fx,fy),r2,(0,210,255),-1)
            cv2.circle(frame,(fx,fy),r2//2,(150,255,255),-1)
        cv2.putText(frame,lp.weapon.get('name',wn),(bx+18,by+53),cv2.FONT_HERSHEY_SIMPLEX,0.36,PAL['gray'],1)
        if lp.reload_end>now:
            prog=max(0,1-(lp.reload_end-now)/WEAPONS.get(wn,{}).get('reload',2.2))
            cv2.putText(frame,f'RELOAD {int(prog*100)}%',(W//2-58,H//2+52),cv2.FONT_HERSHEY_SIMPLEX,0.52,PAL['yellow'],2)

    def _vignette(self,frame,hp):
        ys=np.abs(np.arange(H)-H//2)/(H//2)
        xs=np.abs(np.arange(W)-W//2)/(W//2)
        xg,yg=np.meshgrid(xs,ys); d=np.sqrt(xg*xg+yg*yg)
        intensity=np.clip((d-0.55)/0.45*220,0,255).astype(np.uint8)
        vig=np.zeros((H,W,3),dtype=np.uint8); vig[:,:,2]=intensity
        cv2.addWeighted(vig,(30-hp)/30*0.65,frame,1,0,frame)

    def run(self):
        cv2.namedWindow('CS 1.6 Clone',cv2.WINDOW_NORMAL)
        cv2.resizeWindow('CS 1.6 Clone',W,H)
        cv2.setMouseCallback('CS 1.6 Clone',self.inp.mouse_cb)
        frame=np.zeros((H,W,3),dtype=np.uint8)
        last_t=time.time(); fps_t=time.time(); fps_cnt=0; fps_disp=0

        while self.running:
            now=time.time(); dt=min(now-last_t,0.05); last_t=now
            fps_cnt+=1
            if now-fps_t>1.0: fps_disp=fps_cnt; fps_cnt=0; fps_t=now
            gs=self.gs; lp=gs.local()

            # Phase ticks
            if lp:
                if gs.phase=='buy' and gs.time_left()<=0:
                    gs.phase='live'; gs.round_start=now
                elif gs.phase in('live','planted'):
                    gs.update_physics(dt,gs.local_pid); gs.check_round()
                elif gs.phase=='ended' and now-gs.announce_t>5.5:
                    if gs.round_num<gs.max_rounds: gs.new_round()
                    else: gs.say(f'GAME OVER  CT:{gs.ct_score}  T:{gs.t_score}')

            # Bot AI
            if self._bot_state and gs.phase in('live','planted'):
                self._bots(gs,now,dt)

            # Keys
            while True:
                key=cv2.waitKey(1)&0xFF
                if key==255: break
                if key==27: self.running=False; break
                self.inp.press(key,now)
                if lp and lp.alive:
                    if key in(ord('c'),ord('C')): lp.crouching=not lp.crouching
                    elif key in(ord('r'),ord('R')): self._reload(lp,now)
                    elif key in(ord('e'),ord('E')): self._interact(lp,gs,now)
                    elif key in(ord('g'),ord('G')):
                        for gn in['henade','flash','smoke','molotov']:
                            if gn in lp.weapons and lp.weapons[gn].get('mag',0)>0:
                                self._throw(lp,gs,gn,now); break
                    elif key in(ord('b'),ord('B')): gs.show_buy=not gs.show_buy
                    elif key==9: gs.show_score=not gs.show_score
                    elif key in(ord('f'),ord('F')): lp.zoomed=not lp.zoomed
                    elif ord('1')<=key<=ord('5'):
                        sl=list(lp.weapons.keys()); idx=key-ord('1')
                        if idx<len(sl): lp.switch_slot(sl[idx])
                    if gs.show_buy and gs.phase=='buy':
                        avail=T_BUY if lp.team=='T' else CT_BUY
                        if ord('1')<=key<=ord('9'):
                            bi=key-ord('1')
                            if bi<len(avail): self._buy(lp,avail[bi],gs)
                # Walking/crouching from shift/ctrl
                if lp:
                    lp.walking  =self.inp.held(225,now) or self.inp.held(226,now)
                    lp.crouching=self.inp.held(224,now) or self.inp.held(228,now)
                if self.inp.fire_edge: self._semi=True; self.inp.fire_edge=False

            if not self.running: break

            # Movement + interact hold
            if lp and lp.alive and gs.phase in('live','planted','buy'):
                self._move(lp,dt,now)
                if self.inp.held(ord('e'),now) or self.inp.held(ord('E'),now):
                    self._interact(lp,gs,now)

            # Shoot
            if lp and lp.alive and self.inp.lmb:
                self._shoot(lp,gs,now)

            # Recoil/flash decay
            if lp:
                lp.recoil_v=max(0,lp.recoil_v-dt*3.8)
                lp.recoil_h*=max(0,1-dt*5.5)
                lp.flash_alpha=max(0,lp.flash_alpha-dt*lp.flash_decay)

            self.inp.warp()

            # ── Render ──
            if lp and lp.alive:
                hh=HALF_H+int(lp.recoil_v*28)
                gs.rc.render(lp.x,lp.y,lp.angle,frame)
                # Smoke
                if any(math.hypot(lp.x-e.x,lp.y-e.y)<e.radius for e in gs.area_effects if e.kind=='smoke'):
                    cv2.addWeighted(np.full_like(frame,175),0.85,frame,0.15,0,frame)
                # Other players (simple colored quads)
                self._draw_players(frame,lp,gs)
                self._draw_weapon(frame,lp,now)
                if gs.show_buy:    self.hud.draw_buy(frame,lp)
                elif gs.show_score:self.hud.draw_scoreboard(frame)
                else:
                    self.hud.draw(frame,lp); self.hud.draw_crosshair(frame,lp)
                if lp.flash_alpha>0:
                    cv2.addWeighted(np.full_like(frame,255),lp.flash_alpha,frame,1-lp.flash_alpha,0,frame)
                if lp.hp<30: self._vignette(frame,lp.hp)
                if lp.zoomed and lp.slot in('awp','scout','sg550'):
                    frame[:H//4,:]=0; frame[3*H//4:,:]=0
            else:
                self.hud.draw_dead(frame,gs)
                if gs.show_score: self.hud.draw_scoreboard(frame)

            if lp: self.hud.draw_minimap(frame,lp,gs)
            cv2.putText(frame,f'FPS:{fps_disp}',(4,16),cv2.FONT_HERSHEY_SIMPLEX,0.36,PAL['dgray'],1)
            if self.mode=='host':
                try: ip=socket.gethostbyname(socket.gethostname())
                except: ip='?'
                cv2.putText(frame,f'HOST: {ip}:{PORT}',(4,32),cv2.FONT_HERSHEY_SIMPLEX,0.33,(0,180,80),1)
            cv2.imshow('CS 1.6 Clone',frame)

        cv2.destroyAllWindows()
        if self.net: self.net.close()

    def _draw_players(self,frame,lp,gs):
        # Collect sprites with depth, then draw back-to-front
        sprites=[]
        for pid,p in gs.players.items():
            if pid==gs.local_pid or not p.alive: continue
            dx=p.x-lp.x; dy=p.y-lp.y
            dist=math.hypot(dx,dy)
            if dist<0.1 or dist>MAX_DEPTH: continue
            # Camera transform
            ca=math.cos(-lp.angle); sa=math.sin(-lp.angle)
            tx=ca*dx-sa*dy; tz=sa*dx+ca*dy
            if tz<=0.1: continue
            sx=int((W/2)*(1+tx/tz))
            sh=min(H,abs(int(H/tz)))
            sprites.append((tz,sx,sh,p))
        sprites.sort(key=lambda x:-x[0])
        for tz,sx,sh,p in sprites:
            sw=sh//2
            x1=max(0,sx-sw//2); x2=min(W-1,sx+sw//2)
            top=max(0,HALF_H-sh//2); bot=min(H-1,HALF_H+sh//2)
            if x2<=x1 or bot<=top: continue
            col=PAL['ct_blue'] if p.team=='CT' else PAL['t_gold']
            # Draw as simple quads (CS 1.6 style box model)
            # Body
            bh=(bot-top)
            mid=top+bh//2
            cv2.rectangle(frame,(x1,mid),(x2,bot),col,-1)      # legs
            # Shirt (slightly lighter)
            tc=tuple(min(255,c+40) for c in col)
            cv2.rectangle(frame,(x1,top+bh//5),(x2,mid),tc,-1)  # torso
            # Head
            hc=tuple(min(255,c+20) for c in col)
            hs2=sh//6; hx=sx; hy=top+bh//6
            cv2.circle(frame,(hx,hy),max(2,hs2),hc,-1)
            # Name + HP bar
            if abs(sx-W//2)<W//2+50:
                ny2=max(12,top-16)
                cv2.putText(frame,p.name[:8],(sx-20,ny2),cv2.FONT_HERSHEY_SIMPLEX,0.32,PAL['white'],1)
                bw=36; bxp=sx-bw//2; byp=ny2-8
                if 0<bxp<W-bw and 0<byp<H:
                    cv2.rectangle(frame,(bxp,byp),(bxp+bw,byp+4),(40,40,40),-1)
                    hw2=int(bw*p.hp/100)
                    hpc=PAL['green'] if p.hp>50 else PAL['yellow'] if p.hp>25 else PAL['red']
                    cv2.rectangle(frame,(bxp,byp),(bxp+hw2,byp+4),hpc,-1)

# ── Menu ──
def menu():
    cv2.namedWindow('CS 1.6 Clone',cv2.WINDOW_NORMAL)
    cv2.resizeWindow('CS 1.6 Clone',W,H)
    frame=np.zeros((H,W,3),dtype=np.uint8)

    def bg(f):
        f[:]=(8,6,14)
        for i in range(0,H,36): cv2.line(f,(0,i),(W,i),(14,11,22),1)
        for i in range(0,W,36): cv2.line(f,(i,0),(i,H),(14,11,22),1)

    def draw_menu(f,sel,opts,title,sub=''):
        bg(f)
        ts=cv2.getTextSize(title,cv2.FONT_HERSHEY_SIMPLEX,2.0,3)[0]
        cv2.putText(f,title,((W-ts[0])//2,H//4),cv2.FONT_HERSHEY_SIMPLEX,2.0,(0,180,255),3)
        cv2.putText(f,'Faithful CS 1.6 Recreation',(W//2-158,H//4+42),cv2.FONT_HERSHEY_SIMPLEX,0.55,(80,60,140),1)
        if sub: cv2.putText(f,sub,(W//2-200,H//4+70),cv2.FONT_HERSHEY_SIMPLEX,0.44,(100,100,130),1)
        for i,(label,_) in enumerate(opts):
            y=H//2+10+i*58; bx=W//2-220
            cv2.rectangle(f,(bx,y-32),(bx+440,y+12),(28,18,58) if i==sel else (10,8,20),-1)
            cv2.rectangle(f,(bx,y-32),(bx+440,y+12),(0,180,255) if i==sel else (35,35,70),2)
            tc=(0,220,255) if i==sel else (140,140,180)
            cv2.putText(f,f'{"► " if i==sel else "  "}[{i+1}] {label}',(bx+18,y),cv2.FONT_HERSHEY_SIMPLEX,0.68,tc,2 if i==sel else 1)
        cv2.putText(f,'W/S navigate  •  Enter/Number select  •  ESC quit',(W//2-240,H-28),cv2.FONT_HERSHEY_SIMPLEX,0.38,(60,60,90),1)

    def text_input(f,prompt,hint=''):
        s=''
        while True:
            bg(f)
            cv2.putText(f,prompt,(W//2-200,H//2-30),cv2.FONT_HERSHEY_SIMPLEX,0.85,(0,180,255),2)
            if hint: cv2.putText(f,hint,(W//2-200,H//2+80),cv2.FONT_HERSHEY_SIMPLEX,0.4,(80,80,100),1)
            cv2.putText(f,s+'_',(W//2-200,H//2+30),cv2.FONT_HERSHEY_SIMPLEX,1.0,PAL['white'],2)
            cv2.imshow('CS 1.6 Clone',f); k=cv2.waitKey(30)&0xFF
            if k==13: return s if s else hint
            elif k==27: return None
            elif k==8: s=s[:-1]
            elif 32<=k<127 and len(s)<24: s+=chr(k)

    opts=[('Solo vs Bots','solo'),('Host LAN Game','host'),('Join LAN Game','join'),('Quit','quit')]
    sel=0
    while True:
        draw_menu(frame,sel,opts,'CS 1.6 CLONE')
        cv2.imshow('CS 1.6 Clone',frame); k=cv2.waitKey(30)&0xFF
        if k==27: return None
        elif k in(ord('w'),ord('W'),82): sel=(sel-1)%len(opts)
        elif k in(ord('s'),ord('S'),84): sel=(sel+1)%len(opts)
        elif k==13:
            mode=opts[sel][1]
            if mode=='quit': return None
            break
        elif ord('1')<=k<=ord('4'):
            mode=opts[k-ord('1')][1]
            if mode=='quit': return None
            break

    name=text_input(frame,'Enter your name:') or 'Player'
    if name is None: return None

    team_opts=[('Counter-Terrorist (CT)','CT'),('Terrorist (T)','T')]
    sel2=0
    while True:
        draw_menu(frame,sel2,team_opts,'SELECT TEAM',f'Welcome, {name}!')
        cv2.imshow('CS 1.6 Clone',frame); k=cv2.waitKey(30)&0xFF
        if k==27: return None
        elif k in(ord('w'),ord('W'),82): sel2=(sel2-1)%2
        elif k in(ord('s'),ord('S'),84): sel2=(sel2+1)%2
        elif k==13: team=team_opts[sel2][1]; break
        elif k==ord('1'): team='CT'; break
        elif k==ord('2'): team='T'; break

    host_ip=None
    if mode=='join':
        host_ip=text_input(frame,'Host IP address:','192.168.1.x')
        if host_ip is None: return None

    return mode,name,team,host_ip

# ── Entry ──
if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--solo',action='store_true')
    ap.add_argument('--host',action='store_true')
    ap.add_argument('--join',metavar='IP')
    ap.add_argument('--name',default='')
    ap.add_argument('--team',default='CT',choices=['T','CT'])
    args=ap.parse_args()
    if args.solo or args.host or args.join:
        mode='solo' if args.solo else('host' if args.host else 'join')
        CS16(mode,host_ip=args.join,name=args.name or 'Player',team=args.team).run()
    else:
        r=menu()
        if r:
            mode,name,team,host_ip=r
            try: CS16(mode,host_ip=host_ip,name=name,team=team).run()
            except Exception as e:
                import traceback; print(f'Error: {e}'); traceback.print_exc()
