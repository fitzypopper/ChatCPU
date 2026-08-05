import js
import io
import ast
import json
import shlex
import random
import gzip
import base64
import contextlib
from collections import deque

# ============================================================
# ChatCPU 2.1
# MiniCPU + RAM + ROM + I/O + SCREEN + INPUT + DISK
# ============================================================

RAM_SIZE = 64 * 1024
ROM_SIZE = 64 * 1024

SCREEN_W = 32
SCREEN_H = 16

PORT_KEY       = 0x00
PORT_KEY_STATE = 0x01
PORT_SCREEN    = 0x10
PORT_RANDOM    = 0x20

CACHE_NAME = "ChatCPU-OS-V21"
BASE = "https://ChatCPU.local"


# ============================================================
# PERSISTENT FILESYSTEM
# ============================================================

async def disk():
    return await js.caches.open(CACHE_NAME)


def req(path):
    if not path.startswith("/"):
        path = "/" + path
    return js.Request.new(BASE + path)


async def write_file(path, data):
    d = await disk()
    await d.put(req(path), js.Response.new(str(data)))


async def read_file(path):
    d = await disk()
    r = await d.match(req(path))
    if r is None:
        raise FileNotFoundError(path)
    return await r.text()


async def exists(path):
    d = await disk()
    return (await d.match(req(path))) is not None


async def delete_file(path):
    d = await disk()
    await d.delete(req(path))


async def all_files():
    d = await disk()
    result = []
    for r in await d.keys():
        url = str(r.url)
        # The browser normalizes Request URLs (host is lowercased), so
        # compare case-insensitively against BASE.
        if url.lower().startswith(BASE.lower()):
            result.append(url[len(BASE):])
    return sorted(result)


async def list_dir(path="/"):
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/")
    prefix = path + "/" if path else "/"
    result = set()
    for f in await all_files():
        if not f.startswith(prefix):
            continue
        rest = f[len(prefix):]
        if rest:
            result.add(rest.split("/", 1)[0])
    return sorted(result)


CWD = "/"
CWD_FILE = "/minios/.cwd"


def resolve(path):
    """Resolve a path (relative or absolute) against CWD, normalizing
    '.', '..', and duplicate slashes."""
    if not path.startswith("/"):
        path = CWD + "/" + path
    parts = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/" + "/".join(parts)


async def is_dir(path):
    if path == "/":
        return True
    prefix = path + "/"
    return any(f.startswith(prefix) for f in await all_files())


# ============================================================
# HARDWARE
# ============================================================

class Hardware:

    def __init__(self):
        self.cpu = None
        self.reset()

    def reset(self):
        self.keys = deque()
        self.screen = [[" "] * SCREEN_W for _ in range(SCREEN_H)]

    def attach(self, cpu):
        self.cpu = cpu

    def key(self, value):
        if value is None:
            return
        value = str(value)
        if not value:
            return
        self.keys.append(ord(value[0]))

    def keycode(self, value):
        self.keys.append(int(value) & 0xFF)

    def read_port(self, port):
        port &= 0xFF
        if port == PORT_KEY:
            if self.keys:
                return self.keys.popleft()
            return 0
        if port == PORT_KEY_STATE:
            return int(bool(self.keys))
        if port == PORT_RANDOM:
            return random.randrange(0, 256)
        return 0

    def write_port(self, port, value):
        port &= 0xFF
        value &= 0xFFFF
        if port == PORT_SCREEN:
            if self.cpu is None:
                return
            x = self.cpu.B & 0xFFFF
            y = self.cpu.C & 0xFFFF
            if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
                self.screen[y][x] = chr(self.cpu.A & 0xFF)

    def clear_screen(self):
        self.screen = [[" "] * SCREEN_W for _ in range(SCREEN_H)]

    def render(self):
        return "\n".join("".join(row) for row in self.screen)


hardware = Hardware()


# ============================================================
# CPU
# ============================================================

