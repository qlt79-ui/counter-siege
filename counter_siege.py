#!/usr/bin/env python3
"""
COUNTER SIEGE - A CS-Inspired Tactical FPS
Full raycasting 3D engine, CS mechanics, LAN multiplayer
Controls: WASD=move, Mouse=look, LMB=shoot, R=reload, G=nade, B=buy, 
          E=plant/defuse, Tab=scoreboard, F=flashbang buy, 1-5=weapons
"""

import cv2
import numpy as np
import socket
import threading
import json
import time
import math
import random
import struct
import sys
import os
import argparse
from collections import defaultdict

# ─────────────────────────────────────────────
#  CONSTANTS & CONFIG
# ─────────────────────────────────────────────
W, H = 1280, 720
HALF_H = H // 2
FOV = math.pi / 3
HALF_FOV = FOV / 2
NUM_RAYS = W
RAY_STEP = FOV / NUM_RAYS
MAX_DEPTH = 20
CELL = 64
FPS_TARGET = 60
PORT = 7777
MAX_PLAYERS = 10

# Colors (BGR)
C = {
    'sky':      (80, 40, 20),
    'sky2':     (120, 70, 30),
    'floor':    (30, 30, 30),
    'floor2':   (45, 45, 45),
    'wall_t':   (60, 80, 180),   # T-side walls
    'wall_ct':  (160, 120, 60),  # CT-side walls
    'wall_mid': (100, 100, 100),
    'wall_a':   (40, 120, 40),   # A site
    'wall_b':   (120, 40, 40),   # B site
    'hud_bg':   (0, 0, 0),
    'green':    (0, 200, 80),
    'red':      (0, 60, 220),
    'yellow':   (0, 220, 220),
    'white':    (255, 255, 255),
    'orange':   (0, 165, 255),
    'gray':     (150, 150, 150),
    'ct_blue':  (220, 120, 30),
    't_gold':   (30, 160, 220),
    'bomb_red': (0, 0, 255),
    'bomb_grn': (0, 255, 0),
    'crosshair':(0, 255, 120),
    'dmg':      (0, 80, 255),
    'flash':    (255, 255, 255),
    'hit':      (0, 0, 255),
}

# ─────────────────────────────────────────────
#  MAP DEFINITION  (20x20 grid, 0=empty)
#  1=wall, 2=wall(A), 3=wall(B), 4=box/cover
#  A site = top-right, B site = bottom-left
# ─────────────────────────────────────────────
MAP_DATA = [
    "####################",
    "#T.................#",
    "#..###.....###.....#",
    "#..#.........#.....#",
    "#..#....4....#..BB.#",
    "#..###...4...###...#",
    "#.....4..........A.#",
    "#......4.......AAA.#",
    "#..###...4...###...#",
    "#..#.........#.....#",
    "#..#....4....#.....#",
    "#..###.....###.....#",
    "#......4...........#",
    "#.4.4..............#",
    "#......4...4.......#",
    "#...........4......#",
    "#.....###..........#",
    "#.....#............#",
    "#C....#............#",
    "####################",
]

WALL_CHAR = {'#': 1, 'A': 2, 'B': 3, '4': 4}
WALL_COLORS = {
    1: [(80,80,110),(100,100,140)],
    2: [(30,100,30),(40,130,40)],
    3: [(80,30,30),(110,40,40)],
    4: [(60,50,40),(90,75,60)],
}
A_SITE = (16, 6)   # (col, row)
B_SITE = (3, 4)

# Spawn zones (col, row range)
T_SPAWNS  = [(1,1),(2,1),(1,2),(2,2),(1,3)]
CT_SPAWNS = [(1,18),(2,18),(1,17),(2,17),(3,18)]

# ─────────────────────────────────────────────
#  WEAPON DEFINITIONS
# ─────────────────────────────────────────────
WEAPONS = {
    'knife':   {'name':'Knife',    'damage':40,  'rof':0.8, 'reload':1.0, 'mag':0,   'ammo':0,   'price':0,    'spread':0.001,'auto':False,'range':1.5,'hitscan':False},
    'glock':   {'name':'Glock-18', 'damage':25,  'rof':0.12,'reload':2.0, 'mag':20,  'ammo':120, 'price':200,  'spread':0.03, 'auto':False,'range':20,'hitscan':True},
    'usp':     {'name':'USP-S',    'damage':35,  'rof':0.15,'reload':2.2, 'mag':12,  'ammo':72,  'price':300,  'spread':0.02, 'auto':False,'range':20,'hitscan':True},
    'p250':    {'name':'P250',     'damage':38,  'rof':0.25,'reload':2.0, 'mag':13,  'ammo':52,  'price':300,  'spread':0.025,'auto':False,'range':20,'hitscan':True},
    'deagle':  {'name':'Desert Eagle','damage':98,'rof':0.5, 'reload':2.8,'mag':7,   'ammo':35,  'price':700,  'spread':0.04, 'auto':False,'range':20,'hitscan':True},
    'ak47':    {'name':'AK-47',    'damage':36,  'rof':0.1, 'reload':2.5, 'mag':30,  'ammo':90,  'price':2700, 'spread':0.05, 'auto':True, 'range':20,'hitscan':True},
    'm4a1':    {'name':'M4A1-S',   'damage':33,  'rof':0.09,'reload':2.3, 'mag':20,  'ammo':60,  'price':2900, 'spread':0.04, 'auto':True, 'range':20,'hitscan':True},
    'awp':     {'name':'AWP',      'damage':115, 'rof':1.5, 'reload':3.7, 'mag':5,   'ammo':30,  'price':4750, 'spread':0.001,'auto':False,'range':20,'hitscan':True},
    'mp5':     {'name':'MP5-SD',   'damage':27,  'rof':0.08,'reload':2.1, 'mag':30,  'ammo':120, 'price':1500, 'spread':0.04, 'auto':True, 'range':20,'hitscan':True},
    'sg553':   {'name':'SG 553',   'damage':30,  'rof':0.1, 'reload':2.8, 'mag':30,  'ammo':90,  'price':2750, 'spread':0.035,'auto':True, 'range':20,'hitscan':True},
    'henade':  {'name':'HE Grenade','damage':90, 'rof':1.0, 'reload':0,   'mag':1,   'ammo':1,   'price':300,  'spread':0,    'auto':False,'range':8,'hitscan':False},
    'flash':   {'name':'Flashbang','damage':0,   'rof':1.0, 'reload':0,   'mag':1,   'ammo':2,   'price':200,  'spread':0,    'auto':False,'range':8,'hitscan':False},
    'smoke':   {'name':'Smoke',    'damage':0,   'rof':1.0, 'reload':0,   'mag':1,   'ammo':1,   'price':300,  'spread':0,    'auto':False,'range':8,'hitscan':False},
    'bomb':    {'name':'C4',       'damage':500, 'rof':3.0, 'reload':0,   'mag':1,   'ammo':1,   'price':0,    'spread':0,    'auto':False,'range':2,'hitscan':False},
    'vest':    {'name':'Kevlar',   'damage':0,   'rof':0,   'reload':0,   'mag':0,   'ammo':0,   'price':650,  'spread':0,    'auto':False,'range':0,'hitscan':False},
    'vesthelm':{'name':'K+Helm',   'damage':0,   'rof':0,   'reload':0,   'mag':0,   'ammo':0,   'price':1000, 'spread':0,    'auto':False,'range':0,'hitscan':False},
}

T_WEAPONS  = ['glock','ak47','sg553','mp5','henade','flash','smoke','bomb','deagle','p250']
CT_WEAPONS = ['usp','m4a1','mp5','awp','henade','flash','smoke','deagle','p250']

# ─────────────────────────────────────────────
#  EFFECTS / PARTICLES
# ─────────────────────────────────────────────
class Effect:
    def __init__(self, kind, x, y, ttl, **kw):
        self.kind = kind; self.x = x; self.y = y
        self.ttl = ttl; self.born = time.time()
        self.__dict__.update(kw)
    @property
    def alive(self): return time.time() - self.born < self.ttl
    @property
    def frac(self): return (time.time()-self.born)/self.ttl

# ─────────────────────────────────────────────
#  GAME MAP
# ─────────────────────────────────────────────
class GameMap:
    def __init__(self):
        self.grid = []
        for row in MAP_DATA:
            r = []
            for ch in row:
                r.append(WALL_CHAR.get(ch, 0))
            self.grid.append(r)
        self.rows = len(self.grid)
        self.cols = len(self.grid[0]) if self.grid else 0

    def is_wall(self, col, row):
        c, r = int(col), int(row)
        if c < 0 or r < 0 or c >= self.cols or r >= self.rows:
            return True
        return self.grid[r][c] != 0

    def wall_type(self, col, row):
        c, r = int(col), int(row)
        if c < 0 or r < 0 or c >= self.cols or r >= self.rows:
            return 1
        return self.grid[r][c]

    def near_site(self, px, py, site_col, site_row, dist=1.5):
        return abs(px - site_col - 0.5) < dist and abs(py - site_row - 0.5) < dist

# ─────────────────────────────────────────────
#  RAYCASTER
# ─────────────────────────────────────────────
class Raycaster:
    def __init__(self, gmap):
        self.map = gmap

    def cast(self, px, py, angle):
        """Returns list of (dist, wall_type, shade) for each column."""
        cols = []
        ray_angle = angle - HALF_FOV
        for col in range(NUM_RAYS):
            cos_a = math.cos(ray_angle)
            sin_a = math.sin(ray_angle)
            # DDA
            if cos_a == 0: cos_a = 1e-9
            if sin_a == 0: sin_a = 1e-9

            map_x, map_y = int(px), int(py)
            dx = abs(1/cos_a); dy = abs(1/sin_a)

            step_x = 1 if cos_a > 0 else -1
            step_y = 1 if sin_a > 0 else -1

            side_x = (map_x+1 - px)*dx if cos_a>0 else (px-map_x)*dx
            side_y = (map_y+1 - py)*dy if sin_a>0 else (py-map_y)*dy

            side = 0; dist = 0; wtype = 1
            for _ in range(MAX_DEPTH*4):
                if side_x < side_y:
                    side_x += dx; map_x += step_x; side = 0
                else:
                    side_y += dy; map_y += step_y; side = 1
                if self.map.is_wall(map_x, map_y):
                    wtype = self.map.wall_type(map_x, map_y)
                    if side == 0:
                        dist = (map_x - px + (1-step_x)/2) / cos_a
                    else:
                        dist = (map_y - py + (1-step_y)/2) / sin_a
                    break

            dist = max(0.01, dist)
            # Fix fisheye
            dist *= math.cos(ray_angle - angle)
            cols.append((dist, wtype, side))
            ray_angle += RAY_STEP
        return cols

# ─────────────────────────────────────────────
#  PLAYER
# ─────────────────────────────────────────────
class Player:
    def __init__(self, pid, name, team, spawn):
        self.pid = pid
        self.name = name
        self.team = team  # 'T' or 'CT'
        self.x, self.y = float(spawn[0])+0.5, float(spawn[1])+0.5
        self.angle = math.pi/2
        self.hp = 100
        self.armor = 0
        self.helmet = False
        self.alive = True
        self.money = 800
        self.kills = 0
        self.deaths = 0
        self.score = 0

        # Weapon state
        self.weapons = {'knife': dict(WEAPONS['knife'])}
        if team == 'T':
            self.weapons['glock'] = dict(WEAPONS['glock'])
        else:
            self.weapons['usp'] = dict(WEAPONS['usp'])
        self.current_weapon = list(self.weapons.keys())[1] if len(self.weapons)>1 else 'knife'
        self.reload_time = 0
        self.last_shot = 0
        self.recoil = 0.0

        # Grenades
        self.has_bomb = (team == 'T') and (pid == 0)  # first T gets bomb
        self.grenades = {}

        # State
        self.is_planting = False
        self.plant_start = 0
        self.is_defusing = False
        self.defuse_start = 0
        self.flash_level = 0  # 0-1
        self.in_smoke = False
        self.speed = 0.05
        self.crouching = False

    @property
    def weapon(self):
        return self.weapons.get(self.current_weapon, WEAPONS['knife'])

    def switch_weapon(self, name):
        if name in self.weapons:
            self.current_weapon = name
            self.reload_time = 0

    def take_damage(self, dmg, hit_head=False):
        if not self.alive: return 0
        if hit_head and self.helmet:
            dmg = int(dmg * 0.5)
        elif hit_head:
            dmg = int(dmg * 1.4)
        if self.armor > 0:
            absorbed = min(self.armor, int(dmg * 0.5))
            self.armor -= absorbed
            dmg -= absorbed
        self.hp -= dmg
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return dmg

    def respawn(self, spawn):
        self.x, self.y = float(spawn[0])+0.5, float(spawn[1])+0.5
        self.hp = 100
        self.armor = 0
        self.helmet = False
        self.alive = True
        self.is_planting = False
        self.is_defusing = False
        self.flash_level = 0
        self.reload_time = 0

