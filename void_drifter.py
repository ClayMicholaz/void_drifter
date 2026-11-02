"""
╔══════════════════════════════════════════════════════════════╗
║                      VOID DRIFTER                           ║
║              A Neon Arena Survival Game                      ║
╠══════════════════════════════════════════════════════════════╣
║  Controls:                                                   ║
║    WASD / Arrows  - Move                                     ║
║    Mouse          - Aim                                      ║
║    Left Click     - Shoot                                    ║
║    Space          - Dash (costs energy, grants i-frames)     ║
║    1 / 2 / 3      - Switch Weapons                           ║
║      [1] Pulse   - Balanced rapid fire                       ║
║      [2] Scatter - Shotgun spread                            ║
║      [3] Beam    - Fast narrow bolts                         ║
║                                                              ║
║  Mechanics:                                                  ║
║    • Kill enemies to drop XP crystals                        ║
║    • Crystals are magnetically attracted to you               ║
║    • Level up to choose from random upgrades                  ║
║    • Chain kills for combo multiplier (score × combo)         ║
║    • Chasers split into smaller copies on death               ║
║    • Chargers telegraph then rush you                         ║
║    • Orbiters circle you then dash inward                     ║
║    • Shooters strafe and fire projectiles                     ║
║    • Waves grow harder with enemy tiers scaling up            ║
╚══════════════════════════════════════════════════════════════╝
"""

import pygame
import math
import random
import sys

# ─── Initialise ──────────────────────────────────────────────
pygame.init()

# ─── Constants ───────────────────────────────────────────────
WIDTH, HEIGHT = 1280, 720
FPS = 60

# Arena half-size (world coords −ARENA..+ARENA)
ARENA = 900

# ── Neon colour palette ──
C_BG         = (5, 5, 15)
C_GRID       = (15, 15, 35)
C_PLAYER     = (0, 255, 200)
C_PLAYER_GLOW = (0, 180, 140)
C_BULLET     = (255, 255, 100)
C_ENEMY_1    = (255, 50, 80)       # Chaser  – red
C_ENEMY_2    = (255, 140, 30)      # Shooter – orange
C_ENEMY_3    = (180, 50, 255)      # Charger – purple
C_ENEMY_4    = (50, 150, 255)      # Orbiter – blue
C_XP         = (100, 255, 150)
C_HEALTH     = (255, 50, 80)
C_ENERGY     = (50, 150, 255)
C_SHIELD     = (100, 200, 255)
C_COMBO      = (255, 220, 50)
C_WHITE      = (255, 255, 255)

# ── Physics tunables ──
PLAYER_SPEED   = 5.0
PLAYER_ACCEL   = 0.5
PLAYER_FRICTION = 0.88
DASH_SPEED     = 25
DASH_DURATION  = 8   # frames
DASH_COOLDOWN  = 45  # frames


# ═══════════════════════════════════════════════════════════
#  Utility helpers
# ═══════════════════════════════════════════════════════════
def vec_len(x, y):
    return math.hypot(x, y)

def vec_norm(x, y):
    length = math.hypot(x, y)
    if length == 0:
        return 0.0, 0.0
    return x / length, y / length

def vec_dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])

def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ═══════════════════════════════════════════════════════════
#  Particle system
# ═══════════════════════════════════════════════════════════
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life",
                 "color", "size", "decay")

    def __init__(self, x, y, vx, vy, life, color, size=3, decay=0.96):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.color = color
        self.size = size
        self.decay = decay

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= self.decay
        self.vy *= self.decay
        self.life -= 1
        return self.life > 0

    def draw(self, surface, cam_x, cam_y):
        t = self.life / self.max_life
        s = max(1, int(self.size * t))
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        if 0 <= sx <= WIDTH and 0 <= sy <= HEIGHT:
            color = (
                min(255, int(self.color[0] * t)),
                min(255, int(self.color[1] * t)),
                min(255, int(self.color[2] * t)),
            )
            pygame.draw.circle(surface, color, (sx, sy), s)


class ParticleSystem:
    MAX_PARTICLES = 2000

    def __init__(self):
        self.particles: list[Particle] = []

    def emit(self, x, y, count, color,
             speed_range=(1, 5), life_range=(15, 40),
             size=3, decay=0.96):
        budget = self.MAX_PARTICLES - len(self.particles)
        for _ in range(min(count, budget)):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(*speed_range)
            life = random.randint(*life_range)
            self.particles.append(Particle(
                x, y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life, color, size, decay,
            ))

    def emit_directional(self, x, y, count, color,
                         angle, spread,
                         speed_range=(2, 6), life_range=(10, 30),
                         size=2):
        budget = self.MAX_PARTICLES - len(self.particles)
        for _ in range(min(count, budget)):
            a = angle + random.uniform(-spread, spread)
            speed = random.uniform(*speed_range)
            life = random.randint(*life_range)
            self.particles.append(Particle(
                x, y,
                math.cos(a) * speed,
                math.sin(a) * speed,
                life, color, size,
            ))

    def update(self):
        self.particles = [p for p in self.particles if p.update()]

    def draw(self, surface, cam_x=0, cam_y=0):
        for p in self.particles:
            p.draw(surface, cam_x, cam_y)