class MiniCPU:

    def __init__(self):
        self.reset()
        hardware.attach(self)

    def reset(self):
        self.ram = bytearray(RAM_SIZE)
        self.rom = bytearray(ROM_SIZE)
        self.A = 0
        self.B = 0
        self.C = 0
        self.D = 0
        self.PC = 0
        self.SP = 0xFFFF
        self.Z = 0
        self.CF = 0
        self.N = 0
        self.cycles = 0
        self.running = False
        self.output_buffer = []

    def fetch8(self):
        value = self.rom[self.PC]
        self.PC = (self.PC + 1) & 0xFFFF
        return value

    def fetch16(self):
        lo = self.fetch8()
        hi = self.fetch8()
        return lo | (hi << 8)

    def flags(self, value):
        value &= 0xFFFF
        self.Z = int(value == 0)
        self.N = int(bool(value & 0x8000))

    def read8(self, address):
        return self.ram[address & 0xFFFF]

    def write8(self, address, value):
        self.ram[address & 0xFFFF] = value & 0xFF

    def read16(self, address):
        lo = self.read8(address)
        hi = self.read8(address + 1)
        return lo | (hi << 8)

    def write16(self, address, value):
        self.write8(address, value)
        self.write8(address + 1, value >> 8)

    def push16(self, value):
        value &= 0xFFFF
        self.ram[self.SP] = value & 0xFF
        self.SP = (self.SP - 1) & 0xFFFF
        self.ram[self.SP] = (value >> 8) & 0xFF
        self.SP = (self.SP - 1) & 0xFFFF

    def pop16(self):
        self.SP = (self.SP + 1) & 0xFFFF
        hi = self.ram[self.SP]
        self.SP = (self.SP + 1) & 0xFFFF
        lo = self.ram[self.SP]
        return lo | (hi << 8)

    def load(self, program):
        self.reset()
        if len(program) > ROM_SIZE:
            raise ValueError("PROGRAM TOO LARGE")
        self.rom[:len(program)] = program

    def step(self):
        op = self.fetch8()

        # BASIC
        if op == 0x00:
            pass
        elif op == 0x01:
            self.A = self.fetch16()
            self.flags(self.A)
        elif op == 0x02:
            self.B = self.fetch16()
        elif op == 0x03:
            self.C = self.fetch16()
        elif op == 0x04:
            self.D = self.fetch16()

        # MATH
        elif op == 0x05:
            value = self.A + self.B
            self.CF = int(value > 0xFFFF)
            self.A = value & 0xFFFF
            self.flags(self.A)
        elif op == 0x06:
            value = self.A - self.B
            self.CF = int(value < 0)
            self.A = value & 0xFFFF
            self.flags(self.A)
        elif op == 0x07:
            self.A = (self.A + 1) & 0xFFFF
            self.flags(self.A)
        elif op == 0x08:
            self.A = (self.A - 1) & 0xFFFF
            self.flags(self.A)

        # MEMORY
        elif op == 0x09:
            address = self.fetch16()
            self.write16(address, self.A)
        elif op == 0x0A:
            address = self.fetch16()
            self.A = self.read16(address)
            self.flags(self.A)

        # JUMPS
        elif op == 0x0B:
            self.PC = self.fetch16()
        elif op == 0x0C:
            address = self.fetch16()
            if self.Z:
                self.PC = address
        elif op == 0x0D:
            address = self.fetch16()
            if not self.Z:
                self.PC = address
        elif op == 0x0E:
            self.flags(self.A - self.B)

        # STACK
        elif op == 0x0F:
            self.push16(self.A)
        elif op == 0x10:
            self.A = self.pop16()
            self.flags(self.A)
        elif op == 0x11:
            address = self.fetch16()
            self.push16(self.PC)
            self.PC = address
        elif op == 0x12:
            self.PC = self.pop16()

        # CONSOLE
        elif op == 0x13:
            self.output_buffer.append(chr(self.A & 0xFF))
        elif op == 0x14:
            self.A = 0
            self.flags(self.A)
        elif op == 0x15:
            self.running = False

        # MOVES
        elif op == 0x16:
            self.A = self.B
            self.flags(self.A)
        elif op == 0x17:
            self.B = self.A

        # EXTRA MATH
        elif op == 0x18:
            value = self.A + self.C
            self.CF = int(value > 0xFFFF)
            self.A = value & 0xFFFF
            self.flags(self.A)
        elif op == 0x19:
            value = self.A + self.D
            self.CF = int(value > 0xFFFF)
            self.A = value & 0xFFFF
            self.flags(self.A)
        elif op == 0x1A:
            value = self.A - self.C
            self.CF = int(value < 0)
            self.A = value & 0xFFFF
            self.flags(self.A)
        elif op == 0x1B:
            value = self.A - self.D
            self.CF = int(value < 0)
            self.A = value & 0xFFFF
            self.flags(self.A)

        # LOGIC
        elif op == 0x1C:
            self.A ^= self.B
            self.flags(self.A)
        elif op == 0x1D:
            self.A &= self.B
            self.flags(self.A)
        elif op == 0x1E:
            self.A |= self.B
            self.flags(self.A)
        elif op == 0x1F:
            self.A = (~self.A) & 0xFFFF
            self.flags(self.A)

        # I/O
        elif op == 0x20:
            port = self.fetch8()
            self.A = hardware.read_port(port)
            self.flags(self.A)
        elif op == 0x21:
            port = self.fetch8()
            hardware.write_port(port, self.A)
        else:
            raise RuntimeError(
                f"INVALID OPCODE {op:02X} AT {self.PC - 1:04X}"
            )

        self.cycles += 1

    def run(self, limit=1_000_000):
        self.running = True
        while self.running:
            if self.cycles >= limit:
                self.running = False
                raise RuntimeError("CPU CYCLE LIMIT")
            self.step()

    def output(self):
        return "".join(self.output_buffer)


