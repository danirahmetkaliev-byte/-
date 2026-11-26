import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import websockets
except ImportError:
    raise SystemExit("Установи библиотеку: pip install websockets")

# =====================================
# WIFI SURVIVAL
# ONE FILE EDITION
# =====================================

HOST = "0.0.0.0"
WS_PORT = 5555
HTTP_PORT = 8000

MAX_PLAYERS = 3
MAP_W = 1600
MAP_H = 1000

players = {}
connections = {}

SPAWNS = [(400, 300), (500, 300), (600, 300)]


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# =====================================
# HTML + JS CLIENT
# =====================================

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<meta name="mobile-web-app-capable" content="yes">
<title>WIFI SURVIVAL</title>
<style>
:root { --ink:#f1ead8; --chip:rgba(24,34,36,.74); --amber:#e2b04a; }
html, body { margin:0; height:100%; background:#000; overflow:hidden; touch-action:none;
  user-select:none; -webkit-user-select:none; color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
#stage { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; }
#box { position:relative; width:min(100vw, calc(100vh * 16 / 9)); height:min(100vh, calc(100vw * 9 / 16));
  width:min(100vw, calc(100dvh * 16 / 9)); height:min(100dvh, calc(100vw * 9 / 16)); }
canvas { width:100%; height:100%; display:block; }
.chip { position:absolute; top:10px; padding:8px 14px; border-radius:999px; border:0;
  background:var(--chip); color:var(--ink); font:inherit; font-size:14px; }
button.chip { cursor:pointer; }
#status { left:10px; }
#cam { right:78px; }
#fs { right:10px; }
#menu { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:12px; background:rgba(29,43,46,.94); text-align:center; padding:16px; }
#menu[hidden] { display:none; }
#menu h1 { margin:0; font-size:clamp(24px,6vh,44px); letter-spacing:.04em; }
#menu input { width:min(320px,80%); padding:12px 14px; font-size:18px; border-radius:10px;
  border:2px solid #4c6468; background:#16211f; color:var(--ink); text-align:center; }
#menu input:focus { outline:3px solid var(--amber); outline-offset:2px; }
#go { padding:12px 36px; font-size:18px; font-weight:700; border:0; border-radius:10px;
  background:var(--amber); color:#2a2208; cursor:pointer; }
#msg { min-height:1.3em; font-size:15px; }
#hint { font-size:13px; opacity:.7; max-width:420px; }
</style>
</head>
<body>
<div id="stage">
  <div id="box">
    <canvas id="c"></canvas>
    <div id="status" class="chip">Нет связи</div>
    <button id="cam" class="chip">Камера: я</button>
    <button id="fs" class="chip" aria-label="Полный экран">Экран</button>
    <div id="menu">
      <h1>WIFI SURVIVAL</h1>
      <input id="addr" inputmode="url" autocapitalize="off" autocomplete="off" placeholder="IP сервера, например 192.168.43.1">
      <button id="go">Играть</button>
      <div id="msg"></div>
      <div id="hint">Движение: палец по левой половине экрана или WASD. Камера: кнопка сверху или клавиша C.</div>
    </div>
  </div>
</div>

<script>
const W = 1280, H = 720;            // размер холста (16:9)
const MAP_W = 1600, MAP_H = 1000;   // как на сервере
const SPEED = 240, WS_PORT = 5555, MAX_PLAYERS = 3;
const COLORS = { 1: '#e2b04a', 2: '#4aa3c7', 3: '#c75b7a' };

const $ = id => document.getElementById(id);
const cv = $('c'), ctx = cv.getContext('2d');
cv.width = W; cv.height = H;

let ws = null, myId = null, lastErr = '', count = 0;
const me = { x: 400, y: 300, ready: false };
let others = {};
let camKey = 'self';                // 'self' | id друга | 'map'
const cam = { x: 400, y: 300, z: 1 };
const keys = {};
let joy = null;

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// ---------- деревья (одинаковые у всех, только для вида) ----------
function rng(seed) {
  return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
const rand = rng(7), trees = [];
while (trees.length < 45) {
  const x = 40 + rand() * (MAP_W - 80), y = 40 + rand() * (MAP_H - 80);
  if (Math.hypot(x - 400, y - 300) > 160) trees.push({ x, y, r: 24 + rand() * 14 });
}

// ---------- подключение ----------
$('addr').value = location.hostname || '';

function setMsg(t) { $('msg').textContent = t; }

function connect() {
  const host = $('addr').value.trim() || location.hostname;
  if (!host) { setMsg('Введи IP сервера'); return; }
  lastErr = '';
  setMsg('Подключаемся...');
  let sock;
  try { sock = new WebSocket('ws://' + host + ':' + WS_PORT); }
  catch (e) { setMsg('Неверный адрес'); return; }
  ws = sock;
  sock.onmessage = ev => {
    let d; try { d = JSON.parse(ev.data); } catch (e) { return; }
    if (d.error) { lastErr = d.error; return; }
    if (d.id) { myId = String(d.id); $('menu').hidden = true; return; }
    if (d.players) applyState(d.players);
  };
  sock.onclose = () => {
    if (ws !== sock) return;
    ws = null; myId = null; others = {}; me.ready = false; camKey = 'self';
    $('menu').hidden = false;
    setMsg(lastErr || 'Нет соединения с сервером. Проверь IP и Wi-Fi.');
  };
}
$('go').onclick = connect;
$('addr').addEventListener('keydown', e => { if (e.key === 'Enter') connect(); });

function applyState(p) {
  count = Object.keys(p).length;
  for (const id in p) {
    const s = p[id];
    if (id === myId) {
      if (!me.ready) { me.x = s.x; me.y = s.y; cam.x = s.x; cam.y = s.y; me.ready = true; }
      continue;
    }
    const o = others[id];
    if (o) { o.tx = s.x; o.ty = s.y; }
    else others[id] = { x: s.x, y: s.y, tx: s.x, ty: s.y };
  }
  for (const id in others) if (!(id in p)) delete others[id];
}

// отправляем свою позицию 20 раз в секунду
setInterval(() => {
  if (ws && ws.readyState === 1 && me.ready)
    ws.send(JSON.stringify({ x: Math.round(me.x), y: Math.round(me.y) }));
}, 50);

// ---------- управление ----------
addEventListener('keydown', e => {
  keys[e.code] = true;
  if (e.code === 'KeyC') nextCam();
});
addEventListener('keyup', e => { keys[e.code] = false; });

function toCanvas(e) {
  const r = cv.getBoundingClientRect();
  return { x: (e.clientX - r.left) * W / r.width, y: (e.clientY - r.top) * H / r.height };
}
const JOY_R = 70;
cv.addEventListener('pointerdown', e => {
  const p = toCanvas(e);
  if (p.x < W / 2 && !joy) {
    joy = { id: e.pointerId, ox: p.x, oy: p.y, dx: 0, dy: 0, vx: 0, vy: 0 };
    cv.setPointerCapture(e.pointerId);
  }
});
cv.addEventListener('pointermove', e => {
  if (!joy || e.pointerId !== joy.id) return;
  const p = toCanvas(e);
  let dx = p.x - joy.ox, dy = p.y - joy.oy;
  const d = Math.hypot(dx, dy);
  if (d > JOY_R) { dx *= JOY_R / d; dy *= JOY_R / d; }
  joy.dx = dx; joy.dy = dy;
  const vx = dx / JOY_R, vy = dy / JOY_R;
  const dead = Math.hypot(vx, vy) < 0.12;
  joy.vx = dead ? 0 : vx; joy.vy = dead ? 0 : vy;
});
const endJoy = e => { if (joy && e.pointerId === joy.id) joy = null; };
cv.addEventListener('pointerup', endJoy);
cv.addEventListener('pointercancel', endJoy);
addEventListener('contextmenu', e => e.preventDefault());

// ---------- камера ----------
function nextCam() {
  const views = ['self', ...Object.keys(others).sort(), 'map'];
  camKey = views[(views.indexOf(camKey) + 1) % views.length];
}
$('cam').onclick = nextCam;

$('fs').onclick = async () => {
  try {
    if (document.fullscreenElement) { await document.exitFullscreen(); return; }
    await document.documentElement.requestFullscreen();
    if (screen.orientation && screen.orientation.lock) await screen.orientation.lock('landscape');
  } catch (e) { /* не все браузеры разрешают */ }
};

function camLabel() {
  if (camKey === 'map') return 'Камера: карта';
  if (camKey === 'self') return 'Камера: я';
  return 'Камера: игрок ' + camKey;
}

// ---------- обновление ----------
function update(dt) {
  if (ws && me.ready) {
    let vx = 0, vy = 0;
    if (keys.KeyA || keys.ArrowLeft) vx -= 1;
    if (keys.KeyD || keys.ArrowRight) vx += 1;
    if (keys.KeyW || keys.ArrowUp) vy -= 1;
    if (keys.KeyS || keys.ArrowDown) vy += 1;
    if (joy) { vx += joy.vx; vy += joy.vy; }
    const len = Math.hypot(vx, vy);
    if (len > 1) { vx /= len; vy /= len; }
    me.x = clamp(me.x + vx * SPEED * dt, 0, MAP_W);
    me.y = clamp(me.y + vy * SPEED * dt, 0, MAP_H);
  }

  const k = 1 - Math.exp(-14 * dt);
  for (const id in others) {
    const o = others[id];
    o.x += (o.tx - o.x) * k; o.y += (o.ty - o.y) * k;
  }

  if (camKey !== 'self' && camKey !== 'map' && !others[camKey]) camKey = 'self';
  let tx, ty, tz;
  if (camKey === 'map') {
    tx = MAP_W / 2; ty = MAP_H / 2; tz = Math.min(W / MAP_W, H / MAP_H);
  } else {
    const s = camKey === 'self' ? me : others[camKey];
    tz = 1;
    tx = clamp(s.x, W / 2, MAP_W - W / 2);
    ty = clamp(s.y, H / 2, MAP_H - H / 2);
  }
  const kc = 1 - Math.exp(-8 * dt);
  cam.x += (tx - cam.x) * kc; cam.y += (ty - cam.y) * kc; cam.z += (tz - cam.z) * kc;

  const label = camLabel();
  if ($('cam').textContent !== label) $('cam').textContent = label;
  const st = ws && myId ? 'Игроки: ' + count + '/' + MAX_PLAYERS : 'Нет связи';
  if ($('status').textContent !== st) $('status').textContent = st;
}

// ---------- рисование ----------
function drawPlayer(id, x, y, self) {
  ctx.fillStyle = 'rgba(0,0,0,.22)';
  ctx.beginPath(); ctx.ellipse(x, y + 18, 20, 8, 0, 0, 7); ctx.fill();
  ctx.fillStyle = COLORS[id] || '#cccccc';
  ctx.beginPath(); ctx.arc(x, y, 22, 0, 7); ctx.fill();
  ctx.lineWidth = self ? 4 : 2;
  ctx.strokeStyle = self ? '#f1ead8' : 'rgba(0,0,0,.4)';
  ctx.stroke();
  ctx.fillStyle = '#f1ead8';
  ctx.font = 'bold 18px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(self ? 'Ты' : 'Игрок ' + id, x, y - 32);
}

function draw() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#2c4a52';                       // вода за краем карты
  ctx.fillRect(0, 0, W, H);

  ctx.setTransform(cam.z, 0, 0, cam.z, W / 2 - cam.x * cam.z, H / 2 - cam.y * cam.z);
  ctx.fillStyle = '#8a8f5c';
  ctx.fillRect(0, 0, MAP_W, MAP_H);
  ctx.fillStyle = '#838854';
  for (let gx = 0; gx < MAP_W; gx += 100)
    for (let gy = 0; gy < MAP_H; gy += 100)
      if ((gx + gy) / 100 % 2 === 0) ctx.fillRect(gx, gy, 100, 100);

  for (const t of trees) {
    ctx.fillStyle = '#5a4630'; ctx.fillRect(t.x - 5, t.y, 10, t.r * 0.8);
    ctx.fillStyle = '#3d5a3a'; ctx.beginPath(); ctx.arc(t.x, t.y, t.r, 0, 7); ctx.fill();
    ctx.fillStyle = '#4b6e45'; ctx.beginPath(); ctx.arc(t.x - t.r * 0.25, t.y - t.r * 0.25, t.r * 0.5, 0, 7); ctx.fill();
  }

  for (const id in others) drawPlayer(id, others[id].x, others[id].y, false);
  if (myId && me.ready) drawPlayer(myId, me.x, me.y, true);

  ctx.setTransform(1, 0, 0, 1, 0, 0);               // джойстик в экранных координатах
  if (joy) {
    ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(241,234,216,.45)';
    ctx.beginPath(); ctx.arc(joy.ox, joy.oy, JOY_R, 0, 7); ctx.stroke();
    ctx.fillStyle = 'rgba(241,234,216,.55)';
    ctx.beginPath(); ctx.arc(joy.ox + joy.dx, joy.oy + joy.dy, 28, 0, 7); ctx.fill();
  }
}

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  update(dt);
  draw();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
</body>
</html>
"""


# =====================================
# HTTP SERVER
# =====================================

class GameHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return

        content = HTML.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


def start_http():
    server = ThreadingHTTPServer(
        (HOST, HTTP_PORT),
        GameHandler
    )

    threading.Thread(
        target=server.serve_forever,
        daemon=True
    ).start()


# =====================================
# WEBSOCKET SERVER
# =====================================

def free_slot():
    for i in range(1, MAX_PLAYERS + 1):
        if str(i) not in players:
            return str(i)
    return None


async def broadcast():
    if not connections:
        return

    message = json.dumps({
        "players": players
    })

    await asyncio.gather(
        *[
            ws.send(message)
            for ws in list(connections.values())
        ],
        return_exceptions=True
    )


async def handler(ws):
    pid = free_slot()

    if pid is None:
        await ws.send(json.dumps({
            "error": "Сервер заполнен!"
        }))
        await ws.close()
        return

    slot = int(pid) - 1
    x, y = SPAWNS[slot]

    players[pid] = {"x": x, "y": y}
    connections[pid] = ws

    print("Подключился игрок:", pid)

    try:
        await ws.send(json.dumps({"id": pid}))

        async for message in ws:
            try:
                data = json.loads(message)

                x = int(data["x"])
                y = int(data["y"])

                players[pid]["x"] = max(0, min(MAP_W, x))
                players[pid]["y"] = max(0, min(MAP_H, y))

            except (ValueError, TypeError, KeyError):
                continue

    except websockets.ConnectionClosed:
        pass

    finally:
        players.pop(pid, None)
        connections.pop(pid, None)

        print("Отключился игрок:", pid)
        await broadcast()


async def broadcast_loop():
    while True:
        await broadcast()
        await asyncio.sleep(1 / 20)


# =====================================
# START GAME
# =====================================

async def main():
    start_http()

    ip = get_ip()

    print("=" * 40)
    print("         WIFI SURVIVAL")
    print("=" * 40)
    print("Сервер IP:", ip)
    print("Игра: http://" + ip + ":" + str(HTTP_PORT))
    print("WebSocket:", WS_PORT)
    print("Максимум игроков:", MAX_PLAYERS)
    print("=" * 40)

    async with websockets.serve(
        handler,
        HOST,
        WS_PORT,
        max_size=1024
    ):
        await broadcast_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Сервер остановлен")