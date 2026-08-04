import js
import json

BASE = "https://chatcpu.local"
CACHE = "CHATCPU-MINIOS"

WIDTH = 20
HEIGHT = 10

IO_KEYBOARD = 0x01

KEY_UP = 1
KEY_DOWN = 2
KEY_LEFT = 3
KEY_RIGHT = 4


async def cache_open():
    return await js.caches.open(CACHE)


async def read_file(path):

    cache = await cache_open()

    r = await cache.match(
        js.Request.new(BASE + path)
    )

    if r is None:
        return ""

    return await r.text()


async def write_file(path, text):

    cache = await cache_open()

    await cache.put(
        js.Request.new(BASE + path),
        js.Response.new(text)
    )


# ============================================================
# LOAD SAVE
# ============================================================

save_text = await read_file(
    "/minios/snake.save"
)

if not save_text:
    raise RuntimeError(
        "snake.save saknas"
    )

state = json.loads(save_text)

snake = state["segments"]
food = state["food"]
direction = state["direction"]
score = state["score"]
alive = state["alive"]


# ============================================================
# INPUT
# ============================================================

input_text = (
    await read_file(
        "/minios/shell/input.txt"
    )
).strip().upper()


keys = {
    "UP": KEY_UP,
    "DOWN": KEY_DOWN,
    "LEFT": KEY_LEFT,
    "RIGHT": KEY_RIGHT
}

if input_text in keys:

    new_direction = keys[input_text]

    # Prevent immediate 180 degree turns
    opposite = {
        KEY_UP: KEY_DOWN,
        KEY_DOWN: KEY_UP,
        KEY_LEFT: KEY_RIGHT,
        KEY_RIGHT: KEY_LEFT
    }

    if new_direction != opposite[direction]:
        direction = new_direction


# ============================================================
# MOVEMENT
# ============================================================

vectors = {
    KEY_UP: (0, -1),
    KEY_DOWN: (0, 1),
    KEY_LEFT: (-1, 0),
    KEY_RIGHT: (1, 0)
}

dx, dy = vectors[direction]

hx, hy = snake[0]

new_head = [
    hx + dx,
    hy + dy
]


# Wall collision

if (
    new_head[0] < 0
    or new_head[0] >= WIDTH
    or new_head[1] < 0
    or new_head[1] >= HEIGHT
):

    alive = False


# Self collision

elif new_head in snake:

    alive = False


# ============================================================
# MOVE
# ============================================================

if alive:

    snake.insert(
        0,
        new_head
    )

    # Food

    if new_head == food:

        score += 1

        # Temporary deterministic food
        food = [
            (food[0] + 7) % WIDTH,
            (food[1] + 3) % HEIGHT
        ]

    else:

        snake.pop()


# ============================================================
# SAVE
# ============================================================

state = {
    "length": len(snake),
    "segments": snake,
    "food": food,
    "direction": direction,
    "alive": alive,
    "score": score
}

await write_file(
    "/minios/snake.save",
    json.dumps(state)
)


# ============================================================
# DRAW
# ============================================================

print("=== ChatCPU Snake v0.7 ===")
print()

print(
    "Input:",
    input_text or "(none)"
)

print(
    "Direction:",
    direction
)

print(
    "Score:",
    score
)

print()

print("+" + "-" * WIDTH + "+")

for y in range(HEIGHT):

    row = ""

    for x in range(WIDTH):

        pos = [x, y]

        if pos == snake[0]:

            row += "█"

        elif pos in snake:

            row += "▓"

        elif pos == food:

            row += "●"

        else:

            row += " "

    print("|" + row + "|")

print("+" + "-" * WIDTH + "+")

print()

print(
    "Head:",
    snake[0]
)

print(
    "Length:",
    len(snake)
)

print(
    "Score:",
    score
)

if alive:
    print("CPU TICK OK")
else:
    print("GAME OVER")

print("STATE SAVED")