cpu = MiniCPU()


# ============================================================
# ASSEMBLER
# ============================================================

OPS = {
    "NOP": 0x00,
    "LDIA": 0x01, "LDIB": 0x02, "LDIC": 0x03, "LDID": 0x04,
    "ADD": 0x05, "SUB": 0x06,
    "INC": 0x07, "DEC": 0x08,
    "STA": 0x09, "LDA": 0x0A,
    "JMP": 0x0B, "JZ": 0x0C, "JNZ": 0x0D,
    "CMP": 0x0E,
    "PUSH": 0x0F, "POP": 0x10,
    "CALL": 0x11, "RET": 0x12,
    "OUT": 0x13, "IN": 0x14,
    "HLT": 0x15,
    "MOVAB": 0x16, "MOVBA": 0x17,
    "ADDC": 0x18, "ADDD": 0x19,
    "SUBC": 0x1A, "SUBD": 0x1B,
    "XOR": 0x1C, "AND": 0x1D, "OR": 0x1E, "NOT": 0x1F,
    "INP": 0x20, "OUTP": 0x21,
}

ARG8_OPS = {"INP", "OUTP"}
ARG16_OPS = {
    "LDIA", "LDIB", "LDIC", "LDID",
    "STA", "LDA", "JMP", "JZ", "JNZ", "CALL",
}


def number(x):
    x = x.strip()
    if x.lower().startswith("0x"):
        return int(x, 16)
    if x.lower().startswith("0b"):
        return int(x, 2)
    if x.lower().startswith("0o"):
        return int(x, 8)
    if len(x) >= 3 and x.startswith("'") and x.endswith("'"):
        return ord(x[1:-1])
    return int(x)


def _tokenize(line):
    try:
        return [part.rstrip(",") for part in shlex.split(line, posix=False)]
    except ValueError:
        return line.replace(",", " ").split()