# ═══════════════════════════════════════════════════════════
#  Player
# ═══════════════════════════════════════════════════════════
class Player:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.radius = 14

        # Vitals
        self.max_hp = 100
        self.hp = self.max_hp
        self.max_energy = 100
        self.energy = float(self.max_energy)
        self.energy_regen = 0.15

        # Dash state
        self.dash_timer = 0
        self.dash_cooldown = 0
        self.dash_dir = (0.0, 0.0)
        self.invincible = 0

        # Weapons ---------------------------------------------------
        self.weapons = [
            {
                "name": "Pulse", "fire_rate": 8,
                "damage": 12, "speed": 14,
                "spread": 0.05, "count": 1,
                "color": C_BULLET, "size": 4,
            },
            {
                "name": "Scatter", "fire_rate": 20,
                "damage": 8, "speed": 12,
                "spread": 0.12, "count": 5,
                "color": (255, 150, 50), "size": 3,
            },
            {
                "name": "Beam", "fire_rate": 3,
                "damage": 4, "speed": 22,
                "spread": 0.02, "count": 1,
                "color": (100, 200, 255), "size": 2,
            },
        ]
        self.current_weapon = 0
        self.fire_cooldown = 0

        # Score / combo
        self.score = 0
        self.combo = 1
        self.combo_timer = 0
        self.combo_max_timer = 120  # 2 s

        # XP / level
        self.xp = 0
        self.level = 1
        self.xp_to_next = 50

        # Upgrade multipliers
        self.damage_mult = 1.0
        self.speed_mult = 1.0
        self.fire_rate_mult = 1.0

        # Visual helpers
        self.trail_timer = 0
        self.hit_flash = 0

    # ── per-frame update ──
    def update(self, keys, mouse_pos, particles, cam_x, cam_y):
        # Movement input
        ix, iy = 0.0, 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:    iy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  iy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  ix -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: ix += 1
        if ix != 0 or iy != 0:
            ix, iy = vec_norm(ix, iy)

        # Dash override
        if self.dash_timer > 0:
            self.vx = self.dash_dir[0] * DASH_SPEED
            self.vy = self.dash_dir[1] * DASH_SPEED
            self.dash_timer -= 1
            self.invincible = 5
            particles.emit(self.x, self.y, 3, C_PLAYER,
                           speed_range=(0.5, 2), life_range=(10, 25), size=5)
        else:
            speed = PLAYER_SPEED * self.speed_mult
            self.vx += ix * PLAYER_ACCEL * speed
            self.vy += iy * PLAYER_ACCEL * speed
            self.vx *= PLAYER_FRICTION
            self.vy *= PLAYER_FRICTION

        self.x += self.vx
        self.y += self.vy
        self.x = clamp(self.x, -ARENA, ARENA)
        self.y = clamp(self.y, -ARENA, ARENA)

        # Timers
        if self.dash_cooldown > 0:
            self.dash_cooldown -= 1
        if self.fire_cooldown > 0:
            self.fire_cooldown -= 1
        if self.invincible > 0:
            self.invincible -= 1
        if self.hit_flash > 0:
            self.hit_flash -= 1
        self.energy = min(self.max_energy, self.energy + self.energy_regen)

        # Combo decay
        if self.combo_timer > 0:
            self.combo_timer -= 1
        else:
            self.combo = 1

        # Aim direction
        world_mx = mouse_pos[0] + cam_x
        world_my = mouse_pos[1] + cam_y
        self.angle = math.atan2(world_my - self.y, world_mx - self.x)

        # Engine trail
        self.trail_timer += 1
        if self.trail_timer % 3 == 0 and (abs(self.vx) > 1 or abs(self.vy) > 1):
            particles.emit(
                self.x - self.vx * 0.5, self.y - self.vy * 0.5,
                1, C_PLAYER_GLOW,
                speed_range=(0.2, 0.8), life_range=(8, 20), size=3,
            )

    # ── actions ──
    def try_dash(self):
        if self.dash_cooldown <= 0 and self.dash_timer <= 0 and self.energy >= 20:
            dx, dy = math.cos(self.angle), math.sin(self.angle)
            if abs(self.vx) > 0.5 or abs(self.vy) > 0.5:
                dx, dy = vec_norm(self.vx, self.vy)
            self.dash_dir = (dx, dy)
            self.dash_timer = DASH_DURATION
            self.dash_cooldown = DASH_COOLDOWN
            self.energy -= 20
            self.invincible = DASH_DURATION + 3
            return True
        return False

    def try_shoot(self, bullets):
        w = self.weapons[self.current_weapon]
        rate = max(2, int(w["fire_rate"] / self.fire_rate_mult))
        if self.fire_cooldown > 0:
            return False
        self.fire_cooldown = rate

        half = (w["count"] - 1) / 2.0
        for i in range(w["count"]):
            spread = random.uniform(-w["spread"], w["spread"])
            if w["count"] > 1:
                spread += (i - half) * w["spread"] * 2
            a = self.angle + spread
            bx = self.x + math.cos(self.angle) * 20
            by = self.y + math.sin(self.angle) * 20
            bullets.append(Bullet(
                bx, by,
                math.cos(a) * w["speed"],
                math.sin(a) * w["speed"],
                int(w["damage"] * self.damage_mult),
                w["color"], w["size"],
            ))
        return True

    def take_damage(self, amount):
        if self.invincible > 0:
            return False
        self.hp -= amount
        self.hit_flash = 15
        self.invincible = 30
        return True

    def add_xp(self, amount):
        self.xp += amount
        if self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.xp_to_next = int(self.xp_to_next * 1.5)
            return True
        return False

    def add_combo(self):
        self.combo_timer = self.combo_max_timer
        self.combo += 1

    # ── drawing ──
    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)

        # Glow halo
        glow_surf = pygame.Surface((60, 60), pygame.SRCALPHA)
        g_col = C_PLAYER if self.hit_flash <= 0 else (255, 100, 100)
        for r in range(30, 5, -3):
            alpha = int(25 * (1 - r / 30))
            pygame.draw.circle(glow_surf, (*g_col, alpha), (30, 30), r)
        surface.blit(glow_surf, (sx - 30, sy - 30),
                     special_flags=pygame.BLEND_ADD)

        # Shield ring while invincible (not during dash itself)
        if self.invincible > 0 and self.dash_timer <= 0:
            pygame.draw.circle(surface, C_SHIELD, (sx, sy),
                               self.radius + 6, 2)

        # Body – triangle pointing toward cursor
        cos_a = math.cos(self.angle)
        sin_a = math.sin(self.angle)
        r = self.radius
        pts = [
            (sx + cos_a * r * 1.3, sy + sin_a * r * 1.3),
            (sx + math.cos(self.angle + 2.4) * r,
             sy + math.sin(self.angle + 2.4) * r),
            (sx + math.cos(self.angle - 2.4) * r,
             sy + math.sin(self.angle - 2.4) * r),
        ]
        body_col = C_PLAYER if self.hit_flash <= 0 else (255, 150, 150)
        pygame.draw.polygon(surface, body_col, pts)
        pygame.draw.polygon(surface, C_WHITE, pts, 2)

        # Engine glow dot
        ex = sx - cos_a * r * 0.8
        ey = sy - sin_a * r * 0.8
        pygame.draw.circle(surface, (0, 200, 180), (int(ex), int(ey)), 4)