# ─────────────────────────────────────────────
#  GAME STATE
# ─────────────────────────────────────────────
class GameState:
    def __init__(self):
        self.map = GameMap()
        self.raycaster = Raycaster(self.map)
        self.players = {}
        self.local_pid = 0

        # Round
        self.round_num = 1
        self.max_rounds = 30
        self.t_score = 0
        self.ct_score = 0
        self.round_phase = 'buy'  # buy / live / planted / ended / halftime
        self.round_start = time.time()
        self.buy_time = 15.0
        self.round_time = 115.0
        self.plant_time = 40.0
        self.defuse_time = 10.0
        self.bomb_planted = False
        self.bomb_plant_time = 0
        self.bomb_x = 0; self.bomb_y = 0
        self.bomb_defused = False
        self.bomb_exploded = False
        self.round_winner = None  # 'T' or 'CT' or None

        # Effects
        self.effects = []
        self.smokes = []   # [(x,y,ttl,born)]
        self.bullets = []  # [(x1,y1,x2,y2,ttl)]
        self.hit_markers = []  # [(screen_x, screen_y, ttl)]

        # HUD
        self.show_buy = False
        self.show_scoreboard = False
        self.kill_feed = []  # [(killer, victim, weapon, time)]
        self.chat_msgs = []
        self.damage_indicators = []  # [(angle, dmg, born, ttl)]
        self.round_announce = ''
        self.round_announce_time = 0

    def add_player(self, pid, name, team):
        spawns = T_SPAWNS if team == 'T' else CT_SPAWNS
        spawn = spawns[len([p for p in self.players.values() if p.team == team]) % len(spawns)]
        self.players[pid] = Player(pid, name, team, spawn)
        return self.players[pid]

    def local_player(self):
        return self.players.get(self.local_pid)

    def elapsed(self):
        return time.time() - self.round_start

    def time_left(self):
        if self.round_phase == 'buy':
            return max(0, self.buy_time - self.elapsed())
        elif self.round_phase == 'live':
            return max(0, self.round_time - self.elapsed())
        elif self.round_phase == 'planted':
            return max(0, self.plant_time - (time.time() - self.bomb_plant_time))
        return 0

    def announce(self, msg):
        self.round_announce = msg
        self.round_announce_time = time.time()

    def check_round_end(self):
        if self.round_phase in ('ended',): return
        t_alive = [p for p in self.players.values() if p.team=='T' and p.alive]
        ct_alive = [p for p in self.players.values() if p.team=='CT' and p.alive]
        t_players = [p for p in self.players.values() if p.team=='T']
        ct_players = [p for p in self.players.values() if p.team=='CT']

        if self.bomb_exploded:
            self.end_round('T', 'bomb_exploded')
        elif self.bomb_defused:
            self.end_round('CT', 'bomb_defused')
        elif self.round_phase == 'live' and self.time_left() <= 0:
            self.end_round('CT', 'time_up')
        elif not t_alive and t_players:
            self.end_round('CT', 'elim')
        elif not ct_alive and ct_players and not self.bomb_planted:
            self.end_round('T', 'elim')

    def end_round(self, winner, reason):
        self.round_phase = 'ended'
        self.round_winner = winner
        msgs = {
            'bomb_exploded': 'BOMB EXPLODED — Terrorists Win!',
            'bomb_defused':  'BOMB DEFUSED — Counter-Terrorists Win!',
            'time_up':       'TIME UP — Counter-Terrorists Win!',
            'elim':          f'{"Terrorists" if winner=="T" else "Counter-Terrorists"} Win! (Elimination)',
        }
        self.announce(msgs.get(reason, f'{winner} wins'))
        if winner == 'T': self.t_score += 1
        else: self.ct_score += 1

        # Economy: win/loss bonus
        losers = 'CT' if winner=='T' else 'T'
        for p in self.players.values():
            if p.team == winner:
                p.money = min(16000, p.money + 3250)
            else:
                p.money = min(16000, p.money + 1400)
            p.score = p.kills * 2 - p.deaths

    def new_round(self):
        self.round_num += 1
        self.round_phase = 'buy'
        self.round_start = time.time()
        self.bomb_planted = False
        self.bomb_defused = False
        self.bomb_exploded = False
        self.bomb_plant_time = 0
        self.round_winner = None
        self.effects.clear()
        self.smokes.clear()
        self.bullets.clear()

        # Respawn all
        t_idx = 0; ct_idx = 0
        for p in self.players.values():
            if p.team == 'T':
                spawn = T_SPAWNS[t_idx % len(T_SPAWNS)]; t_idx += 1
            else:
                spawn = CT_SPAWNS[ct_idx % len(CT_SPAWNS)]; ct_idx += 1
            p.respawn(spawn)
            # Give starting pistol ammo back
            for wname, w in p.weapons.items():
                proto = WEAPONS.get(wname, w)
                if 'ammo' in proto:
                    w['ammo'] = proto['ammo']