def _parse_line(raw):
    label = None
    line = raw.split(";", 1)[0].strip()
    if not line:
        return None, None, None
    if ":" in line:
        label, line = line.split(":", 1)
        line = line.strip()
        if not line:
            return label.strip().upper(), None, None
    parts = _tokenize(line)
    return (
        label.strip().upper() if label is not None else None,
        parts[0].upper(),
        parts[1:],
    )


def assemble(source):
    lines = []
    labels = {}
    pc = 0

    for raw in source.splitlines():
        label, op, args = _parse_line(raw)
        if op is None:
            if label is not None:
                labels[label] = pc
            continue
        if label is not None:
            labels[label] = pc
        pc += 1
        if op in ARG8_OPS:
            pc += 1
        elif op in ARG16_OPS:
            pc += 2
        lines.append((op, args))

    result = bytearray()
    for op, args in lines:
        result.append(OPS[op])
        if op in ARG8_OPS:
            result.append(number(args[0]) & 0xFF)
        elif op in ARG16_OPS:
            arg = args[0]
            value = labels[arg.upper()] if arg.upper() in labels else number(arg)
            value &= 0xFFFF
            result.append(value & 0xFF)
            result.append((value >> 8) & 0xFF)

    return bytes(result)


# ============================================================
# SHELL
# ============================================================

def _help():
    return """ChatCPU 2.1

FILES
  ls [-l] [path]
  cd <path> / pwd
  mkdir <path>
  rmdir <path>
  touch <file>
  cat <file>
  write <file> <text>
  append <file> <text>
  cp <src> <dst>
  mv <src> <dst>
  rm [-r] <path>
  echo <text>
  disk

CPU
  run <file> [cycles]
  step <file> [cycles]
  asm <file>
  regs
  mem [address] [length]
  reset

HARDWARE
  screen
  cls
  key <character>
  keys

PROGRAMS
  snake
  exec <file>

SYSTEM
  help
  clear
"""


async def _cmd_help(args):
    return _help()


async def _cmd_ls(args):
    long = False
    if args and args[0] == "-l":
        long = True
        args = args[1:]
    path = resolve(args[0]) if args else CWD
    if not await is_dir(path):
        return f"ls: {path}: no such directory"
    prefix = path + "/" if path != "/" else "/"
    allf = await all_files()
    lines = []
    for name in await list_dir(path):
        if name.startswith("."):
            continue
        full = prefix + name
        isdir = any(f.startswith(full + "/") for f in allf)
        if long:
            if isdir:
                lines.append(f"{name}/  dir")
            else:
                size = len(await read_file(full))
                lines.append(f"{name}  {size} bytes")
        else:
            lines.append(name + ("/" if isdir else ""))
    return "\n".join(lines) or "(empty)"


async def _cmd_cat(args):
    return await read_file(resolve(args[0]))


async def _cmd_write(args):
    if not args:
        return "usage: write <file> <text>"
    await write_file(resolve(args[0]), " ".join(args[1:]).replace("\\n", "\n"))
    return "OK"


async def _cmd_append(args):
    if not args:
        return "usage: append <file> <text>"
    path = resolve(args[0])
    text = " ".join(args[1:]).replace("\\n", "\n")
    existing = ""
    try:
        existing = await read_file(path)
    except Exception:
        pass
    new = existing + "\n" + text if existing else text
    await write_file(path, new)
    return "OK"


async def _cmd_cd(args):
    global CWD
    target = resolve(args[0]) if args else "/"
    if not await is_dir(target):
        return f"cd: {target}: no such directory"
    CWD = target
    await write_file(CWD_FILE, target)
    return CWD


async def _cmd_pwd(args):
    return CWD


async def _cmd_mkdir(args):
    if not args:
        return "usage: mkdir <path>"
    path = resolve(args[0])
    if path == "/":
        return "OK"
    if await exists(path):
        return f"mkdir: {path}: file exists"
    if not await exists(path + "/.keep"):
        await write_file(path + "/.keep", "")
    return "OK"