# ═══════════════════════════════════════════════════════════
#  Projectiles
# ═══════════════════════════════════════════════════════════
class Bullet:
    def __init__(self, x, y, vx, vy, damage, color, size=4):
        self.x = x;  self.y = y
        self.vx = vx; self.vy = vy
        self.damage = damage
        self.color = color
        self.size = size
        self.life = 90
        self.active = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        if self.life <= 0 or abs(self.x) > 1050 or abs(self.y) > 1050:
            self.active = False
        return self.active

    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        if -10 < sx < WIDTH + 10 and -10 < sy < HEIGHT + 10:
            tx = int(self.x - self.vx * 0.5 - cam_x)
            ty = int(self.y - self.vy * 0.5 - cam_y)
            pygame.draw.line(surface, self.color, (tx, ty), (sx, sy),
                             max(1, self.size - 1))
            pygame.draw.circle(surface, C_WHITE, (sx, sy),
                               max(1, self.size // 2))


class EnemyBullet:
    def __init__(self, x, y, vx, vy, damage, color=(255, 100, 80)):
        self.x = x;  self.y = y
        self.vx = vx; self.vy = vy
        self.damage = damage
        self.color = color
        self.life = 180
        self.active = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        if self.life <= 0 or abs(self.x) > 1050 or abs(self.y) > 1050:
            self.active = False
        return self.active

    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        if -10 < sx < WIDTH + 10 and -10 < sy < HEIGHT + 10:
            pygame.draw.circle(surface, self.color, (sx, sy), 5)
            pygame.draw.circle(surface, C_WHITE, (sx, sy), 2)


# ═══════════════════════════════════════════════════════════
#  Enemy base & four variants
# ═══════════════════════════════════════════════════════════
class Enemy:
    def __init__(self, x, y, hp, speed, radius, color,
                 score_value, damage=10):
        self.x = float(x); self.y = float(y)
        self.vx = 0.0;     self.vy = 0.0
        self.hp = hp;       self.max_hp = hp
        self.speed = speed; self.radius = radius
        self.color = color; self.score_value = score_value
        self.damage = damage
        self.active = True
        self.hit_flash = 0
        self.spawn_anim = 20

    def take_damage(self, amount, particles):
        self.hp -= amount
        self.hit_flash = 6
        particles.emit(self.x, self.y, 5, self.color,
                       speed_range=(1, 3), life_range=(8, 15), size=2)
        if self.hp <= 0:
            self.active = False
            particles.emit(self.x, self.y, 25, self.color,
                           speed_range=(2, 7), life_range=(15, 40), size=4)
            particles.emit(self.x, self.y, 10, C_WHITE,
                           speed_range=(1, 4), life_range=(5, 15), size=2)
            return True
        return False

    def _draw_spawn_ring(self, surface, cam_x, cam_y):
        """Draw expanding ring during spawn; returns True when spawn done."""
        if self.spawn_anim > 0:
            self.spawn_anim -= 1
            sx = int(self.x - cam_x)
            sy = int(self.y - cam_y)
            r = int(self.radius * (1 + self.spawn_anim * 0.3))
            if -r < sx < WIDTH + r and -r < sy < HEIGHT + r:
                pygame.draw.circle(surface, self.color, (sx, sy), r, 2)
            return False
        return True

    def _draw_hp_bar(self, surface, cam_x, cam_y):
        if self.hp < self.max_hp:
            sx = int(self.x - cam_x)
            sy = int(self.y - cam_y) - self.radius - 8
            bar_w = self.radius * 2
            pygame.draw.rect(surface, (40, 40, 40),
                             (sx - bar_w // 2, sy, bar_w, 4))
            fill = int(bar_w * self.hp / self.max_hp)
            pygame.draw.rect(surface, C_HEALTH,
                             (sx - bar_w // 2, sy, fill, 4))


# ── Chaser (diamond) ─────────────────────────────────────
class Chaser(Enemy):
    """Relentlessly chases the player.  Splits on death when tier > 1."""

    def __init__(self, x, y, tier=1):
        super().__init__(
            x, y,
            hp=25 * tier,
            speed=2.5 + tier * 0.3,
            radius=10 + tier * 2,
            color=C_ENEMY_1,
            score_value=10 * tier,
            damage=8 + tier * 2,
        )
        self.tier = tier

    def update(self, player, enemy_bullets, particles):
        if self.spawn_anim > 0:
            return
        dx, dy = vec_norm(player.x - self.x, player.y - self.y)
        self.vx = lerp(self.vx, dx * self.speed, 0.05)
        self.vy = lerp(self.vy, dy * self.speed, 0.05)
        self.x += self.vx
        self.y += self.vy

    def draw(self, surface, cam_x, cam_y):
        if not self._draw_spawn_ring(surface, cam_x, cam_y):
            return
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        col = C_WHITE if self.hit_flash > 0 else self.color
        self.hit_flash = max(0, self.hit_flash - 1)
        r = self.radius
        pts = [(sx, sy - r), (sx + r, sy), (sx, sy + r), (sx - r, sy)]
        pygame.draw.polygon(surface, col, pts)
        pygame.draw.polygon(surface, C_WHITE, pts, 2)
        self._draw_hp_bar(surface, cam_x, cam_y)


# ── Shooter (hexagon) ────────────────────────────────────
class Shooter(Enemy):
    """Keeps distance and fires at the player."""

    def __init__(self, x, y, tier=1):
        super().__init__(
            x, y,
            hp=35 * tier,
            speed=1.8,
            radius=12 + tier * 2,
            color=C_ENEMY_2,
            score_value=15 * tier,
            damage=5,
        )
        self.tier = tier
        self.shoot_cd = 0
        self.pref_dist = 250 + random.uniform(-50, 50)

    def update(self, player, enemy_bullets, particles):
        if self.spawn_anim > 0:
            return
        dist = vec_dist((self.x, self.y), (player.x, player.y))
        dx, dy = vec_norm(player.x - self.x, player.y - self.y)

        if dist < self.pref_dist - 30:            # too close – back off
            self.vx = lerp(self.vx, -dx * self.speed, 0.05)
            self.vy = lerp(self.vy, -dy * self.speed, 0.05)
        elif dist > self.pref_dist + 30:           # too far – approach
            self.vx = lerp(self.vx,  dx * self.speed, 0.05)
            self.vy = lerp(self.vy,  dy * self.speed, 0.05)
        else:                                      # strafe
            self.vx = lerp(self.vx, -dy * self.speed * 0.5, 0.05)
            self.vy = lerp(self.vy,  dx * self.speed * 0.5, 0.05)

        self.x += self.vx
        self.y += self.vy
        self.x = clamp(self.x, -ARENA + 10, ARENA - 10)
        self.y = clamp(self.y, -ARENA + 10, ARENA - 10)

        # Fire
        self.shoot_cd -= 1
        if self.shoot_cd <= 0 and dist < 450:
            self.shoot_cd = max(40, 80 - self.tier * 10)
            angle = math.atan2(player.y - self.y, player.x - self.x)
            spd = 5 + self.tier
            half = (self.tier - 1) / 2.0
            for i in range(self.tier):
                s = (i - half) * 0.15
                enemy_bullets.append(EnemyBullet(
                    self.x, self.y,
                    math.cos(angle + s) * spd,
                    math.sin(angle + s) * spd,
                    self.damage,
                ))
            particles.emit_directional(self.x, self.y, 5, C_ENEMY_2,
                                       angle, 0.3, speed_range=(2, 5))

    def draw(self, surface, cam_x, cam_y):
        if not self._draw_spawn_ring(surface, cam_x, cam_y):
            return
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        col = C_WHITE if self.hit_flash > 0 else self.color
        self.hit_flash = max(0, self.hit_flash - 1)
        r = self.radius
        pts = [(int(sx + r * math.cos(i * math.pi / 3)),
                int(sy + r * math.sin(i * math.pi / 3))) for i in range(6)]
        pygame.draw.polygon(surface, col, pts)
        pygame.draw.polygon(surface, C_WHITE, pts, 2)
        # "eye"
        a = math.atan2(self.vy, self.vx) if abs(self.vx) > 0.1 else 0
        pygame.draw.circle(surface, (50, 30, 10),
                           (int(sx + math.cos(a) * 4),
                            int(sy + math.sin(a) * 4)), 3)
        self._draw_hp_bar(surface, cam_x, cam_y)


# ── Charger (pentagon) ───────────────────────────────────
class Charger(Enemy):
    """Winds up, telegraphs direction, then charges at the player."""

    def __init__(self, x, y, tier=1):
        super().__init__(
            x, y,
            hp=50 * tier,
            speed=1.5,
            radius=16 + tier * 2,
            color=C_ENEMY_3,
            score_value=20 * tier,
            damage=20 + tier * 5,
        )
        self.tier = tier
        self.state = "idle"
        self.state_timer = 0
        self.charge_dir = (0.0, 0.0)
        self.charge_speed = 12 + tier * 2

    def update(self, player, enemy_bullets, particles):
        if self.spawn_anim > 0:
            return
        dist = vec_dist((self.x, self.y), (player.x, player.y))
        dx, dy = vec_norm(player.x - self.x, player.y - self.y)

        if self.state == "idle":
            self.vx = lerp(self.vx, dx * self.speed, 0.03)
            self.vy = lerp(self.vy, dy * self.speed, 0.03)
            self.x += self.vx
            self.y += self.vy
            if dist < 300:
                self.state = "windup"
                self.state_timer = 45
                self.charge_dir = (dx, dy)

        elif self.state == "windup":
            self.vx *= 0.9
            self.vy *= 0.9
            self.x += random.uniform(-2, 2)
            self.y += random.uniform(-2, 2)
            self.charge_dir = vec_norm(player.x - self.x,
                                       player.y - self.y)
            particles.emit(self.x, self.y, 1, C_ENEMY_3,
                           speed_range=(0.5, 1.5), life_range=(5, 10),
                           size=3)
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = "charging"
                self.state_timer = 25

        elif self.state == "charging":
            self.vx = self.charge_dir[0] * self.charge_speed
            self.vy = self.charge_dir[1] * self.charge_speed
            self.x += self.vx
            self.y += self.vy
            particles.emit(self.x, self.y, 2, C_ENEMY_3,
                           speed_range=(1, 3), life_range=(8, 15), size=3)
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = "recovering"
                self.state_timer = 60

        elif self.state == "recovering":
            self.vx *= 0.92
            self.vy *= 0.92
            self.x += self.vx
            self.y += self.vy
            self.state_timer -= 1
            if self.state_timer <= 0:
                self.state = "idle"

        self.x = clamp(self.x, -ARENA + 10, ARENA - 10)
        self.y = clamp(self.y, -ARENA + 10, ARENA - 10)

    def draw(self, surface, cam_x, cam_y):
        if not self._draw_spawn_ring(surface, cam_x, cam_y):
            return
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        col = C_WHITE if self.hit_flash > 0 else self.color
        if self.state == "windup":
            col = C_WHITE if self.state_timer % 6 < 3 else self.color
        self.hit_flash = max(0, self.hit_flash - 1)
        r = self.radius
        ang_off = (math.atan2(self.charge_dir[1], self.charge_dir[0])
                   if self.state in ("windup", "charging") else 0)
        pts = [(int(sx + r * math.cos(ang_off + i * math.tau / 5 - math.pi / 2)),
                int(sy + r * math.sin(ang_off + i * math.tau / 5 - math.pi / 2)))
               for i in range(5)]
        pygame.draw.polygon(surface, col, pts)
        pygame.draw.polygon(surface, C_WHITE, pts, 2)
        # Telegraph line
        if self.state == "windup":
            tx = sx + self.charge_dir[0] * 40
            ty = sy + self.charge_dir[1] * 40
            pygame.draw.line(surface, (255, 255, 100),
                             (sx, sy), (int(tx), int(ty)), 2)
        self._draw_hp_bar(surface, cam_x, cam_y)


# ── Orbiter (circle) ─────────────────────────────────────
class Orbiter(Enemy):
    """Circles around the player, periodically dashes inward."""

    def __init__(self, x, y, tier=1):
        super().__init__(
            x, y,
            hp=30 * tier,
            speed=3.0,
            radius=11 + tier * 2,
            color=C_ENEMY_4,
            score_value=12 * tier,
            damage=12 + tier * 3,
        )
        self.tier = tier
        self.orbit_angle = random.uniform(0, math.tau)
        self.orbit_speed = 0.03 + random.uniform(-0.005, 0.005)
        self.orbit_dist = 180 + random.uniform(-30, 30)
        self.dash_cd = random.randint(120, 240)
        self.dashing = 0
        self.dash_dir = (0.0, 0.0)

    def update(self, player, enemy_bullets, particles):
        if self.spawn_anim > 0:
            return

        if self.dashing > 0:
            self.x += self.dash_dir[0] * 10
            self.y += self.dash_dir[1] * 10
            self.dashing -= 1
            particles.emit(self.x, self.y, 1, C_ENEMY_4,
                           speed_range=(0.5, 2), life_range=(5, 12), size=2)
        else:
            self.orbit_angle += self.orbit_speed
            tx = player.x + math.cos(self.orbit_angle) * self.orbit_dist
            ty = player.y + math.sin(self.orbit_angle) * self.orbit_dist
            dx, dy = vec_norm(tx - self.x, ty - self.y)
            self.vx = lerp(self.vx, dx * self.speed, 0.08)
            self.vy = lerp(self.vy, dy * self.speed, 0.08)
            self.x += self.vx
            self.y += self.vy

            self.dash_cd -= 1
            if self.dash_cd <= 0:
                self.dash_cd = random.randint(120, 240)
                self.dashing = 15
                self.dash_dir = vec_norm(player.x - self.x,
                                         player.y - self.y)

        self.x = clamp(self.x, -ARENA + 10, ARENA - 10)
        self.y = clamp(self.y, -ARENA + 10, ARENA - 10)

    def draw(self, surface, cam_x, cam_y):
        if not self._draw_spawn_ring(surface, cam_x, cam_y):
            return
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        col = C_WHITE if self.hit_flash > 0 else self.color
        self.hit_flash = max(0, self.hit_flash - 1)
        pygame.draw.circle(surface, col, (sx, sy), self.radius)
        pygame.draw.circle(surface, C_WHITE, (sx, sy), self.radius, 2)
        pygame.draw.circle(surface, (30, 80, 150), (sx, sy),
                           self.radius // 2)
        self._draw_hp_bar(surface, cam_x, cam_y)


# ═══════════════════════════════════════════════════════════
#  XP Crystal
# ═══════════════════════════════════════════════════════════
class Crystal:
    def __init__(self, x, y, value=5):
        self.x = x; self.y = y
        self.value = value
        self.radius = 6 + value // 5
        self.bob = random.uniform(0, math.tau)
        self.active = True

    def update(self, player):
        self.bob += 0.08
        dist = vec_dist((self.x, self.y), (player.x, player.y))
        # Magnetic pull
        if dist < 140:
            dx, dy = vec_norm(player.x - self.x, player.y - self.y)
            pull = (1 - dist / 140) * 8
            self.x += dx * pull
            self.y += dy * pull
        # Collect
        if dist < player.radius + self.radius:
            self.active = False
            return self.value
        return 0

    def draw(self, surface, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y + math.sin(self.bob) * 3)
        if -20 < sx < WIDTH + 20 and -20 < sy < HEIGHT + 20:
            glow_s = pygame.Surface((30, 30), pygame.SRCALPHA)
            pygame.draw.circle(glow_s, (*C_XP, 40), (15, 15), 15)
            surface.blit(glow_s, (sx - 15, sy - 15),
                         special_flags=pygame.BLEND_ADD)
            r = self.radius
            pts = [(sx, sy - r), (sx + int(r * 0.6), sy),
                   (sx, sy + r), (sx - int(r * 0.6), sy)]
            pygame.draw.polygon(surface, C_XP, pts)
            pygame.draw.polygon(surface, C_WHITE, pts, 1)


# ═══════════════════════════════════════════════════════════
#  Main Game class
# ═══════════════════════════════════════════════════════════
class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("VOID DRIFTER")
        self.clock = pygame.time.Clock()

        # Fonts — fall back gracefully
        try:
            self.font_title = pygame.font.SysFont("consolas", 72, bold=True)
            self.font_large = pygame.font.SysFont("consolas", 36, bold=True)
            self.font_med   = pygame.font.SysFont("consolas", 24)
            self.font_small = pygame.font.SysFont("consolas", 16)
        except Exception:
            self.font_title = pygame.font.Font(None, 72)
            self.font_large = pygame.font.Font(None, 36)
            self.font_med   = pygame.font.Font(None, 24)
            self.font_small = pygame.font.Font(None, 16)

        self.reset()

    # ── state reset ──
    def reset(self):
        self.player = Player(0, 0)
        self.bullets: list[Bullet] = []
        self.enemy_bullets: list[EnemyBullet] = []
        self.enemies: list[Enemy] = []
        self.crystals: list[Crystal] = []
        self.particles = ParticleSystem()

        self.wave = 0
        self.wave_spawning = False
        self.spawn_queue: list[tuple] = []
        self.spawn_timer = 0
        self.wave_clear_timer = 0

        self.cam_x = 0.0; self.cam_y = 0.0
        self.shake_x = 0.0; self.shake_y = 0.0
        self.shake_intensity = 0.0

        self.state = "menu"  # menu | playing | upgrading | gameover
        self.upgrade_options: list[dict] = []

        self.bg_stars = [
            (random.uniform(-1000, 1000),
             random.uniform(-1000, 1000),
             random.uniform(0.3, 1.0))
            for _ in range(200)
        ]
        self.grid_pulse = 0.0

        self.damage_numbers: list[list] = []
        self.notifications: list[list] = []

    # ── helpers ──
    def add_shake(self, intensity):
        self.shake_intensity = max(self.shake_intensity, intensity)

    def add_notification(self, text, color=C_WHITE):
        self.notifications.append([text, 120, color])

    # ── wave management ──
    def spawn_wave(self):
        self.wave += 1
        self.wave_spawning = True
        base_count = 3 + self.wave * 2
        tier = 1 + self.wave // 5

        queue = []
        for _ in range(base_count):
            roll = random.random()
            if roll < 0.35:
                queue.append(("chaser", tier))
            elif roll < 0.55:
                queue.append(("shooter", min(tier, 3)))
            elif roll < 0.75:
                queue.append(("charger", min(tier, 3)))
            else:
                queue.append(("orbiter", min(tier, 3)))
        self.spawn_queue = queue
        self.spawn_timer = 0
        self.add_notification(f"WAVE {self.wave}", C_COMBO)

    def _spawn_one(self, etype, tier):
        angle = random.uniform(0, math.tau)
        dist = 500 + random.uniform(0, 200)
        x = clamp(self.player.x + math.cos(angle) * dist,
                  -ARENA + 20, ARENA - 20)
        y = clamp(self.player.y + math.sin(angle) * dist,
                  -ARENA + 20, ARENA - 20)
        mapping = {
            "chaser":  Chaser,
            "shooter": Shooter,
            "charger": Charger,
            "orbiter": Orbiter,
        }
        cls = mapping.get(etype, Chaser)
        self.enemies.append(cls(x, y, tier))

    # ── upgrade system ──
    def generate_upgrades(self):
        pool = [
            {"name": "Max HP +20",
             "desc": "Increase maximum health",
             "apply": lambda p: (
                 setattr(p, "max_hp", p.max_hp + 20),
                 setattr(p, "hp", min(p.hp + 20, p.max_hp)))},
            {"name": "Damage +15%",
             "desc": "Increase all damage dealt",
             "apply": lambda p: setattr(p, "damage_mult",
                                        p.damage_mult + 0.15)},
            {"name": "Speed +10%",
             "desc": "Move faster",
             "apply": lambda p: setattr(p, "speed_mult",
                                        p.speed_mult + 0.1)},
            {"name": "Fire Rate +15%",
             "desc": "Shoot faster",
             "apply": lambda p: setattr(p, "fire_rate_mult",
                                        p.fire_rate_mult + 0.15)},
            {"name": "Energy +25",
             "desc": "More dash energy capacity",
             "apply": lambda p: (
                 setattr(p, "max_energy", p.max_energy + 25),
                 setattr(p, "energy", float(p.max_energy)))},
            {"name": "Regen +0.1",
             "desc": "Faster energy regeneration",
             "apply": lambda p: setattr(p, "energy_regen",
                                        p.energy_regen + 0.1)},
            {"name": "Heal 30 HP",
             "desc": "Restore health right now",
             "apply": lambda p: setattr(p, "hp",
                                        min(p.hp + 30, p.max_hp))},
            {"name": "Magnet +40%",
             "desc": "Wider crystal pickup range",
             "apply": lambda p: setattr(p, "radius", p.radius + 4)},
        ]
        random.shuffle(pool)
        self.upgrade_options = pool[:3]

    def apply_upgrade(self, index):
        if 0 <= index < len(self.upgrade_options):
            self.upgrade_options[index]["apply"](self.player)
            self.state = "playing"
            self.upgrade_options = []

    # ═══════════════════════════════════════════════════════
    #  Game-play update
    # ═══════════════════════════════════════════════════════
    def update_playing(self):
        keys = pygame.key.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        mouse_btns = pygame.mouse.get_pressed()

        # Player
        self.player.update(keys, mouse_pos, self.particles,
                           self.cam_x, self.cam_y)

        if mouse_btns[0]:
            self.player.try_shoot(self.bullets)

        # Camera
        tcx = self.player.x - WIDTH / 2
        tcy = self.player.y - HEIGHT / 2
        self.cam_x = lerp(self.cam_x, tcx, 0.08)
        self.cam_y = lerp(self.cam_y, tcy, 0.08)

        # Screen shake
        if self.shake_intensity > 0:
            self.shake_x = random.uniform(-self.shake_intensity,
                                          self.shake_intensity)
            self.shake_y = random.uniform(-self.shake_intensity,
                                          self.shake_intensity)
            self.shake_intensity *= 0.85
            if self.shake_intensity < 0.5:
                self.shake_intensity = 0
                self.shake_x = self.shake_y = 0

        # Projectiles
        self.bullets = [b for b in self.bullets if b.update()]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.update()]

        # Enemies
        for e in self.enemies:
            e.update(self.player, self.enemy_bullets, self.particles)

        # Bullet ↔ enemy collisions
        new_enemies: list[Enemy] = []
        for b in self.bullets:
            if not b.active:
                continue
            for e in self.enemies:
                if not e.active or e.spawn_anim > 0:
                    continue
                if vec_dist((b.x, b.y), (e.x, e.y)) < e.radius + b.size:
                    b.active = False
                    killed = e.take_damage(b.damage, self.particles)
                    self.add_shake(2 if not killed else 6)
                    self.damage_numbers.append(
                        [e.x, e.y - e.radius, str(b.damage), 30, C_BULLET])
                    if killed:
                        self.player.score += (e.score_value
                                              * self.player.combo)
                        self.player.add_combo()
                        for _ in range(random.randint(1, 3)):
                            self.crystals.append(Crystal(
                                e.x + random.uniform(-15, 15),
                                e.y + random.uniform(-15, 15),
                                random.randint(3, 8 + self.wave),
                            ))
                        # Chaser splitting
                        if isinstance(e, Chaser) and e.tier > 1:
                            for _ in range(2):
                                new_enemies.append(Chaser(
                                    e.x + random.uniform(-20, 20),
                                    e.y + random.uniform(-20, 20),
                                    e.tier - 1,
                                ))
                    break  # this bullet is done

        self.enemies.extend(new_enemies)
        self.enemies = [e for e in self.enemies if e.active]

        # Enemy ↔ player body collisions
        for e in self.enemies:
            if e.spawn_anim > 0:
                continue
            if vec_dist((e.x, e.y),
                        (self.player.x, self.player.y)) < (
                            e.radius + self.player.radius):
                if self.player.take_damage(e.damage):
                    self.add_shake(8)
                    self.particles.emit(
                        self.player.x, self.player.y, 15, C_HEALTH,
                        speed_range=(2, 5), life_range=(10, 25), size=3)
                    dx, dy = vec_norm(
                        self.player.x - e.x, self.player.y - e.y)
                    self.player.vx += dx * 8
                    self.player.vy += dy * 8

        # Enemy-bullet ↔ player
        for b in self.enemy_bullets:
            if not b.active:
                continue
            if vec_dist((b.x, b.y),
                        (self.player.x, self.player.y)) < (
                            self.player.radius + 5):
                b.active = False
                if self.player.take_damage(b.damage):
                    self.add_shake(5)
                    self.particles.emit(
                        self.player.x, self.player.y, 10, C_HEALTH,
                        speed_range=(1, 4), life_range=(8, 20), size=2)

        # Crystals
        for c in self.crystals:
            xp = c.update(self.player)
            if xp > 0:
                if self.player.add_xp(xp):
                    self.state = "upgrading"
                    self.generate_upgrades()
                    self.add_notification(f"LEVEL {self.player.level}!",
                                         C_XP)
                    self.particles.emit(
                        self.player.x, self.player.y, 30, C_XP,
                        speed_range=(2, 6), life_range=(20, 40), size=4)
        self.crystals = [c for c in self.crystals if c.active]

        # Particles
        self.particles.update()

        # Damage numbers
        for dn in self.damage_numbers:
            dn[1] -= 0.5
            dn[3] -= 1
        self.damage_numbers = [d for d in self.damage_numbers if d[3] > 0]

        # Notifications
        for n in self.notifications:
            n[1] -= 1
        self.notifications = [n for n in self.notifications if n[1] > 0]

        # Wave spawning
        if self.wave_spawning:
            self.spawn_timer -= 1
            if self.spawn_timer <= 0 and self.spawn_queue:
                etype, tier = self.spawn_queue.pop(0)
                self._spawn_one(etype, tier)
                self.spawn_timer = 15
            if not self.spawn_queue:
                self.wave_spawning = False

        if not self.wave_spawning and not self.enemies:
            self.wave_clear_timer += 1
            if self.wave_clear_timer > 90:
                self.wave_clear_timer = 0
                self.spawn_wave()

        # Grid pulse
        self.grid_pulse += 0.02

        # Death
        if self.player.hp <= 0:
            self.state = "gameover"
            self.add_shake(15)
            self.particles.emit(
                self.player.x, self.player.y, 50, C_PLAYER,
                speed_range=(3, 10), life_range=(20, 60), size=5)

    # ═══════════════════════════════════════════════════════
    #  Drawing
    # ═══════════════════════════════════════════════════════
    def _draw_background(self, surface):
        surface.fill(C_BG)

        # Pulsing grid
        pulse = math.sin(self.grid_pulse) * 0.3 + 0.7
        g = (int(C_GRID[0] * pulse),
             int(C_GRID[1] * pulse),
             int(C_GRID[2] * pulse))
        gs = 80
        ox = int(self.cam_x + self.shake_x) % gs
        oy = int(self.cam_y + self.shake_y) % gs
        for x in range(-ox, WIDTH + gs, gs):
            pygame.draw.line(surface, g, (x, 0), (x, HEIGHT))
        for y in range(-oy, HEIGHT + gs, gs):
            pygame.draw.line(surface, g, (0, y), (WIDTH, y))

        # Stars (parallax)
        for sx, sy, br in self.bg_stars:
            px = int(sx - self.cam_x * 0.3 + self.shake_x) % WIDTH
            py = int(sy - self.cam_y * 0.3 + self.shake_y) % HEIGHT
            b = int(br * 100)
            pygame.draw.circle(surface, (b, b, b + 20), (px, py), 1)

        # Arena border
        bcol = (60, 25, 80)
        al = int(-ARENA - self.cam_x - self.shake_x)
        ar = int( ARENA - self.cam_x - self.shake_x)
        at = int(-ARENA - self.cam_y - self.shake_y)
        ab = int( ARENA - self.cam_y - self.shake_y)
        top_c = max(0, at); bot_c = min(HEIGHT, ab)
        lft_c = max(0, al); rgt_c = min(WIDTH, ar)
        if al > 0:
            pygame.draw.line(surface, bcol,
                             (al, top_c), (al, bot_c), 3)
        if ar < WIDTH:
            pygame.draw.line(surface, bcol,
                             (ar, top_c), (ar, bot_c), 3)
        if at > 0:
            pygame.draw.line(surface, bcol,
                             (lft_c, at), (rgt_c, at), 3)
        if ab < HEIGHT:
            pygame.draw.line(surface, bcol,
                             (lft_c, ab), (rgt_c, ab), 3)

    def _draw_hud(self, surface):
        p = self.player

        # ── HP bar ──
        bx, by = 20, HEIGHT - 50
        bw, bh = 250, 18
        pygame.draw.rect(surface, (30, 10, 15),
                         (bx, by, bw, bh), border_radius=4)
        hp_fill = int(bw * max(0, p.hp) / p.max_hp)
        if hp_fill > 0:
            pygame.draw.rect(surface, C_HEALTH,
                             (bx, by, hp_fill, bh), border_radius=4)
        pygame.draw.rect(surface, (200, 60, 80),
                         (bx, by, bw, bh), 2, border_radius=4)
        surface.blit(
            self.font_small.render(
                f"HP {max(0, p.hp)}/{p.max_hp}", True, C_WHITE),
            (bx + 5, by + 1))

        # ── Energy bar ──
        by2 = HEIGHT - 28
        pygame.draw.rect(surface, (10, 15, 30),
                         (bx, by2, bw, 12), border_radius=3)
        en_fill = int(bw * p.energy / p.max_energy)
        if en_fill > 0:
            pygame.draw.rect(surface, C_ENERGY,
                             (bx, by2, en_fill, 12), border_radius=3)
        pygame.draw.rect(surface, (60, 120, 200),
                         (bx, by2, bw, 12), 1, border_radius=3)

        # ── Score ──
        st = self.font_large.render(f"{p.score:,}", True, C_WHITE)
        surface.blit(st, (WIDTH // 2 - st.get_width() // 2, 15))

        # ── Combo ──
        if p.combo > 1:
            ct = self.font_med.render(f"x{p.combo} COMBO", True, C_COMBO)
            surface.blit(ct, (WIDTH // 2 - ct.get_width() // 2, 52))
            cpct = p.combo_timer / p.combo_max_timer
            cbw = 100
            pygame.draw.rect(surface, (50, 40, 10),
                             (WIDTH // 2 - cbw // 2, 75, cbw, 4),
                             border_radius=2)
            pygame.draw.rect(surface, C_COMBO,
                             (WIDTH // 2 - cbw // 2, 75,
                              int(cbw * cpct), 4),
                             border_radius=2)

        # ── Wave ──
        wt = self.font_med.render(f"Wave {self.wave}", True, (150, 150, 180))
        surface.blit(wt, (WIDTH - wt.get_width() - 20, 15))

        # ── Weapon indicator ──
        w = p.weapons[p.current_weapon]
        surface.blit(
            self.font_small.render(
                f"[{p.current_weapon + 1}] {w['name']}", True, w["color"]),
            (20, HEIGHT - 70))

        # ── Level / XP ──
        surface.blit(
            self.font_small.render(f"LV {p.level}", True, C_XP),
            (WIDTH - 80, HEIGHT - 50))
        xbx = WIDTH - 160
        xbw = 140
        pygame.draw.rect(surface, (15, 30, 20),
                         (xbx, HEIGHT - 28, xbw, 10), border_radius=3)
        xf = int(xbw * p.xp / p.xp_to_next)
        if xf > 0:
            pygame.draw.rect(surface, C_XP,
                             (xbx, HEIGHT - 28, xf, 10), border_radius=3)
        pygame.draw.rect(surface, (60, 150, 80),
                         (xbx, HEIGHT - 28, xbw, 10), 1, border_radius=3)

        # ── Dash cooldown ──
        if p.dash_cooldown > 0:
            dp = 1 - p.dash_cooldown / DASH_COOLDOWN
            surface.blit(
                self.font_small.render("DASH", True, (80, 80, 100)),
                (290, HEIGHT - 45))
            pygame.draw.rect(surface, (30, 30, 40),
                             (290, HEIGHT - 28, 60, 8), border_radius=2)
            pygame.draw.rect(surface, C_PLAYER,
                             (290, HEIGHT - 28, int(60 * dp), 8),
                             border_radius=2)
        else:
            surface.blit(
                self.font_small.render("DASH [RDY]", True, C_PLAYER),
                (290, HEIGHT - 45))

        # ── Off-screen enemy indicators ──
        cam_cx = self.cam_x + self.shake_x
        cam_cy = self.cam_y + self.shake_y
        margin = 30
        for e in self.enemies:
            esx = e.x - cam_cx
            esy = e.y - cam_cy
            if 0 <= esx <= WIDTH and 0 <= esy <= HEIGHT:
                continue  # on screen
            # Clamp to screen edge
            cx = clamp(esx, margin, WIDTH - margin)
            cy = clamp(esy, margin, HEIGHT - margin)
            angle = math.atan2(esy - HEIGHT / 2, esx - WIDTH / 2)
            # Small triangle indicator
            size = 6
            pts = [
                (cx + math.cos(angle) * size,
                 cy + math.sin(angle) * size),
                (cx + math.cos(angle + 2.3) * size * 0.6,
                 cy + math.sin(angle + 2.3) * size * 0.6),
                (cx + math.cos(angle - 2.3) * size * 0.6,
                 cy + math.sin(angle - 2.3) * size * 0.6),
            ]
            pygame.draw.polygon(surface, e.color, pts)

        # ── Floating damage numbers ──
        for dn in self.damage_numbers:
            alpha_frac = dn[3] / 30
            if alpha_frac > 0:
                txt = self.font_small.render(dn[2], True, dn[4])
                surface.blit(txt,
                             (int(dn[0] - cam_cx - txt.get_width() / 2),
                              int(dn[1] - cam_cy)))

        # ── Notifications ──
        for i, n in enumerate(self.notifications):
            txt = self.font_large.render(n[0], True, n[2])
            y_off = HEIGHT // 3 + i * 45
            surface.blit(txt,
                         (WIDTH // 2 - txt.get_width() // 2, y_off))

        # ── Custom crosshair ──
        mx, my = pygame.mouse.get_pos()
        pygame.draw.circle(surface, C_PLAYER, (mx, my), 8, 1)
        pygame.draw.circle(surface, C_PLAYER, (mx, my), 2)
        for dx, dy in [(-12, 0), (12, 0), (0, -12), (0, 12)]:
            ndx, ndy = dx * 5 // 12, dy * 5 // 12
            pygame.draw.line(surface, C_PLAYER,
                             (mx + ndx, my + ndy),
                             (mx + dx, my + dy), 1)

    def _draw_upgrade_screen(self, surface):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        surface.blit(overlay, (0, 0))

        title = self.font_large.render(
            "LEVEL UP!  Choose an upgrade:", True, C_XP)
        surface.blit(title,
                     (WIDTH // 2 - title.get_width() // 2, 150))

        mx, my = pygame.mouse.get_pos()
        for i, opt in enumerate(self.upgrade_options):
            x = WIDTH // 2 - 180
            y = 230 + i * 90
            w, h = 360, 75
            hovered = x <= mx <= x + w and y <= my <= y + h
            bg = (30, 50, 40) if hovered else (20, 25, 35)
            bd = C_XP if hovered else (50, 60, 80)
            pygame.draw.rect(surface, bg, (x, y, w, h), border_radius=8)
            pygame.draw.rect(surface, bd, (x, y, w, h), 2, border_radius=8)
            surface.blit(self.font_small.render(
                f"[{i + 1}]", True, C_XP), (x + 15, y + 15))
            surface.blit(self.font_med.render(
                opt["name"], True,
                C_WHITE if hovered else (180, 180, 200)),
                (x + 50, y + 12))
            surface.blit(self.font_small.render(
                opt["desc"], True, (120, 120, 140)),
                (x + 50, y + 42))

    def _draw_menu(self, surface):
        surface.fill(C_BG)
        t = pygame.time.get_ticks() / 1000.0

        # Floating dots
        for i in range(60):
            px = int((math.sin(t * 0.3 + i * 0.7) * 0.5 + 0.5) * WIDTH)
            py = int((math.cos(t * 0.2 + i * 1.1) * 0.5 + 0.5) * HEIGHT)
            a = int(30 + math.sin(t * 0.5 + i) * 20)
            pygame.draw.circle(surface, (a, a, a + 10), (px, py),
                               int(2 + math.sin(t + i) * 1.5))

        # Title
        shadow = self.font_title.render("VOID DRIFTER", True, (0, 80, 70))
        title  = self.font_title.render("VOID DRIFTER", True, C_PLAYER)
        surface.blit(shadow,
                     (WIDTH // 2 - title.get_width() // 2 + 3, 153))
        surface.blit(title,
                     (WIDTH // 2 - title.get_width() // 2, 150))

        # Subtitle
        pulse = int(180 + math.sin(t * 2) * 75)
        sub = self.font_med.render(
            "A Neon Arena Survival Game", True,
            (0, pulse, int(pulse * 0.7)))
        surface.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 240))

        # Controls list
        lines = [
            "WASD / Arrows ─ Move",
            "Mouse ─ Aim & Shoot (Left Click)",
            "Space ─ Dash",
            "1 / 2 / 3 ─ Switch Weapons",
        ]
        for i, l in enumerate(lines):
            txt = self.font_small.render(l, True, (120, 120, 150))
            surface.blit(txt,
                         (WIDTH // 2 - txt.get_width() // 2,
                          320 + i * 28))

        # Prompt
        if int(t * 2) % 2:
            start = self.font_med.render(
                "[ Press ENTER or CLICK to Start ]", True, C_COMBO)
            surface.blit(start,
                         (WIDTH // 2 - start.get_width() // 2, 480))

    def _draw_gameover(self, surface):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        title = self.font_title.render("GAME OVER", True, C_HEALTH)
        surface.blit(title,
                     (WIDTH // 2 - title.get_width() // 2, 180))
        score = self.font_large.render(
            f"Score: {self.player.score:,}", True, C_WHITE)
        surface.blit(score,
                     (WIDTH // 2 - score.get_width() // 2, 290))
        wave = self.font_med.render(
            f"Reached Wave {self.wave}", True, (150, 150, 180))
        surface.blit(wave,
                     (WIDTH // 2 - wave.get_width() // 2, 340))
        lvl = self.font_med.render(
            f"Level {self.player.level}", True, C_XP)
        surface.blit(lvl, (WIDTH // 2 - lvl.get_width() // 2, 380))

        t = pygame.time.get_ticks() / 1000.0
        if int(t * 2) % 2:
            r = self.font_med.render(
                "[ Press R to Restart ]", True, C_COMBO)
            surface.blit(r, (WIDTH // 2 - r.get_width() // 2, 460))

    # ═══════════════════════════════════════════════════════
    #  Main loop
    # ═══════════════════════════════════════════════════════
    def run(self):
        pygame.mouse.set_visible(False)
        running = True

        while running:
            self.clock.tick(FPS)

            # ── Events ──
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

                    if self.state == "menu":
                        if event.key == pygame.K_RETURN:
                            self.state = "playing"
                            self.spawn_wave()

                    elif self.state == "playing":
                        if event.key == pygame.K_SPACE:
                            self.player.try_dash()
                        elif event.key == pygame.K_1:
                            self.player.current_weapon = 0
                        elif event.key == pygame.K_2:
                            self.player.current_weapon = 1
                        elif event.key == pygame.K_3:
                            self.player.current_weapon = 2

                    elif self.state == "upgrading":
                        if event.key in (pygame.K_1, pygame.K_2,
                                         pygame.K_3):
                            self.apply_upgrade(event.key - pygame.K_1)

                    elif self.state == "gameover":
                        if event.key == pygame.K_r:
                            self.reset()
                            self.state = "playing"
                            self.spawn_wave()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.state == "menu":
                            self.state = "playing"
                            self.spawn_wave()
                        elif self.state == "upgrading":
                            mx, my = event.pos
                            for i in range(len(self.upgrade_options)):
                                ux = WIDTH // 2 - 180
                                uy = 230 + i * 90
                                if (ux <= mx <= ux + 360
                                        and uy <= my <= uy + 75):
                                    self.apply_upgrade(i)
                                    break

            # ── Update ──
            if self.state == "playing":
                self.update_playing()
            elif self.state == "gameover":
                self.particles.update()

            # ── Draw ──
            surf = self.screen
            if self.state == "menu":
                self._draw_menu(surf)
            else:
                cx = self.cam_x + self.shake_x
                cy = self.cam_y + self.shake_y
                self._draw_background(surf)

                for c in self.crystals:
                    c.draw(surf, cx, cy)
                for b in self.bullets:
                    b.draw(surf, cx, cy)
                for b in self.enemy_bullets:
                    b.draw(surf, cx, cy)
                for e in self.enemies:
                    e.draw(surf, cx, cy)
                if self.player.hp > 0:
                    self.player.draw(surf, cx, cy)
                self.particles.draw(surf, cx, cy)

                self._draw_hud(surf)

                if self.state == "upgrading":
                    self._draw_upgrade_screen(surf)
                elif self.state == "gameover":
                    self._draw_gameover(surf)

            # Show / hide system cursor based on state
            pygame.mouse.set_visible(
                self.state in ("menu", "upgrading", "gameover"))

            pygame.display.flip()

        pygame.quit()
        sys.exit()


# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    Game().run()