# ─────────────────────────────────────────────
#  RENDERER
# ─────────────────────────────────────────────
class Renderer:
    def __init__(self, gs):
        self.gs = gs
        self.frame = np.zeros((H, W, 3), dtype=np.uint8)
        self.zbuf = np.zeros(W, dtype=np.float32)

    def render(self):
        gs = self.gs
        lp = gs.local_player()
        frame = self.frame
        frame[:] = 0

        if lp is None or not lp.alive:
            self._draw_dead_screen(lp)
            return frame

        # ── Sky & Floor ──
        sky_top = np.array(C['sky'], dtype=np.uint8)
        sky_bot = np.array(C['sky2'], dtype=np.uint8)
        for y in range(HALF_H):
            t = y / HALF_H
            col = (sky_top * (1-t) + sky_bot * t).astype(np.uint8)
            frame[y, :] = col
        # Floor gradient
        fl_top = np.array(C['floor2'], dtype=np.uint8)
        fl_bot = np.array(C['floor'], dtype=np.uint8)
        for y in range(HALF_H, H):
            t = (y - HALF_H) / HALF_H
            col = (fl_top * (1-t) + fl_bot * t).astype(np.uint8)
            frame[y, :] = col

        # ── Raycasting walls ──
        rays = gs.raycaster.cast(lp.x, lp.y, lp.angle)
        for col_idx, (dist, wtype, side) in enumerate(rays):
            self.zbuf[col_idx] = dist
            wall_h = min(H, int(H / max(dist, 0.01)))
            top = HALF_H - wall_h // 2
            bot = top + wall_h

            colors = WALL_COLORS.get(wtype, [(100,100,100),(130,130,130)])
            base_col = np.array(colors[side], dtype=np.float32)
            # Lighting by distance
            brightness = max(0.2, 1.0 - dist / MAX_DEPTH)
            col = (base_col * brightness).astype(np.uint8)

            # Draw column
            draw_top = max(0, top)
            draw_bot = min(H-1, bot)
            if draw_bot > draw_top:
                frame[draw_top:draw_bot, col_idx] = col

        # ── Smoke clouds ──
        for sx, sy, ttl, born in gs.smokes:
            age = time.time() - born
            if age > ttl: continue
            alpha = min(1.0, age/0.5) * (1.0 - max(0, age-ttl+1.0))
            self._draw_sprite(frame, lp, sx, sy, 0.8, (180,180,180), alpha)

        # ── Bomb ──
        if gs.bomb_planted:
            self._draw_sprite(frame, lp, gs.bomb_x, gs.bomb_y, 0.3,
                              C['bomb_red'] if int(time.time()*4)%2 else C['bomb_grn'], 1.0)

        # ── Other players ──
        for pid, p in gs.players.items():
            if pid == gs.local_pid or not p.alive: continue
            col = C['ct_blue'] if p.team=='CT' else C['t_gold']
            self._draw_player_sprite(frame, lp, p, col)

        # ── Weapon model ──
        self._draw_weapon(frame, lp)

        # ── HUD overlays ──
        self._draw_hud(frame, lp)

        # ── Flash effect ──
        if lp.flash_level > 0:
            overlay = np.ones((H, W, 3), dtype=np.uint8) * 255
            alpha = lp.flash_level
            cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0, frame)

        # ── Damage vignette ──
        if lp.hp < 30:
            self._draw_damage_vignette(frame, lp.hp)

        # ── Crosshair ──
        if gs.show_buy:
            self._draw_buy_menu(frame, lp)
        elif gs.show_scoreboard:
            self._draw_scoreboard(frame)
        else:
            self._draw_crosshair(frame, lp)

        return frame

    def _draw_player_sprite(self, frame, lp, p, color):
        dx = p.x - lp.x; dy = p.y - lp.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 0.1 or dist > MAX_DEPTH: return

        # Camera transform
        inv_det = 1.0 / (math.cos(lp.angle)*(-math.sin(lp.angle)) -
                         math.sin(lp.angle)*(-math.cos(lp.angle)) + 1e-9)
        tx = math.cos(-lp.angle)*dx - math.sin(-lp.angle)*dy
        tz = math.sin(-lp.angle)*dx + math.cos(-lp.angle)*dy
        if tz <= 0.01: return

        sp_x = int((W/2) * (1 + tx/tz))
        sp_h = min(H, abs(int(H / tz)))
        sp_w = sp_h // 2
        top = HALF_H - sp_h//2; bot = top + sp_h

        # Occlusion check
        col_start = sp_x - sp_w//2
        col_end = sp_x + sp_w//2
        for col in range(max(0, col_start), min(W, col_end)):
            if col < len(self.zbuf) and self.zbuf[col] < tz: continue
            t_frac = (top, bot)
            dt = max(0, top); db = min(H-1, bot)
            if db > dt:
                frame[dt:db, col] = color

        # Name label
        if abs(sp_x - W//2) < W//2:
            name_y = max(10, top - 15)
            cv2.putText(frame, p.name[:8], (sp_x - 20, name_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.35, C['white'], 1)
            # HP bar above
            bar_w = 40
            bx = sp_x - bar_w//2; by = name_y - 8
            if 0 < bx < W-bar_w and 0 < by < H:
                cv2.rectangle(frame, (bx,by), (bx+bar_w,by+5), (50,50,50), -1)
                hp_w = int(bar_w * p.hp/100)
                hp_col = C['green'] if p.hp>50 else C['yellow'] if p.hp>25 else C['red']
                cv2.rectangle(frame, (bx,by), (bx+hp_w,by+5), hp_col, -1)

    def _draw_sprite(self, frame, lp, sx, sy, size, color, alpha):
        dx = sx - lp.x; dy = sy - lp.y
        dist = math.sqrt(dx*dx+dy*dy)
        if dist < 0.1 or dist > MAX_DEPTH: return
        tx = math.cos(-lp.angle)*dx - math.sin(-lp.angle)*dy
        tz = math.sin(-lp.angle)*dx + math.cos(-lp.angle)*dy
        if tz <= 0.01: return
        sp_x = int((W/2)*(1+tx/tz))
        sp_h = min(H//2, abs(int(H/tz * size)))
        x1 = max(0, sp_x-sp_h//2); x2 = min(W-1, sp_x+sp_h//2)
        y1 = max(0, HALF_H-sp_h//2); y2 = min(H-1, HALF_H+sp_h//2)
        if x2>x1 and y2>y1:
            overlay = frame[y1:y2, x1:x2].copy()
            overlay[:] = color
            cv2.addWeighted(overlay, alpha, frame[y1:y2,x1:x2], 1-alpha, 0, frame[y1:y2,x1:x2])

    def _draw_weapon(self, frame, lp):
        wname = lp.current_weapon
        w = lp.weapon

        # Recoil offset
        recoil_y = int(lp.recoil * 80)
        sway = int(math.sin(time.time()*2) * 2)

        # Draw weapon silhouette bottom-right
        gun_x = W - 300 + sway
        gun_y = H - 120 + recoil_y

        # Is reloading?
        reloading = lp.reload_time > time.time()

        # Weapon shapes
        if wname == 'knife':
            pts = np.array([[gun_x+60,gun_y+40],[gun_x+80,gun_y-20],
                            [gun_x+90,gun_y-25],[gun_x+85,gun_y+10]], np.int32)
            cv2.fillPoly(frame, [pts], (100,100,160))
            cv2.putText(frame, 'KNIFE', (gun_x+50, gun_y+55),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, C['gray'], 1)
        elif wname == 'awp':
            # Long rifle
            pts = np.array([[gun_x,gun_y+30],[gun_x+180,gun_y+10],
                            [gun_x+180,gun_y+20],[gun_x,gun_y+40]], np.int32)
            cv2.fillPoly(frame, [pts], (60,60,80))
            cv2.rectangle(frame, (gun_x+50,gun_y),(gun_x+130,gun_y+10),(80,80,100),-1)
            cv2.putText(frame, 'AWP', (gun_x+70,gun_y+55),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,200,255), 1)
        elif wname in ('ak47','sg553','m4a1','mp5'):
            pts = np.array([[gun_x,gun_y+30],[gun_x+150,gun_y+10],
                            [gun_x+150,gun_y+22],[gun_x,gun_y+42]], np.int32)
            col = (60,80,60) if wname in ('ak47','sg553') else (60,60,80)
            cv2.fillPoly(frame, [pts], col)
            cv2.rectangle(frame, (gun_x+20,gun_y+15),(gun_x+60,gun_y+50),(50,50,50),-1)
            cv2.putText(frame, wname.upper(), (gun_x+40,gun_y+60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, C['gray'], 1)
        else:
            # Pistol
            pts = np.array([[gun_x+20,gun_y+20],[gun_x+80,gun_y+5],
                            [gun_x+80,gun_y+15],[gun_x+30,gun_y+50],[gun_x+20,gun_y+50]], np.int32)
            cv2.fillPoly(frame, [pts], (70,70,90))
            cv2.putText(frame, wname.upper(), (gun_x+20,gun_y+65),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.38, C['gray'], 1)

        # Muzzle flash
        mag = w.get('mag',0)
        if lp.recoil > 0.5 and mag > 0:
            cx = gun_x + (170 if wname=='awp' else 145 if wname in ('ak47','m4a1','mp5','sg553') else 80)
            cy = gun_y + 15
            cv2.circle(frame, (cx, cy), random.randint(6,14), (0,200,255), -1)
            cv2.circle(frame, (cx, cy), random.randint(2,6), (100,255,255), -1)

        # Reload animation text
        if reloading:
            prog = 1 - (lp.reload_time - time.time()) / w.get('reload_time_set', 2.0)
            cv2.putText(frame, f'RELOADING {int(prog*100)}%',
                       (W//2-70, H-60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, C['yellow'], 2)

    def _draw_crosshair(self, frame, lp):
        cx, cy = W//2, H//2
        spread = int(lp.recoil * 20) + (5 if lp.crouching else 8)
        col = C['crosshair']
        # Classic CS crosshair
        cv2.line(frame, (cx-spread-4,cy),(cx-2,cy), col, 1)
        cv2.line(frame, (cx+2,cy),(cx+spread+4,cy), col, 1)
        cv2.line(frame, (cx,cy-spread-4),(cx,cy-2), col, 1)
        cv2.line(frame, (cx,cy+2),(cx,cy+spread+4), col, 1)
        # Center dot
        cv2.circle(frame, (cx,cy), 1, col, -1)

        # Hit markers
        now = time.time()
        for hx, hy, born, is_kill in self.gs.hit_markers[:]:
            age = now - born
            if age > 0.3:
                self.gs.hit_markers.remove((hx,hy,born,is_kill))
                continue
            c = C['red'] if is_kill else C['white']
            s = 8
            cv2.line(frame,(hx-s,hy-s),(hx+s,hy+s),c,2)
            cv2.line(frame,(hx+s,hy-s),(hx-s,hy+s),c,2)

    def _draw_hud(self, frame, lp):
        gs = self.gs
        # ── Bottom bar background ──
        cv2.rectangle(frame, (0,H-70),(W,H),(10,10,10),-1)
        cv2.line(frame,(0,H-70),(W,H-70),(40,40,40),1)

        # HP
        hp_col = C['green'] if lp.hp>50 else C['yellow'] if lp.hp>25 else C['red']
        cv2.putText(frame, f'HP {lp.hp}', (20, H-42),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, hp_col, 2)
        # HP bar
        bar_w = 120
        cv2.rectangle(frame,(20,H-35),(20+bar_w,H-25),(40,40,40),-1)
        cv2.rectangle(frame,(20,H-35),(20+int(bar_w*lp.hp/100),H-25),hp_col,-1)

        # Armor
        arm_col = C['ct_blue'] if lp.helmet else C['gray']
        cv2.putText(frame, f'ARM {lp.armor}', (160, H-42),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.55, arm_col, 1)
        if lp.helmet:
            cv2.putText(frame, '[H]', (245,H-42), cv2.FONT_HERSHEY_SIMPLEX, 0.4, arm_col, 1)

        # Ammo
        w = lp.weapon
        mag = w.get('mag',0)
        ammo = w.get('ammo',0)
        if lp.current_weapon != 'knife':
            reloading = lp.reload_time > time.time()
            ammo_str = 'RELOADING' if reloading else f'{mag} / {ammo}'
            cv2.putText(frame, ammo_str, (W-200, H-42),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.65, C['white'], 2)
            cv2.putText(frame, lp.weapon.get('name',''), (W-200, H-18),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, C['gray'], 1)

        # Money
        cv2.putText(frame, f'${lp.money}', (W//2-40, H-42),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, C['green'], 2)

        # ── Top HUD ──
        # Scores
        cv2.rectangle(frame,(W//2-120,0),(W//2+120,50),(10,10,10),-1)
        cv2.putText(frame, f'{gs.ct_score}', (W//2-100,38),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, C['ct_blue'], 2)
        cv2.putText(frame, ' : ', (W//2-20,38),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, C['white'], 2)
        cv2.putText(frame, f'{gs.t_score}', (W//2+40,38),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, C['t_gold'], 2)
        cv2.putText(frame, 'CT', (W//2-100,15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, C['ct_blue'], 1)
        cv2.putText(frame, 'T', (W//2+80,15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, C['t_gold'], 1)

        # Timer
        tl = gs.time_left()
        mins = int(tl)//60; secs = int(tl)%60
        t_col = C['red'] if tl < 10 else C['white']
        cv2.putText(frame, f'{mins:02d}:{secs:02d}', (W//2-30,15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.55, t_col, 2)

        # Round
        cv2.putText(frame, f'RD {gs.round_num}/{gs.max_rounds}', (W//2-30,48),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.3, C['gray'], 1)

        # Phase indicator
        phase_str = {'buy':'BUY PHASE','live':'LIVE','planted':'!! BOMB PLANTED !!',
                     'ended':'ROUND OVER','halftime':'HALFTIME'}.get(gs.round_phase,'')
        p_col = C['bomb_red'] if gs.round_phase=='planted' else \
                C['yellow'] if gs.round_phase=='buy' else C['white']
        cv2.putText(frame, phase_str, (W//2-80,65),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, p_col, 1)

        # ── Bomb timer bar ──
        if gs.bomb_planted and not gs.bomb_defused:
            tl_b = gs.time_left()
            prog = tl_b / gs.plant_time
            bx,by = W//2-150, 75
            cv2.rectangle(frame,(bx,by),(bx+300,by+12),(40,0,0),-1)
            cv2.rectangle(frame,(bx,by),(bx+int(300*prog),by+12),C['bomb_red'],-1)
            cv2.putText(frame,'BOMB',(bx-50,by+10),cv2.FONT_HERSHEY_SIMPLEX,0.45,C['bomb_red'],1)

        # ── Defuse indicator ──
        if lp.is_defusing:
            prog = (time.time()-lp.defuse_start)/gs.defuse_time
            cv2.rectangle(frame,(W//2-100,H//2+60),(W//2+100,H//2+80),(20,20,20),-1)
            cv2.rectangle(frame,(W//2-100,H//2+60),(W//2-100+int(200*prog),H//2+80),C['green'],-1)
            cv2.putText(frame,'DEFUSING...',(W//2-55,H//2+75),
                       cv2.FONT_HERSHEY_SIMPLEX,0.55,C['green'],2)

        # ── Plant indicator ──
        if lp.is_planting:
            prog = (time.time()-lp.plant_start)/3.2
            cv2.rectangle(frame,(W//2-100,H//2+60),(W//2+100,H//2+80),(20,20,20),-1)
            cv2.rectangle(frame,(W//2-100,H//2+60),(W//2-100+int(200*prog),H//2+80),C['bomb_red'],-1)
            cv2.putText(frame,'PLANTING C4...',(W//2-70,H//2+75),
                       cv2.FONT_HERSHEY_SIMPLEX,0.55,C['bomb_red'],2)

        # ── Buy hint ──
        if gs.round_phase == 'buy':
            cv2.putText(frame,'[B] BUY MENU',(10,H-85),
                       cv2.FONT_HERSHEY_SIMPLEX,0.45,C['yellow'],1)

        # ── E prompt ──
        if gs.bomb_planted and lp.team=='CT':
            dx=gs.bomb_x-lp.x; dy=gs.bomb_y-lp.y
            if math.sqrt(dx*dx+dy*dy)<1.5:
                cv2.putText(frame,'[E] DEFUSE',(W//2-45,H//2+40),
                           cv2.FONT_HERSHEY_SIMPLEX,0.65,C['green'],2)
        if lp.has_bomb and not gs.bomb_planted and lp.team=='T':
            near_a = gs.map.near_site(lp.x,lp.y,A_SITE[0],A_SITE[1])
            near_b = gs.map.near_site(lp.x,lp.y,B_SITE[0],B_SITE[1])
            if near_a or near_b:
                cv2.putText(frame,f'[E] PLANT C4 ({chr(65 if near_a else 66)}-SITE)',
                           (W//2-90,H//2+40),cv2.FONT_HERSHEY_SIMPLEX,0.65,C['bomb_red'],2)

        # ── Kill feed ──
        now = time.time()
        ky = 90
        for entry in gs.kill_feed[:6]:
            killer,victim,weapon,born = entry
            if now-born > 5: continue
            alpha = min(1.0,(5-(now-born))/1.0)
            kc = C['ct_blue'] if killer.startswith('CT') else C['t_gold']
            vc = C['ct_blue'] if victim.startswith('CT') else C['t_gold']
            s = f'{killer} [{weapon}] {victim}'
            cv2.putText(frame, s, (W-300, ky), cv2.FONT_HERSHEY_SIMPLEX, 0.38, C['white'], 1)
            ky += 18

        # ── Round announcement ──
        if gs.round_announce and now - gs.round_announce_time < 4:
            alpha = min(1.0, (4-(now-gs.round_announce_time))/1.0)
            txt = gs.round_announce
            ts = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.85, 2)[0]
            tx = (W-ts[0])//2; ty = H//2 - 80
            cv2.rectangle(frame,(tx-15,ty-30),(tx+ts[0]+15,ty+10),(0,0,0),-1)
            cv2.putText(frame, txt, (tx,ty), cv2.FONT_HERSHEY_SIMPLEX, 0.85, C['yellow'], 2)

        # ── Weapon list (bottom) ──
        wx = 320
        for i,(wn,wdata) in enumerate(lp.weapons.items()):
            col = C['yellow'] if wn==lp.current_weapon else C['gray']
            cv2.putText(frame, wdata.get('name',wn), (wx, H-50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)
            if wn==lp.current_weapon:
                ts=cv2.getTextSize(wdata.get('name',wn),cv2.FONT_HERSHEY_SIMPLEX,0.35,1)[0]
                cv2.line(frame,(wx,H-45),(wx+ts[0],H-45),col,1)
            wx += 100

        # ── Team players alive ──
        t_alive = sum(1 for p in gs.players.values() if p.team=='T' and p.alive)
        ct_alive = sum(1 for p in gs.players.values() if p.team=='CT' and p.alive)
        cv2.putText(frame, f'T: {t_alive}', (W-80,H-55),
                   cv2.FONT_HERSHEY_SIMPLEX,0.45,C['t_gold'],1)
        cv2.putText(frame, f'CT: {ct_alive}', (W-80,H-38),
                   cv2.FONT_HERSHEY_SIMPLEX,0.45,C['ct_blue'],1)

        # ── Controls reminder ──
        cv2.putText(frame,'WASD:move  Mouse:look  LMB:fire  R:reload  G:nade  E:interact  B:buy  Tab:score',
                   (10,H-10),cv2.FONT_HERSHEY_SIMPLEX,0.28,C['gray'],1)

    def _draw_buy_menu(self, frame, lp):
        overlay = frame.copy()
        cv2.rectangle(overlay,(80,60),(W-80,H-80),(5,5,20),-1)
        cv2.addWeighted(overlay,0.88,frame,0.12,0,frame)
        cv2.rectangle(frame,(80,60),(W-80,H-80),(60,60,120),2)

        cv2.putText(frame,'BUY MENU',(W//2-70,95),
                   cv2.FONT_HERSHEY_SIMPLEX,1.0,C['yellow'],2)
        cv2.putText(frame,f'Money: ${lp.money}',(W//2-60,125),
                   cv2.FONT_HERSHEY_SIMPLEX,0.65,C['green'],1)

        avail = T_WEAPONS if lp.team=='T' else CT_WEAPONS
        cols = 3; item_w=(W-200)//cols; item_h=55; start_y=150

        cv2.putText(frame,'[B] close  [1-9] select  Click to buy',(90,H-90),
                   cv2.FONT_HERSHEY_SIMPLEX,0.4,C['gray'],1)

        for i,wname in enumerate(avail):
            if wname not in WEAPONS: continue
            w=WEAPONS[wname]
            col_i=i%cols; row_i=i//cols
            x=100+col_i*item_w; y=start_y+row_i*item_h
            already = wname in lp.weapons
            can_buy = lp.money >= w['price'] and not already
            bg = (20,40,20) if can_buy else (30,10,10) if not can_buy else (10,10,40)
            cv2.rectangle(frame,(x,y),(x+item_w-10,y+item_h-5),bg,-1)
            border_col = C['green'] if can_buy else C['gray']
            cv2.rectangle(frame,(x,y),(x+item_w-10,y+item_h-5),border_col,1)

            name_col = C['white'] if can_buy else C['gray']
            cv2.putText(frame,f'[{i+1}] {w["name"]}',(x+5,y+20),
                       cv2.FONT_HERSHEY_SIMPLEX,0.42,name_col,1)
            price_col = C['green'] if can_buy else C['red']
            cv2.putText(frame,f'${w["price"]}',(x+5,y+40),
                       cv2.FONT_HERSHEY_SIMPLEX,0.4,price_col,1)
            if already:
                cv2.putText(frame,'OWNED',(x+item_w-70,y+40),
                           cv2.FONT_HERSHEY_SIMPLEX,0.35,C['yellow'],1)

            # Damage / stats mini
            dmg_str=f'DMG:{w["damage"]}' if w['damage']>0 else ''
            cv2.putText(frame,dmg_str,(x+item_w-80,y+20),
                       cv2.FONT_HERSHEY_SIMPLEX,0.32,C['gray'],1)

        # Armor
        y=start_y + (len(avail)//cols+1)*item_h
        for vi,(vname,vdata) in enumerate([('vest',WEAPONS['vest']),
                                            ('vesthelm',WEAPONS['vesthelm'])]):
            x=100+vi*item_w; already=lp.armor>0
            can=lp.money>=vdata['price']
            bg=(20,30,20) if can else (30,15,15)
            cv2.rectangle(frame,(x,y),(x+item_w-10,y+item_h-5),bg,-1)
            cv2.rectangle(frame,(x,y),(x+item_w-10,y+item_h-5),
                         C['green'] if can else C['gray'],1)
            cv2.putText(frame,vdata['name'],(x+5,y+20),
                       cv2.FONT_HERSHEY_SIMPLEX,0.42,C['white'] if can else C['gray'],1)
            cv2.putText(frame,f'${vdata["price"]}',(x+5,y+40),
                       cv2.FONT_HERSHEY_SIMPLEX,0.4,C['green'] if can else C['red'],1)

    def _draw_scoreboard(self, frame):
        overlay = frame.copy()
        cv2.rectangle(overlay,(100,50),(W-100,H-50),(5,5,15),-1)
        cv2.addWeighted(overlay,0.85,frame,0.15,0,frame)
        cv2.rectangle(frame,(100,50),(W-100,H-50),(60,60,100),2)

        cv2.putText(frame,'SCOREBOARD',(W//2-80,90),
                   cv2.FONT_HERSHEY_SIMPLEX,0.9,C['white'],2)
        cv2.putText(frame,f'CT  {self.gs.ct_score} : {self.gs.t_score}  T',
                   (W//2-80,120),cv2.FONT_HERSHEY_SIMPLEX,0.75,C['white'],2)

        # Headers
        hx=120; hy=150
        for hdr,hpos in [('Name',hx),('K',hx+180),('D',hx+220),('Score',hx+265),('$',hx+320)]:
            cv2.putText(frame,hdr,(hpos,hy),cv2.FONT_HERSHEY_SIMPLEX,0.45,C['gray'],1)

        # CT side
        cy=175
        cv2.putText(frame,'── COUNTER-TERRORISTS ──',(hx,cy),
                   cv2.FONT_HERSHEY_SIMPLEX,0.5,C['ct_blue'],1); cy+=22
        for p in sorted(self.gs.players.values(),key=lambda x:-x.score):
            if p.team!='CT': continue
            col=C['yellow'] if p.pid==self.gs.local_pid else C['white']
            alive_marker='●' if p.alive else '○'
            cv2.putText(frame,f'{alive_marker} {p.name[:12]}',(hx,cy),
                       cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,str(p.kills),(hx+180,cy),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,str(p.deaths),(hx+220,cy),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,str(p.score),(hx+265,cy),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,f'${p.money}',(hx+320,cy),cv2.FONT_HERSHEY_SIMPLEX,0.4,C['green'],1)
            cy+=22

        cy+=10
        cv2.putText(frame,'── TERRORISTS ──',(hx,cy),
                   cv2.FONT_HERSHEY_SIMPLEX,0.5,C['t_gold'],1); cy+=22
        for p in sorted(self.gs.players.values(),key=lambda x:-x.score):
            if p.team!='T': continue
            col=C['yellow'] if p.pid==self.gs.local_pid else C['white']
            alive_marker='●' if p.alive else '○'
            cv2.putText(frame,f'{alive_marker} {p.name[:12]}',(hx,cy),
                       cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,str(p.kills),(hx+180,cy),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,str(p.deaths),(hx+220,cy),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,str(p.score),(hx+265,cy),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1)
            cv2.putText(frame,f'${p.money}',(hx+320,cy),cv2.FONT_HERSHEY_SIMPLEX,0.4,C['green'],1)
            cy+=22

    def _draw_dead_screen(self, lp):
        frame = self.frame
        frame[:] = (10,5,5)
        cv2.putText(frame,'YOU DIED',(W//2-120,H//2-40),
                   cv2.FONT_HERSHEY_SIMPLEX,2.0,C['red'],3)
        cv2.putText(frame,'Waiting for next round...',(W//2-140,H//2+20),
                   cv2.FONT_HERSHEY_SIMPLEX,0.65,C['gray'],1)
        gs=self.gs
        t_alive=sum(1 for p in gs.players.values() if p.team=='T' and p.alive)
        ct_alive=sum(1 for p in gs.players.values() if p.team=='CT' and p.alive)
        cv2.putText(frame,f'T alive: {t_alive}  CT alive: {ct_alive}',
                   (W//2-120,H//2+60),cv2.FONT_HERSHEY_SIMPLEX,0.55,C['white'],1)
        if gs.round_winner:
            w_str=f'{"Terrorists" if gs.round_winner=="T" else "Counter-Terrorists"} won the round!'
            cv2.putText(frame,w_str,(W//2-180,H//2+100),
                       cv2.FONT_HERSHEY_SIMPLEX,0.65,C['yellow'],2)

    def _draw_damage_vignette(self, frame, hp):
        alpha = (30-hp)/30 * 0.6
        vig = np.zeros_like(frame)
        for y in range(H):
            for x in range(W):
                dx=abs(x-W//2)/(W//2); dy=abs(y-H//2)/(H//2)
                d=math.sqrt(dx*dx+dy*dy)
                if d>0.6:
                    vig[y,x]=[0,0,int((d-0.6)/0.4*180)]
        cv2.addWeighted(vig,alpha,frame,1,0,frame)

# ─────────────────────────────────────────────
#  NETWORK — SERVER
# ─────────────────────────────────────────────
class GameServer:
    def __init__(self, gs, port=PORT):
        self.gs = gs
        self.clients = {}  # addr -> (conn, pid)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', port))
        self.sock.listen(MAX_PLAYERS)
        self.running = True
        self.next_pid = 1
        self.lock = threading.Lock()
        print(f"[SERVER] Listening on 0.0.0.0:{port}")
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.sock.accept()
                pid = self.next_pid; self.next_pid += 1
                self.clients[addr] = (conn, pid)
                print(f"[SERVER] Client {addr} -> PID {pid}")
                threading.Thread(target=self._handle_client,
                                args=(conn, addr, pid), daemon=True).start()
            except: break

    def _handle_client(self, conn, addr, pid):
        buf = b''
        while self.running:
            try:
                data = conn.recv(4096)
                if not data: break
                buf += data
                while len(buf) >= 4:
                    msg_len = struct.unpack('!I', buf[:4])[0]
                    if len(buf) < 4+msg_len: break
                    msg = json.loads(buf[4:4+msg_len].decode())
                    buf = buf[4+msg_len:]
                    self._process(msg, pid, addr)
            except: break
        self._disconnect(addr, pid)

    def _process(self, msg, pid, addr):
        gs = self.gs
        t = msg.get('type')
        with self.lock:
            if t == 'join':
                team = msg.get('team','CT')
                name = msg.get('name','Player')[:16]
                gs.add_player(pid, name, team)
                # Send full state back
                self._send_to(addr, {'type':'welcome','pid':pid})
                self._broadcast_state()

            elif t == 'update':
                p = gs.players.get(pid)
                if p:
                    p.x = msg.get('x', p.x)
                    p.y = msg.get('y', p.y)
                    p.angle = msg.get('angle', p.angle)
                    self._broadcast({'type':'player_pos','pid':pid,
                                    'x':p.x,'y':p.y,'angle':p.angle,
                                    'alive':p.alive,'hp':p.hp})

            elif t == 'shoot':
                self._handle_shoot(pid, msg)

            elif t == 'buy':
                self._handle_buy(pid, msg)

            elif t == 'plant':
                self._handle_plant(pid, msg)

            elif t == 'defuse':
                self._handle_defuse(pid)

            elif t == 'chat':
                self._broadcast({'type':'chat','name':msg.get('name',''),
                                'text':msg.get('text','')[:80]})

    def _handle_shoot(self, pid, msg):
        gs=self.gs; shooter=gs.players.get(pid)
        if not shooter or not shooter.alive: return
        # Find hit
        target_pid=msg.get('target_pid')
        if target_pid is not None:
            target=gs.players.get(target_pid)
            if target and target.alive and target.team!=shooter.team:
                hit_head=msg.get('head',False)
                wname=shooter.current_weapon
                dmg_base=WEAPONS.get(wname,{}).get('damage',10)
                dmg=target.take_damage(dmg_base, hit_head)
                is_kill=not target.alive
                self._broadcast({'type':'hit','target':target_pid,
                                'dmg':dmg,'kill':is_kill,'killer':pid,
                                'weapon':wname})
                if is_kill:
                    shooter.kills+=1; target.deaths+=1
                    shooter.money=min(16000,shooter.money+300)
                    gs.kill_feed.insert(0,(shooter.name,target.name,wname,time.time()))
                    if len(gs.kill_feed)>8: gs.kill_feed.pop()
                gs.check_round_end()

    def _handle_buy(self, pid, msg):
        gs=self.gs; p=gs.players.get(pid)
        if not p or gs.round_phase!='buy': return
        item=msg.get('item')
        if not item: return
        w=WEAPONS.get(item)
        if not w: return
        price=w['price']
        if p.money<price: return
        if item=='vest':
            p.armor=100; p.money-=price
        elif item=='vesthelm':
            p.armor=100; p.helmet=True; p.money-=price
        elif item not in p.weapons:
            p.weapons[item]=dict(w); p.money-=price
        self._broadcast_state()

    def _handle_plant(self, pid, msg):
        gs=self.gs; p=gs.players.get(pid)
        if not p or not p.alive or not p.has_bomb: return
        gs.bomb_planted=True
        gs.bomb_x=p.x; gs.bomb_y=p.y
        gs.bomb_plant_time=time.time()
        gs.round_phase='planted'
        p.has_bomb=False
        gs.announce('BOMB PLANTED — CT DEFUSE IT!')
        self._broadcast({'type':'bomb_planted','x':p.x,'y':p.y})

    def _handle_defuse(self, pid):
        gs=self.gs; p=gs.players.get(pid)
        if not p or not p.alive: return
        if not gs.bomb_planted: return
        gs.bomb_defused=True
        gs.announce('BOMB DEFUSED!')
        gs.check_round_end()
        self._broadcast({'type':'bomb_defused','defuser':pid})

    def _disconnect(self, addr, pid):
        with self.lock:
            self.clients.pop(addr, None)
            self.gs.players.pop(pid, None)
        print(f"[SERVER] PID {pid} disconnected")

    def _send_to(self, addr, msg):
        conn, pid = self.clients.get(addr, (None,None))
        if conn: self._send_raw(conn, msg)

    def _send_raw(self, conn, msg):
        try:
            data=json.dumps(msg).encode()
            conn.sendall(struct.pack('!I',len(data))+data)
        except: pass

    def _broadcast(self, msg):
        for addr,(conn,pid) in list(self.clients.items()):
            self._send_raw(conn, msg)

    def _broadcast_state(self):
        gs=self.gs
        state={
            'type':'game_state',
            'players':{str(pid):{'name':p.name,'team':p.team,'x':p.x,'y':p.y,
                                  'angle':p.angle,'hp':p.hp,'armor':p.armor,
                                  'helmet':p.helmet,'alive':p.alive,'kills':p.kills,
                                  'deaths':p.deaths,'score':p.score,'money':p.money,
                                  'weapons':list(p.weapons.keys()),'current':p.current_weapon}
                       for pid,p in gs.players.items()},
            'round_phase':gs.round_phase,'round_num':gs.round_num,
            't_score':gs.t_score,'ct_score':gs.ct_score,
            'bomb_planted':gs.bomb_planted,'bomb_x':gs.bomb_x,'bomb_y':gs.bomb_y,
        }
        self._broadcast(state)

    def tick(self):
        """Server-side game logic tick"""
        gs=self.gs
        # Phase transitions
        if gs.round_phase=='buy' and gs.time_left()<=0:
            gs.round_phase='live'
            gs.round_start=time.time()
            with self.lock:
                self._broadcast({'type':'phase_change','phase':'live'})

        elif gs.round_phase=='planted':
            if gs.time_left()<=0:
                gs.bomb_exploded=True
                gs.announce('BOMB EXPLODED!')
                gs.check_round_end()
                with self.lock:
                    self._broadcast({'type':'bomb_exploded'})

        elif gs.round_phase=='ended':
            if time.time()-gs.round_announce_time>5:
                if gs.round_num>=gs.max_rounds:
                    self._broadcast({'type':'game_over',
                                    'ct':gs.ct_score,'t':gs.t_score})
                else:
                    gs.new_round()
                    with self.lock:
                        self._broadcast_state()

        # Smoke expiry
        gs.smokes=[s for s in gs.smokes if time.time()-s[3]<s[2]]

# ─────────────────────────────────────────────
#  NETWORK — CLIENT
# ─────────────────────────────────────────────
class GameClient:
    def __init__(self, gs, host, port=PORT):
        self.gs = gs
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.running = True
        self.buf = b''
        self.lock = threading.Lock()
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _recv_loop(self):
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data: break
                self.buf += data
                while len(self.buf) >= 4:
                    msg_len = struct.unpack('!I', self.buf[:4])[0]
                    if len(self.buf) < 4+msg_len: break
                    msg = json.loads(self.buf[4:4+msg_len].decode())
                    self.buf = self.buf[4+msg_len:]
                    self._process(msg)
            except Exception as e:
                print(f"[CLIENT] recv error: {e}")
                break

    def _process(self, msg):
        gs=self.gs; t=msg.get('type')
        with self.lock:
            if t=='welcome':
                gs.local_pid=msg['pid']
                print(f"[CLIENT] Got PID {gs.local_pid}")

            elif t=='game_state':
                for spid,pdata in msg.get('players',{}).items():
                    pid=int(spid)
                    if pid not in gs.players:
                        spawns=T_SPAWNS if pdata['team']=='T' else CT_SPAWNS
                        gs.players[pid]=Player(pid,pdata['name'],pdata['team'],spawns[0])
                    p=gs.players[pid]
                    p.x=pdata['x']; p.y=pdata['y']; p.angle=pdata['angle']
                    p.hp=pdata['hp']; p.armor=pdata['armor']
                    p.helmet=pdata['helmet']; p.alive=pdata['alive']
                    p.kills=pdata['kills']; p.deaths=pdata['deaths']
                    p.score=pdata['score']; p.money=pdata['money']
                    p.current_weapon=pdata['current']
                gs.round_phase=msg.get('round_phase',gs.round_phase)
                gs.round_num=msg.get('round_num',gs.round_num)
                gs.t_score=msg.get('t_score',gs.t_score)
                gs.ct_score=msg.get('ct_score',gs.ct_score)
                gs.bomb_planted=msg.get('bomb_planted',False)
                gs.bomb_x=msg.get('bomb_x',0); gs.bomb_y=msg.get('bomb_y',0)

            elif t=='player_pos':
                pid=msg['pid']
                if pid in gs.players:
                    p=gs.players[pid]
                    p.x=msg['x']; p.y=msg['y']; p.angle=msg['angle']
                    p.alive=msg['alive']; p.hp=msg['hp']

            elif t=='hit':
                target=gs.players.get(msg.get('target'))
                if target:
                    target.hp=max(0,target.hp-msg.get('dmg',0))
                    if msg.get('kill'):
                        target.alive=False
                        killer=gs.players.get(msg.get('killer'))
                        kname=killer.name if killer else '?'
                        gs.kill_feed.insert(0,(kname,target.name,
                                              msg.get('weapon','?'),time.time()))
                if msg.get('target')==gs.local_pid:
                    gs.damage_indicators.append((random.uniform(0,math.pi*2),
                                                msg.get('dmg',0),time.time(),1.5))
                gs.hit_markers.append((W//2,H//2,time.time(),msg.get('kill',False)))

            elif t=='bomb_planted':
                gs.bomb_planted=True; gs.bomb_x=msg['x']; gs.bomb_y=msg['y']
                gs.round_phase='planted'; gs.bomb_plant_time=time.time()
                gs.announce('BOMB PLANTED!')

            elif t=='bomb_defused':
                gs.bomb_defused=True; gs.announce('BOMB DEFUSED!')

            elif t=='bomb_exploded':
                gs.bomb_exploded=True; gs.announce('BOMB EXPLODED!')

            elif t=='phase_change':
                gs.round_phase=msg['phase']
                if msg['phase']=='live':
                    gs.round_start=time.time()

            elif t=='chat':
                gs.chat_msgs.insert(0,(msg['name'],msg['text'],time.time()))
                if len(gs.chat_msgs)>6: gs.chat_msgs.pop()

    def send(self, msg):
        try:
            data=json.dumps(msg).encode()
            self.sock.sendall(struct.pack('!I',len(data))+data)
        except: pass

# ─────────────────────────────────────────────
#  INPUT HANDLER
# ─────────────────────────────────────────────
class InputHandler:
    def __init__(self):
        self.keys = defaultdict(bool)
        self.mouse_dx = 0
        self.mouse_left = False
        self.mouse_right = False
        self.last_mouse = None
        self.sensitivity = 0.002

    def process_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            if self.last_mouse:
                self.mouse_dx += (x - self.last_mouse[0]) * self.sensitivity
            self.last_mouse = (x, y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            self.mouse_left = True
        elif event == cv2.EVENT_LBUTTONUP:
            self.mouse_left = False
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.mouse_right = True
        elif event == cv2.EVENT_RBUTTONUP:
            self.mouse_right = False

# ─────────────────────────────────────────────
#  GAME LOOP (LOCAL / SINGLEPLAYER)
# ─────────────────────────────────────────────
class Game:
    def __init__(self, mode, host=None, name='Player', team='CT', is_server=False):
        self.gs = GameState()
        self.mode = mode  # 'solo','host','join'
        self.renderer = Renderer(self.gs)
        self.inp = InputHandler()
        self.server = None
        self.client = None
        self.running = True
        self.last_update_sent = 0
        self.name = name
        self.team = team

        if mode == 'solo' or mode == 'host':
            # Add local player (PID 0)
            self.gs.add_player(0, name, team)
            self.gs.local_pid = 0

            # Add some bots for solo
            if mode == 'solo':
                bot_teams={'CT':[],'T':[]}
                for bt,bn_list in [('CT',['Ghost','Hawk','Shield','Bolt']),
                                   ('T', ['Viper','Cobra','Shadow','Flame'])]:
                    for bi,bn in enumerate(bn_list):
                        pid=bi+1+(4 if bt=='T' else 0)
                        sp=CT_SPAWNS[bi] if bt=='CT' else T_SPAWNS[bi]
                        p=Player(pid,bn,bt,sp)
                        self.gs.players[pid]=p
                        if bt=='T' and bi==0: p.has_bomb=True

            if mode=='host':
                self.server = GameServer(self.gs)
                # Give local T player bomb
                lp=self.gs.local_player()
                if lp and lp.team=='T': lp.has_bomb=True

        elif mode == 'join':
            self.client = GameClient(self.gs, host)
            time.sleep(0.3)
            self.client.send({'type':'join','name':name,'team':team})

        self.bots = {} if mode=='solo' else None
        if mode=='solo':
            self._init_bots()

    def _init_bots(self):
        """Simple bot AI state"""
        for pid,p in self.gs.players.items():
            if pid==0: continue
            self.bots[pid]={
                'target_angle': p.angle,
                'move_timer': 0,
                'shoot_timer': 0,
                'waypoint': None,
                'state': 'roam',  # roam/chase/plant/defuse
                'last_shoot': 0,
            }

    def _update_bots(self):
        gs=self.gs; now=time.time()
        lp=gs.local_player()
        for pid,p in list(gs.players.items()):
            if pid==0 or not p.alive: continue
            bot=self.bots.get(pid,{})
            if not bot: continue

            # Find nearest enemy
            enemies=[e for e in gs.players.values()
                    if e.team!=p.team and e.alive]
            if not enemies:
                continue
            nearest=min(enemies,key=lambda e:math.hypot(e.x-p.x,e.y-p.y))
            dist=math.hypot(nearest.x-p.x,nearest.y-p.y)

            # Turn toward enemy
            target_a=math.atan2(nearest.y-p.y,nearest.x-p.x)
            diff=((target_a-p.angle+math.pi)%(math.pi*2))-math.pi
            p.angle+=diff*0.03*random.uniform(0.5,1.5)

            # Move toward enemy if far
            if dist>2.5:
                spd=0.03
                nx=p.x+math.cos(p.angle)*spd
                ny=p.y+math.sin(p.angle)*spd
                if not gs.map.is_wall(nx,p.y): p.x=nx
                if not gs.map.is_wall(p.x,ny): p.y=ny

            # Shoot
            if dist<12 and now-bot['last_shoot']>0.4+random.uniform(0,0.6):
                bot['last_shoot']=now
                # Bot hit chance depends on distance
                hit_chance=max(0.1, 0.7-dist*0.05)
                if random.random()<hit_chance:
                    wname=p.current_weapon
                    dmg=WEAPONS.get(wname,{}).get('damage',25)
                    is_head=random.random()<0.1
                    actual_dmg=nearest.take_damage(dmg,is_head)
                    if not nearest.alive:
                        p.kills+=1; nearest.deaths+=1
                        gs.kill_feed.insert(0,(p.name,nearest.name,wname,now))
                        if len(gs.kill_feed)>8: gs.kill_feed.pop()
                    gs.check_round_end()

            # T bomb logic
            if p.team=='T' and p.has_bomb and not gs.bomb_planted:
                near_a=gs.map.near_site(p.x,p.y,A_SITE[0],A_SITE[1],2.0)
                if near_a and now-bot.get('plant_start',0)>5:
                    gs.bomb_planted=True
                    gs.bomb_x=p.x; gs.bomb_y=p.y
                    gs.bomb_plant_time=now; gs.round_phase='planted'
                    p.has_bomb=False
                    gs.announce('BOMB PLANTED!')

    def run(self):
        cv2.namedWindow('Counter Siege', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Counter Siege', W, H)
        cv2.setMouseCallback('Counter Siege', self.inp.process_mouse)

        last_time = time.time()
        frame_count = 0
        fps_timer = time.time()
        fps_display = 0

        while self.running:
            now = time.time()
            dt = now - last_time
            last_time = now
            frame_count += 1
            if now-fps_timer>1.0:
                fps_display=frame_count; frame_count=0; fps_timer=now

            gs = self.gs
            lp = gs.local_player()

            # ── Server tick ──
            if self.server:
                self.server.tick()

            # ── Bot AI ──
            if self.bots is not None and gs.round_phase in ('buy','live','planted'):
                self._update_bots()

            # ── Input ──
            key = cv2.waitKey(1) & 0xFF
            self._handle_key(key, lp, now)

            # ── Player movement ──
            if lp and lp.alive and gs.round_phase in ('live','planted','buy'):
                self._move_player(lp, gs)

                # Send position update to server
                if self.client and now-self.last_update_sent>0.05:
                    self.last_update_sent=now
                    self.client.send({'type':'update','x':lp.x,'y':lp.y,'angle':lp.angle})

            # ── Shooting ──
            if lp and lp.alive and self.inp.mouse_left:
                self._shoot(lp, gs, now)

            # ── Phase logic (solo/host) ──
            if self.mode in ('solo','host'):
                self._solo_phase_logic(gs, lp, now)

            # ── Decay recoil ──
            if lp:
                lp.recoil = max(0, lp.recoil - dt*3)
                lp.flash_level = max(0, lp.flash_level - dt*0.5)

            # ── Render ──
            frame = self.renderer.render()

            # FPS counter
            cv2.putText(frame, f'FPS:{fps_display}', (10,20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, C['gray'], 1)

            # Mini-map
            self._draw_minimap(frame, lp)

            cv2.imshow('Counter Siege', frame)

            # Target frame rate
            elapsed = time.time()-now
            wait = max(1, int((1/FPS_TARGET - elapsed)*1000))
            cv2.waitKey(wait)

            # Exit
            if key == 27:  # ESC
                break

        cv2.destroyAllWindows()

    def _solo_phase_logic(self, gs, lp, now):
        if gs.round_phase=='buy' and gs.time_left()<=0:
            gs.round_phase='live'; gs.round_start=now
        elif gs.round_phase in('live','planted'):
            gs.check_round_end()
            if gs.round_phase=='planted':
                if gs.time_left()<=0:
                    gs.bomb_exploded=True
                    gs.announce('BOMB EXPLODED! T WIN')
                    gs.end_round('T','bomb_exploded')
        elif gs.round_phase=='ended':
            if now-gs.round_announce_time>5:
                if gs.round_num<gs.max_rounds:
                    gs.new_round()
                    # Re-init bots after new round
                    if self.bots is not None:
                        for pid,p in gs.players.items():
                            if pid!=0 and pid in self.bots:
                                pass  # bots already in gs.players after new_round

    def _handle_key(self, key, lp, now):
        gs = self.gs
        if key == ord('b') or key == ord('B'):
            gs.show_buy = not gs.show_buy
        elif key == 9:  # Tab
            gs.show_scoreboard = not gs.show_scoreboard
        elif key == ord('r') or key == ord('R'):
            if lp and lp.alive:
                w=lp.weapon
                if w.get('mag',0) is not None and w.get('mag',0) < WEAPONS.get(lp.current_weapon,{}).get('mag',0):
                    reload_dur=WEAPONS.get(lp.current_weapon,{}).get('reload',2.0)
                    lp.reload_time=now+reload_dur
                    w['reload_time_set']=reload_dur
        elif key == ord('e') or key == ord('E'):
            if lp and lp.alive:
                self._interact(lp, gs, now)
        elif key == ord('g') or key == ord('G'):
            if lp and lp.alive:
                # Quick-throw best grenade
                for gname in ['henade','flash','smoke']:
                    if gname in lp.weapons and lp.weapons[gname].get('mag',0)>0:
                        self._throw_grenade(lp, gs, gname, now)
                        break
        elif key == ord('c') or key == ord('C'):
            if lp: lp.crouching = not lp.crouching
        elif ord('1') <= key <= ord('5'):
            if lp:
                idx=key-ord('1')
                wlist=list(lp.weapons.keys())
                if idx<len(wlist): lp.switch_weapon(wlist[idx])
        # Buy menu item selection
        if gs.show_buy and lp:
            avail=T_WEAPONS if lp.team=='T' else CT_WEAPONS
            if ord('1') <= key <= ord('9'):
                idx=key-ord('1')
                if idx<len(avail):
                    item=avail[idx]
                    self._do_buy(lp, item, gs)

    def _do_buy(self, lp, item, gs):
        if gs.round_phase!='buy': return
        w=WEAPONS.get(item)
        if not w: return
        if lp.money<w['price']: return
        if item in ('vest','vesthelm'):
            if item=='vest': lp.armor=100
            else: lp.armor=100; lp.helmet=True
            lp.money-=w['price']
        elif item not in lp.weapons:
            lp.weapons[item]=dict(w); lp.money-=w['price']
            lp.switch_weapon(item)
        if self.client:
            self.client.send({'type':'buy','item':item})

    def _interact(self, lp, gs, now):
        # Plant
        if lp.has_bomb and not gs.bomb_planted and lp.team=='T':
            near_a=gs.map.near_site(lp.x,lp.y,A_SITE[0],A_SITE[1])
            near_b=gs.map.near_site(lp.x,lp.y,B_SITE[0],B_SITE[1])
            if near_a or near_b:
                if not lp.is_planting:
                    lp.is_planting=True; lp.plant_start=now
                elif now-lp.plant_start>=3.2:
                    lp.is_planting=False
                    gs.bomb_planted=True; gs.bomb_x=lp.x; gs.bomb_y=lp.y
                    gs.bomb_plant_time=now; gs.round_phase='planted'
                    lp.has_bomb=False
                    gs.announce('BOMB PLANTED!')
                    if self.client: self.client.send({'type':'plant'})
                return
            else:
                lp.is_planting=False
        else:
            lp.is_planting=False

        # Defuse
        if gs.bomb_planted and not gs.bomb_defused and lp.team=='CT':
            dx=gs.bomb_x-lp.x; dy=gs.bomb_y-lp.y
            if math.sqrt(dx*dx+dy*dy)<1.5:
                if not lp.is_defusing:
                    lp.is_defusing=True; lp.defuse_start=now
                elif now-lp.defuse_start>=gs.defuse_time:
                    lp.is_defusing=False
                    gs.bomb_defused=True
                    gs.announce('BOMB DEFUSED!')
                    gs.check_round_end()
                    if self.client: self.client.send({'type':'defuse'})
                return
            else:
                lp.is_defusing=False
        else:
            lp.is_defusing=False

    def _move_player(self, lp, gs):
        # Mouse look
        lp.angle += self.inp.mouse_dx
        self.inp.mouse_dx = 0

        spd = 0.025 if lp.crouching else 0.05
        dx = dy = 0

        # WASD via key states
        if self.inp.keys.get(ord('w'),False) or self.inp.keys.get(ord('W'),False):
            dx += math.cos(lp.angle)*spd; dy += math.sin(lp.angle)*spd
        if self.inp.keys.get(ord('s'),False) or self.inp.keys.get(ord('S'),False):
            dx -= math.cos(lp.angle)*spd; dy -= math.sin(lp.angle)*spd
        if self.inp.keys.get(ord('a'),False) or self.inp.keys.get(ord('A'),False):
            dx += math.cos(lp.angle-math.pi/2)*spd
            dy += math.sin(lp.angle-math.pi/2)*spd
        if self.inp.keys.get(ord('d'),False) or self.inp.keys.get(ord('D'),False):
            dx += math.cos(lp.angle+math.pi/2)*spd
            dy += math.sin(lp.angle+math.pi/2)*spd

        # Collision
        nx, ny = lp.x+dx, lp.y+dy
        margin = 0.25
        if not gs.map.is_wall(nx+margin*math.copysign(1,dx), lp.y): lp.x=nx
        if not gs.map.is_wall(lp.x, ny+margin*math.copysign(1,dy)): lp.y=ny

        # Update key states from OpenCV (polling approach)
        for k in [ord('w'),ord('s'),ord('a'),ord('d'),
                  ord('W'),ord('S'),ord('A'),ord('D')]:
            self.inp.keys[k]=False

        # We'll rely on the key check trick: set from waitKey
        # Actually let's use a different polling: check known key
        # OpenCV doesn't support key hold well, so we'll use getWindowProperty
        # Instead track via keydown/up events via waitKey
        pass

    def _shoot(self, lp, gs, now):
        if not lp.alive: return
        if gs.round_phase not in ('live','planted'): return
        wname=lp.current_weapon
        w=lp.weapon
        if lp.reload_time > now: return

        # Auto vs semi
        if not w.get('auto',False):
            if hasattr(self,'_last_shot_frame') and self._last_shot_frame==now:
                return

        # ROF check
        if now - lp.last_shot < w.get('rof',0.1): return
        lp.last_shot = now

        # Knife melee
        if wname=='knife':
            for pid,p in gs.players.items():
                if pid==gs.local_pid or not p.alive or p.team==lp.team: continue
                dist=math.hypot(p.x-lp.x,p.y-lp.y)
                if dist<1.5:
                    dmg=p.take_damage(WEAPONS['knife']['damage'])
                    gs.hit_markers.append((W//2,H//2,now,not p.alive))
                    if not p.alive:
                        lp.kills+=1; p.deaths+=1
                        gs.kill_feed.insert(0,(lp.name,p.name,'knife',now))
                    gs.check_round_end()
                    if self.client: self.client.send({'type':'shoot','target_pid':pid,'head':False})
            lp.recoil=0.3
            return

        # Check mag
        if w.get('mag',0)<=0:
            # Auto reload
            reload_dur=WEAPONS.get(wname,{}).get('reload',2.0)
            lp.reload_time=now+reload_dur
            w['reload_time_set']=reload_dur
            return

        # Consume ammo
        w['mag']-=1
        if w['mag']==0 and w.get('ammo',0)>0:
            reload_dur=WEAPONS.get(wname,{}).get('reload',2.0)
            lp.reload_time=now+reload_dur
            w['reload_time_set']=reload_dur
            refill=min(WEAPONS.get(wname,{}).get('mag',30), w.get('ammo',0))
            w['ammo']-=refill

        lp.recoil=min(1.0, lp.recoil+0.4)

        # Grenade
        if wname in ('henade','flash','smoke'):
            self._throw_grenade(lp, gs, wname, now)
            return

        # Hitscan raycast for enemies
        spread=WEAPONS.get(wname,{}).get('spread',0.05)
        shoot_angle=lp.angle+random.uniform(-spread,spread)
        if lp.crouching: spread*=0.5

        hit_pid=None; min_dist=999; is_head=False
        for pid,p in gs.players.items():
            if pid==gs.local_pid or not p.alive or p.team==lp.team: continue
            # Check if player is in shoot direction
            dx=p.x-lp.x; dy=p.y-lp.y
            dist=math.sqrt(dx*dx+dy*dy)
            if dist>WEAPONS.get(wname,{}).get('range',20): continue
            ang_to=math.atan2(dy,dx)
            ang_diff=abs(((ang_to-shoot_angle+math.pi)%(math.pi*2))-math.pi)
            # Angular tolerance decreases with distance
            tolerance=max(0.05, 0.3/max(dist,0.5))
            if ang_diff<tolerance and dist<min_dist:
                # Wall check
                blocked=False
                steps=int(dist*10)
                for step in range(1,steps):
                    cx=lp.x+dx/dist*step*0.1
                    cy=lp.y+dy/dist*step*0.1
                    if gs.map.is_wall(cx,cy): blocked=True; break
                if not blocked:
                    hit_pid=pid; min_dist=dist
                    is_head=(random.random()<0.15)

        if hit_pid is not None:
            target=gs.players[hit_pid]
            wdata=WEAPONS.get(wname,{})
            dmg=target.take_damage(wdata.get('damage',30), is_head)
            is_kill=not target.alive
            gs.hit_markers.append((W//2,H//2,now,is_kill))
            if is_kill:
                lp.kills+=1; target.deaths+=1
                lp.money=min(16000,lp.money+300)
                gs.kill_feed.insert(0,(lp.name,target.name,wname,now))
                if len(gs.kill_feed)>8: gs.kill_feed.pop()
            gs.check_round_end()
            if self.client:
                self.client.send({'type':'shoot','target_pid':hit_pid,
                                 'head':is_head,'weapon':wname})
        else:
            # Miss - send for server tracking
            if self.client:
                self.client.send({'type':'shoot','target_pid':None})

    def _throw_grenade(self, lp, gs, gname, now):
        w=lp.weapons.get(gname)
        if not w or w.get('mag',0)<=0: return
        w['mag']-=1
        # Simulate grenade at landing spot
        land_x=lp.x+math.cos(lp.angle)*4
        land_y=lp.y+math.sin(lp.angle)*4
        # Wall bounce (simple)
        if gs.map.is_wall(land_x, land_y):
            land_x=lp.x+math.cos(lp.angle)*1.5
            land_y=lp.y+math.sin(lp.angle)*1.5

        if gname=='henade':
            # Damage nearby
            for pid,p in gs.players.items():
                if not p.alive: continue
                dist=math.hypot(p.x-land_x, p.y-land_y)
                if dist<3.5:
                    dmg=int(WEAPONS['henade']['damage']*(1-dist/3.5))
                    actual=p.take_damage(dmg)
                    if not p.alive:
                        lp.kills+=1; p.deaths+=1
                        gs.kill_feed.insert(0,(lp.name,p.name,'HE',now))
            gs.effects.append(Effect('explosion',land_x,land_y,1.0))
            gs.announce('HE GRENADE!')

        elif gname=='flash':
            # Flash nearby players
            for pid,p in gs.players.items():
                if not p.alive: continue
                dist=math.hypot(p.x-land_x, p.y-land_y)
                if dist<5 and pid==gs.local_pid:
                    lp.flash_level=min(1.0, 1.5-dist/5)

        elif gname=='smoke':
            gs.smokes.append((land_x,land_y,15.0,now))
            gs.announce('SMOKE!')

    def _draw_minimap(self, frame, lp):
        if lp is None: return
        gs=self.gs
        mm_x,mm_y=W-160,H-160
        mm_w,mm_h=150,150
        scale=mm_w/gs.map.cols

        # Background
        cv2.rectangle(frame,(mm_x-5,mm_y-5),(mm_x+mm_w+5,mm_y+mm_h+5),(10,10,10),-1)
        cv2.rectangle(frame,(mm_x-5,mm_y-5),(mm_x+mm_w+5,mm_y+mm_h+5),(60,60,60),1)

        # Draw map
        for r,row in enumerate(gs.map.grid):
            for c,cell in enumerate(row):
                if cell>0:
                    colors={1:(80,80,100),2:(30,80,30),3:(80,30,30),4:(60,50,40)}
                    col=colors.get(cell,(80,80,80))
                    x1=mm_x+int(c*scale); y1=mm_y+int(r*scale)
                    x2=mm_x+int((c+1)*scale); y2=mm_y+int((r+1)*scale)
                    cv2.rectangle(frame,(x1,y1),(max(x1+1,x2),max(y1+1,y2)),col,-1)

        # Bomb site labels
        ax=mm_x+int(A_SITE[0]*scale); ay=mm_y+int(A_SITE[1]*scale)
        bx_=mm_x+int(B_SITE[0]*scale); by_=mm_y+int(B_SITE[1]*scale)
        cv2.putText(frame,'A',(ax,ay),cv2.FONT_HERSHEY_SIMPLEX,0.3,C['white'],1)
        cv2.putText(frame,'B',(bx_,by_),cv2.FONT_HERSHEY_SIMPLEX,0.3,C['white'],1)

        # Draw players
        for pid,p in gs.players.items():
            if not p.alive: continue
            px_=mm_x+int(p.x*scale); py_=mm_y+int(p.y*scale)
            col=C['ct_blue'] if p.team=='CT' else C['t_gold']
            size=4 if pid==gs.local_pid else 3
            cv2.circle(frame,(px_,py_),size,col,-1)
            if pid==gs.local_pid:
                # Direction
                ex=int(px_+math.cos(p.angle)*8)
                ey=int(py_+math.sin(p.angle)*8)
                cv2.line(frame,(px_,py_),(ex,ey),C['white'],1)

        # Bomb indicator
        if gs.bomb_planted:
            bpx=mm_x+int(gs.bomb_x*scale); bpy=mm_y+int(gs.bomb_y*scale)
            blink=int(time.time()*4)%2
            cv2.circle(frame,(bpx,bpy),5,C['bomb_red'] if blink else C['yellow'],2)

# ─────────────────────────────────────────────
#  KEY STATE TRACKING (patched movement)
# ─────────────────────────────────────────────
# OpenCV doesn't support keyup events, so we use a workaround
# with a separate polling approach by checking ASCII pressed keys
_held_keys = set()

def _patch_movement(game):
    """Override movement to use a different key tracking strategy."""
    orig_move = game._move_player
    def new_move(lp, gs):
        spd = 0.025 if lp.crouching else 0.05
        dx = dy = 0
        if ord('w') in _held_keys or ord('W') in _held_keys:
            dx += math.cos(lp.angle)*spd; dy += math.sin(lp.angle)*spd
        if ord('s') in _held_keys or ord('S') in _held_keys:
            dx -= math.cos(lp.angle)*spd; dy -= math.sin(lp.angle)*spd
        if ord('a') in _held_keys or ord('A') in _held_keys:
            dx += math.cos(lp.angle-math.pi/2)*spd
            dy += math.sin(lp.angle-math.pi/2)*spd
        if ord('d') in _held_keys or ord('D') in _held_keys:
            dx += math.cos(lp.angle+math.pi/2)*spd
            dy += math.sin(lp.angle+math.pi/2)*spd
        lp.angle += game.inp.mouse_dx
        game.inp.mouse_dx = 0
        margin = 0.25
        nx, ny = lp.x+dx, lp.y+dy
        if dx != 0 and not gs.map.is_wall(nx+margin*math.copysign(1,dx), lp.y): lp.x=nx
        if dy != 0 and not gs.map.is_wall(lp.x, ny+margin*math.copysign(1,dy)): lp.y=ny
    game._move_player = new_move

    # Patch handle_key to also update _held_keys
    orig_key = game._handle_key
    def new_key(key, lp, now):
        if key != 255 and key != -1:
            # Track held keys — reset each frame and set current
            _held_keys.discard(ord('w')); _held_keys.discard(ord('W'))
            _held_keys.discard(ord('s')); _held_keys.discard(ord('S'))
            _held_keys.discard(ord('a')); _held_keys.discard(ord('A'))
            _held_keys.discard(ord('d')); _held_keys.discard(ord('D'))
            if key in (ord('w'),ord('W'),ord('s'),ord('S'),
                      ord('a'),ord('A'),ord('d'),ord('D')):
                _held_keys.add(key)
        orig_key(key, lp, now)
    game._handle_key = new_key

# ─────────────────────────────────────────────
#  CONTINUOUS KEY HOLD (thread-based)
# ─────────────────────────────────────────────
import threading as _threading

class KeyboardState:
    """Track held keys via a background thread reading stdin raw"""
    def __init__(self):
        self.held = set()
        self._active = True

    def stop(self): self._active = False

# ─────────────────────────────────────────────
#  TEAM SELECTION & MAIN MENU
# ─────────────────────────────────────────────
def draw_menu(frame, sel, options, title, subtitle=''):
    frame[:] = (8, 5, 15)
    # Grid background
    for i in range(0, H, 40):
        cv2.line(frame, (0,i), (W,i), (15,10,25), 1)
    for i in range(0, W, 40):
        cv2.line(frame, (i,0), (i,H), (15,10,25), 1)

    # Title
    ts=cv2.getTextSize(title,cv2.FONT_HERSHEY_SIMPLEX,1.8,3)[0]
    cv2.putText(frame,title,((W-ts[0])//2,H//4),
               cv2.FONT_HERSHEY_SIMPLEX,1.8,(0,180,255),3)
    cv2.putText(frame,'TACTICAL FPS — LAN MULTIPLAYER',
               (W//2-180,H//4+40),cv2.FONT_HERSHEY_SIMPLEX,0.55,(100,80,160),1)
    if subtitle:
        cv2.putText(frame,subtitle,(W//2-200,H//4+65),
                   cv2.FONT_HERSHEY_SIMPLEX,0.45,(120,120,120),1)

    for i,(label,_) in enumerate(options):
        y=H//2+i*55
        is_sel=(i==sel)
        bg=(30,20,60) if is_sel else (10,8,20)
        bx=W//2-200
        cv2.rectangle(frame,(bx,y-30),(bx+400,y+10),bg,-1)
        border_col=(0,180,255) if is_sel else (40,40,80)
        cv2.rectangle(frame,(bx,y-30),(bx+400,y+10),border_col,2)
        txt_col=(0,220,255) if is_sel else (150,150,200)
        prefix='► ' if is_sel else '  '
        cv2.putText(frame,f'{prefix}[{i+1}] {label}',(bx+20,y),
                   cv2.FONT_HERSHEY_SIMPLEX,0.65,txt_col,2 if is_sel else 1)

    cv2.putText(frame,'W/S or ↑↓ to navigate  •  ENTER or number to select  •  ESC to quit',
               (W//2-290,H-30),cv2.FONT_HERSHEY_SIMPLEX,0.38,(80,80,100),1)

def main_menu():
    cv2.namedWindow('Counter Siege', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Counter Siege', W, H)
    frame = np.zeros((H,W,3),dtype=np.uint8)
    sel = 0
    options = [
        ('Solo (vs Bots)', 'solo'),
        ('Host LAN Game', 'host'),
        ('Join LAN Game', 'join'),
        ('Quit', 'quit'),
    ]
    while True:
        draw_menu(frame, sel, options, 'COUNTER SIEGE')
        cv2.imshow('Counter Siege', frame)
        key = cv2.waitKey(30) & 0xFF
        if key == 27: return None, None, None
        elif key == ord('w') or key == ord('W') or key==82: sel=(sel-1)%len(options)
        elif key == ord('s') or key == ord('S') or key==84: sel=(sel+1)%len(options)
        elif key == 13 or key == ord('\r'):
            mode = options[sel][1]
            if mode == 'quit': return None,None,None
            break
        elif ord('1')<=key<=ord('4'):
            mode=options[key-ord('1')][1]
            if mode=='quit': return None,None,None
            break

    # Name entry
    name = 'Player'
    frame2=frame.copy()
    entering=True
    input_str=''
    while entering:
        f=frame2.copy()
        f[:]=0
        cv2.putText(f,'ENTER YOUR NAME:',(W//2-150,H//2-20),
                   cv2.FONT_HERSHEY_SIMPLEX,0.9,(0,180,255),2)
        disp=input_str+'_'
        cv2.putText(f,disp,(W//2-150,H//2+40),
                   cv2.FONT_HERSHEY_SIMPLEX,1.0,(255,255,255),2)
        cv2.putText(f,'Press ENTER to confirm',(W//2-140,H//2+90),
                   cv2.FONT_HERSHEY_SIMPLEX,0.45,(100,100,120),1)
        cv2.imshow('Counter Siege',f)
        k=cv2.waitKey(30)&0xFF
        if k==13: entering=False; name=input_str if input_str else 'Player'
        elif k==8: input_str=input_str[:-1]
        elif 32<=k<=126 and len(input_str)<16: input_str+=chr(k)
        elif k==27: return None,None,None

    # Team selection
    team='CT'
    if mode in ('solo','host','join'):
        sel2=0
        team_opts=[('Counter-Terrorist (CT)','CT'),('Terrorist (T)','T')]
        while True:
            f=frame.copy(); f[:]=0
            draw_menu(f,sel2,team_opts,'SELECT TEAM',f'Welcome, {name}!')
            cv2.imshow('Counter Siege',f)
            k=cv2.waitKey(30)&0xFF
            if k==27: return None,None,None
            elif k in (ord('w'),ord('W'),82): sel2=(sel2-1)%2
            elif k in (ord('s'),ord('S'),84): sel2=(sel2+1)%2
            elif k==13 or k==ord('\r'): team=team_opts[sel2][1]; break
            elif k==ord('1'): team='CT'; break
            elif k==ord('2'): team='T'; break

    # Host IP entry if joining
    host = '127.0.0.1'
    if mode=='join':
        entering=True; input_str=''
        while entering:
            f=np.zeros((H,W,3),dtype=np.uint8)
            cv2.putText(f,'ENTER HOST IP ADDRESS:',(W//2-180,H//2-20),
                       cv2.FONT_HERSHEY_SIMPLEX,0.85,(0,180,255),2)
            cv2.putText(f,input_str+'_',(W//2-180,H//2+40),
                       cv2.FONT_HERSHEY_SIMPLEX,1.0,(255,255,255),2)
            cv2.putText(f,'e.g. 192.168.1.5  (Press ENTER)',(W//2-200,H//2+90),
                       cv2.FONT_HERSHEY_SIMPLEX,0.42,(100,100,120),1)
            cv2.imshow('Counter Siege',f)
            k=cv2.waitKey(30)&0xFF
            if k==13: entering=False; host=input_str if input_str else '127.0.0.1'
            elif k==8: input_str=input_str[:-1]
            elif 32<=k<=126 and len(input_str)<20: input_str+=chr(k)
            elif k==27: return None,None,None

    return mode, name, team, host if mode=='join' else None

# ─────────────────────────────────────────────
#  IMPROVED MOVEMENT with proper key hold
# ─────────────────────────────────────────────
class ImprovedGame(Game):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keys_held = {
            'w':False,'s':False,'a':False,'d':False,'c':False
        }

    def run(self):
        cv2.namedWindow('Counter Siege', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Counter Siege', W, H)
        cv2.setMouseCallback('Counter Siege', self.inp.process_mouse)

        last_time = time.time()
        frame_count = 0
        fps_timer = time.time()
        fps_display = 0

        while self.running:
            now = time.time()
            dt = now - last_time
            last_time = now
            frame_count+=1
            if now-fps_timer>1.0:
                fps_display=frame_count; frame_count=0; fps_timer=now

            gs = self.gs
            lp = gs.local_player()

            if self.server:
                self.server.tick()

            if self.bots is not None and gs.round_phase in ('live','planted','buy'):
                self._update_bots()

            # Process ALL pending keys
            key = cv2.waitKey(1) & 0xFF

            if key != 255:
                if key == 27: break
                # Toggle held keys
                if key in (ord('w'),ord('W')): self._keys_held['w']=True
                elif key in (ord('s'),ord('S')): self._keys_held['s']=True
                elif key in (ord('a'),ord('A')): self._keys_held['a']=True
                elif key in (ord('d'),ord('D')): self._keys_held['d']=True
                elif key in (ord('c'),ord('C')):
                    if lp: lp.crouching = not lp.crouching
                self._handle_key(key, lp, now)

            # Movement via held keys
            if lp and lp.alive and gs.round_phase in ('live','planted','buy'):
                self._move_with_held(lp, gs, dt)
                if self.client and now-self.last_update_sent>0.05:
                    self.last_update_sent=now
                    self.client.send({'type':'update','x':lp.x,'y':lp.y,'angle':lp.angle})

            # Shooting
            if lp and lp.alive and self.inp.mouse_left:
                self._shoot(lp, gs, now)

            # Phase logic
            if self.mode in ('solo','host'):
                self._solo_phase_logic(gs, lp, now)

            # Decay
            if lp:
                lp.recoil = max(0, lp.recoil - dt*3)
                lp.flash_level = max(0, lp.flash_level - dt*0.5)

            # Hold-key decay: if no key pressed this frame, release movement
            # (since OpenCV only gives keydown) — use a timer approach
            if key == 255:
                # No key this frame — clear movement keys after short timeout
                for k in ('w','s','a','d'):
                    self._keys_held[k] = False

            frame = self.renderer.render()
            cv2.putText(frame,f'FPS:{fps_display}',(10,20),
                       cv2.FONT_HERSHEY_SIMPLEX,0.4,C['gray'],1)
            # LAN info
            if self.mode=='host':
                try:
                    ip=socket.gethostbyname(socket.gethostname())
                except: ip='?'
                cv2.putText(frame,f'HOST IP: {ip}:{PORT}',(10,40),
                           cv2.FONT_HERSHEY_SIMPLEX,0.38,(0,200,100),1)
            self._draw_minimap(frame, lp)
            cv2.imshow('Counter Siege', frame)

        cv2.destroyAllWindows()

    def _move_with_held(self, lp, gs, dt):
        lp.angle += self.inp.mouse_dx
        self.inp.mouse_dx = 0
        spd = (0.03 if lp.crouching else 0.065) * min(dt*60, 2.0)
        dx = dy = 0
        if self._keys_held.get('w'): dx+=math.cos(lp.angle)*spd; dy+=math.sin(lp.angle)*spd
        if self._keys_held.get('s'): dx-=math.cos(lp.angle)*spd; dy-=math.sin(lp.angle)*spd
        if self._keys_held.get('a'): dx+=math.cos(lp.angle-math.pi/2)*spd; dy+=math.sin(lp.angle-math.pi/2)*spd
        if self._keys_held.get('d'): dx+=math.cos(lp.angle+math.pi/2)*spd; dy+=math.sin(lp.angle+math.pi/2)*spd
        margin=0.3
        nx,ny=lp.x+dx,lp.y+dy
        if not gs.map.is_wall(nx,lp.y): lp.x=nx
        if not gs.map.is_wall(lp.x,ny): lp.y=ny

    def _handle_key(self, key, lp, now):
        gs=self.gs
        # Movement is handled separately
        if key==ord('b') or key==ord('B'): gs.show_buy=not gs.show_buy
        elif key==9: gs.show_scoreboard=not gs.show_scoreboard
        elif key==ord('r') or key==ord('R'):
            if lp and lp.alive:
                w=lp.weapon; wname=lp.current_weapon
                proto=WEAPONS.get(wname,{})
                if proto.get('mag',0)>0 and w.get('ammo',0)>0:
                    reload_dur=proto.get('reload',2.0)
                    lp.reload_time=now+reload_dur
                    w['reload_time_set']=reload_dur
                    refill=min(proto.get('mag',30)-w.get('mag',0), w.get('ammo',0))
                    w['ammo']-=refill; w['mag']=proto.get('mag',30)
        elif key==ord('e') or key==ord('E'):
            if lp and lp.alive: self._interact(lp,gs,now)
        elif key==ord('g') or key==ord('G'):
            if lp and lp.alive:
                for gname in ['henade','flash','smoke']:
                    if gname in lp.weapons and lp.weapons[gname].get('mag',0)>0:
                        self._throw_grenade(lp,gs,gname,now); break
        elif ord('1')<=key<=ord('5'):
            if lp:
                idx=key-ord('1')
                wlist=list(lp.weapons.keys())
                if idx<len(wlist): lp.switch_weapon(wlist[idx])
        # Buy menu
        if gs.show_buy and lp and gs.round_phase=='buy':
            avail=T_WEAPONS if lp.team=='T' else CT_WEAPONS
            if ord('1')<=key<=ord('9'):
                idx=key-ord('1')
                if idx<len(avail): self._do_buy(lp,avail[idx],gs)

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Counter Siege FPS')
    parser.add_argument('--host',action='store_true',help='Start as host')
    parser.add_argument('--join',metavar='IP',help='Join a host by IP')
    parser.add_argument('--name',default='',help='Player name')
    parser.add_argument('--team',default='',choices=['T','CT'],help='Team')
    parser.add_argument('--solo',action='store_true',help='Solo vs bots')
    args=parser.parse_args()

    if args.host or args.join or args.solo or args.name:
        # Command-line mode
        mode='solo' if args.solo else ('host' if args.host else 'join')
        name=args.name or 'Player'
        team=args.team or 'CT'
        host=args.join or '127.0.0.1'
        game=ImprovedGame(mode,host=host if mode=='join' else None,name=name,team=team)
        game.run()
    else:
        # GUI menu
        result=main_menu()
        if result and result[0]:
            if len(result)==4:
                mode,name,team,host=result
            else:
                mode,name,team=result; host=None
            if mode and name:
                try:
                    game=ImprovedGame(mode,host=host,name=name,team=team)
                    game.run()
                except Exception as e:
                    print(f"Error starting game: {e}")
                    import traceback; traceback.print_exc()