async def _cmd_rmdir(args):
    if not args:
        return "usage: rmdir <path>"
    path = resolve(args[0])
    if path == "/":
        return "cannot remove /"
    prefix = path + "/"
    children = [f for f in await all_files() if f.startswith(prefix)]
    if not children:
        return f"rmdir: {path}: no such directory"
    if [f for f in children if f != prefix + ".keep"]:
        return f"rmdir: {path}: directory not empty"
    await delete_file(prefix + ".keep")
    return "OK"


async def _cmd_mv(args):
    if len(args) < 2:
        return "usage: mv <src> <dst>"
    src, dst = resolve(args[0]), resolve(args[1])
    if not await exists(src):
        return f"mv: {src}: no such file"
    await write_file(dst, await read_file(src))
    await delete_file(src)
    return "OK"


async def _cmd_cp(args):
    if len(args) < 2:
        return "usage: cp <src> <dst>"
    src, dst = resolve(args[0]), resolve(args[1])
    if not await exists(src):
        return f"cp: {src}: no such file"
    await write_file(dst, await read_file(src))
    return "OK"


async def _cmd_echo(args):
    return " ".join(args)


async def _cmd_exec(args):
    if not args:
        return "usage: exec <file>"
    source = await read_file(resolve(args[0]))
    code = compile(source, args[0], "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        coro = eval(code, globals())
        if coro is not None:
            await coro
    return buf.getvalue() or "OK"


async def _cmd_snake(args):
    try:
        state = json.loads(await read_file("/minios/snake.save"))
    except Exception:
        state = json.loads(SNAKE_SAVE)

    snake = state["segments"]
    food = state["food"]
    direction = state["direction"]
    score = state["score"]
    alive = state["alive"]

    W, H = 20, 10
    dirs = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}
    opposite = {1: 2, 2: 1, 3: 4, 4: 3}

    input_text = ""
    try:
        input_text = (await read_file("/minios/shell/input.txt")).strip().upper()
    except Exception:
        pass
    if input_text in dirs:
        nd = {"UP": 1, "DOWN": 2, "LEFT": 3, "RIGHT": 4}[input_text]
        if nd != opposite[direction]:
            direction = nd

    dx, dy = dirs[direction]
    hx, hy = snake[0]
    head = [hx + dx, hy + dy]
    if head[0] < 0 or head[0] >= W or head[1] < 0 or head[1] >= H or head in snake:
        alive = False
    if alive:
        snake.insert(0, head)
        if head == food:
            score += 1
            food = [(food[0] + 7) % W, (food[1] + 3) % H]
        else:
            snake.pop()

    state = {
        "length": len(snake),
        "segments": snake,
        "food": food,
        "direction": direction,
        "score": score,
        "alive": alive,
    }
    await write_file("/minios/snake.save", json.dumps(state))

    out = [
        "=== ChatCPU Snake ===",
        "",
        f"Input: {input_text or '(none)'}",
        f"Direction: {direction}",
        f"Score: {score}",
        "",
        "+" + "-" * W + "+",
    ]
    for y in range(H):
        row = ""
        for x in range(W):
            pos = [x, y]
            if pos == snake[0]:
                row += "#"
            elif pos in snake:
                row += "="
            elif pos == food:
                row += "*"
            else:
                row += " "
        out.append("|" + row + "|")
    out.append("+" + "-" * W + "+")
    out.append(f"Head: {snake[0]}  Length: {len(snake)}  Score: {score}")
    out.append("STATE SAVED" if alive else "GAME OVER")
    return "\n".join(out)


async def _cmd_touch(args):
    await write_file(resolve(args[0]), "")
    return "OK"


async def _cmd_rm(args):
    if not args:
        return "usage: rm [-r] <path>"
    if args[0] == "-r":
        path = resolve(args[1])
        if path == "/":
            return "refusing to remove /"
        prefix = path + "/"
        removed = 0
        for f in await all_files():
            if f == path or f.startswith(prefix):
                await delete_file(f)
                removed += 1
        if removed == 0:
            return f"rm: {path}: no such file or directory"
        return f"OK ({removed} items removed)"
    path = resolve(args[0])
    if not await exists(path):
        return f"rm: {path}: no such file"
    await delete_file(path)
    return "OK"


async def _cmd_disk(args):
    result = await all_files()
    return "\n".join(result) or "(empty)"


async def _cmd_asm(args):
    source = await read_file(resolve(args[0]))
    program = assemble(source)
    return (
        f"ASSEMBLED {len(program)} BYTES\n"
        + " ".join(f"{x:02X}" for x in program)
    )


async def _cmd_run(args):
    if not args:
        return "usage: run <file> [cycles]"
    source = await read_file(resolve(args[0]))
    program = assemble(source)
    cpu.load(program)
    limit = number(args[1]) if len(args) > 1 else 1_000_000
    try:
        cpu.run(limit)
        return f"HALTED ({cpu.cycles} cycles)\n" + cpu.output()
    except RuntimeError as e:
        return f"{e}\n" + cpu.output()


def regs_text():
    return (
        f"A  = {cpu.A:04X} ({cpu.A})\n"
        f"B  = {cpu.B:04X} ({cpu.B})\n"
        f"C  = {cpu.C:04X} ({cpu.C})\n"
        f"D  = {cpu.D:04X} ({cpu.D})\n"
        f"PC = {cpu.PC:04X} ({cpu.PC})\n"
        f"SP = {cpu.SP:04X} ({cpu.SP})\n"
        f"Z  = {cpu.Z}\n"
        f"CF = {cpu.CF}\n"
        f"N  = {cpu.N}\n"
        f"CYCLES = {cpu.cycles}"
    )


async def _cmd_regs(args):
    return regs_text()


async def _cmd_step(args):
    if not args:
        return "usage: step <file> [cycles]"
    source = await read_file(resolve(args[0]))
    program = assemble(source)
    cpu.load(program)
    limit = number(args[1]) if len(args) > 1 else 16
    for _ in range(limit):
        if not cpu.running:
            break
        cpu.step()
    return (
        f"STEPPED {limit} CYCLES (PC={cpu.PC:04X})\n" + regs_text()
    )


async def _cmd_mem(args):
    address = number(args[0]) if args else 0
    length = number(args[1]) if len(args) > 1 else 64
    address &= 0xFFFF
    lines = []
    for offset in range(0, length, 16):
        addr = (address + offset) & 0xFFFF
        data = cpu.ram[addr:addr + 16]
        lines.append(
            f"{addr:04X}: "
            + " ".join(f"{x:02X}" for x in data)
        )
    return "\n".join(lines)


async def _cmd_reset(args):
    cpu.reset()
    hardware.reset()
    return "RESET OK"


async def _cmd_screen(args):
    return "\n" + hardware.render() + "\n"


async def _cmd_cls(args):
    hardware.clear_screen()
    return "SCREEN CLEARED"


async def _cmd_key(args):
    if not args:
        return "usage: key <character>"
    hardware.key(args[0][0])
    return f"KEY QUEUED: {args[0][0]}"


async def _cmd_keys(args):
    return f"QUEUED: {len(hardware.keys)}"


async def _cmd_clear(args):
    d = await disk()
    for r in await d.keys():
        await d.delete(r)
    return "DISK CLEARED"


async def shell(line):
    parts = shlex.split(line)
    if not parts:
        return ""
    cmd = parts[0].lower()
    args = parts[1:]

    commands = {
        "help": _cmd_help,
        "ls": _cmd_ls,
        "cd": _cmd_cd,
        "pwd": _cmd_pwd,
        "mkdir": _cmd_mkdir,
        "rmdir": _cmd_rmdir,
        "cat": _cmd_cat,
        "write": _cmd_write,
        "append": _cmd_append,
        "touch": _cmd_touch,
        "cp": _cmd_cp,
        "mv": _cmd_mv,
        "rm": _cmd_rm,
        "echo": _cmd_echo,
        "disk": _cmd_disk,
        "asm": _cmd_asm,
        "run": _cmd_run,
        "step": _cmd_step,
        "regs": _cmd_regs,
        "mem": _cmd_mem,
        "reset": _cmd_reset,
        "screen": _cmd_screen,
        "cls": _cmd_cls,
        "key": _cmd_key,
        "keys": _cmd_keys,
        "exec": _cmd_exec,
        "snake": _cmd_snake,
        "clear": _cmd_clear,
    }

    handler = commands.get(cmd)
    if handler is None:
        return f"{cmd}: command not found"
    return await handler(args)


PROMPT = "MiniOS@ChatCPU~$"


async def cmd(line):
    """Run a shell command and return it formatted with a terminal prompt."""
    return f"{PROMPT} {line}\n" + await shell(line)


# ============================================================
# DEFAULT FILES
# ============================================================

VERSION = """ChatCPU MiniOS
Version 2.1
CPU: ChatCPU
Architecture: 16-bit
RAM: 65536
ROM: 65536
Persistent storage: Cache
"""

CONFIG = """[machine]
name=ChatCPU
os=MiniOS
version=2.1
ram=65536
rom=65536
screen=32x16
io=256

[storage]
backend=Cache
persistent=true
"""

HELLO = r'''; ChatCPU Hello World

LDIA 'H'
OUT

LDIA 'e'
OUT

LDIA 'l'
OUT

LDIA 'l'
OUT

LDIA 'o'
OUT

LDIA ' '
OUT

LDIA 'C'
OUT

LDIA 'h'
OUT

LDIA 'a'
OUT

LDIA 't'
OUT

LDIA 'C'
OUT

LDIA 'P'
OUT

LDIA 'U'
OUT

HLT
'''

DEMO = """\
; MiniCPU 2.1
; Draw X at screen coordinate 10,5

LDIA 'X'
LDIB 10
LDIC 5
OUTP 0x10

HLT
"""

SNAKE_SAVE = ('{"length": 3, "segments": [[10, 5], [9, 5], [8, 5]], '
              '"food": [15, 5], "direction": 4, "score": 0, "alive": true}')

DEFAULT_FILES = {
    "/minios/version.txt": VERSION,
    "/minios/config.cfg": CONFIG,
    "/minios/system.cfg": CONFIG,
    "/minios/programs/demo.asm": DEMO,
    "/minios/programs/hello.asm": HELLO,
    "/minios/snake.save": SNAKE_SAVE,
}


async def boot():
    global CWD
    src = _cpu_source()
    if src is not None:
        try:
            await write_file("/minios/cpu.py", src)
        except Exception:
            pass

    try:
        for path, data in DEFAULT_FILES.items():
            if not await exists(path):
                await write_file(path, data)
    except Exception as e:
        print(f"DISK WARNING: {type(e).__name__}: {e}")

    try:
        saved_cwd = (await read_file(CWD_FILE)).strip()
        if saved_cwd.startswith("/") and await is_dir(saved_cwd):
            CWD = saved_cwd
    except Exception:
        CWD = "/"


def _cpu_source():
    """Return this module's own source, for saving to the cache.

    In the sandbox, pasted code has no readable __file__, so boot() cannot
    recover its source from disk. _CPU_SRC (regenerated by tools/embed_src.py
    and verified by test_cpu.py) carries a gzip+base64 copy of this file so
    the machine can always save itself. Returns None if neither works.
    """
    try:
        with open(__file__) as f:
            return f.read()
    except Exception:
        pass
    try:
        src = gzip.decompress(base64.b64decode(_CPU_SRC)).decode("utf-8")
        return src + '\n_CPU_SRC = "' + _CPU_SRC + '"\n'
    except Exception:
        return None


_CPU_SRC = "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"
