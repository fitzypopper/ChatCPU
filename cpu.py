import js
import shlex
import random
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
        if url.startswith(BASE):
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
  ls [path]
  cat <file>
  write <file> <text>
  touch <file>
  rm <file>
  disk

CPU
  run <file>
  asm <file>
  regs
  mem [address] [length]
  reset

HARDWARE
  screen
  cls
  key <character>
  keys

SYSTEM
  help
  clear
"""


async def _cmd_help(args):
    return _help()


async def _cmd_ls(args):
    path = args[0] if args else "/"
    result = await list_dir(path)
    return "\n".join(result) or "(empty)"


async def _cmd_cat(args):
    return await read_file(args[0])


async def _cmd_write(args):
    await write_file(args[0], " ".join(args[1:]))
    return "OK"


async def _cmd_touch(args):
    await write_file(args[0], "")
    return "OK"


async def _cmd_rm(args):
    await delete_file(args[0])
    return "OK"


async def _cmd_disk(args):
    result = await all_files()
    return "\n".join(result) or "(empty)"


async def _cmd_asm(args):
    source = await read_file(args[0])
    program = assemble(source)
    return (
        f"ASSEMBLED {len(program)} BYTES\n"
        + " ".join(f"{x:02X}" for x in program)
    )


async def _cmd_run(args):
    source = await read_file(args[0])
    program = assemble(source)
    cpu.load(program)
    cpu.run()
    return f"HALTED ({cpu.cycles} cycles)\n" + cpu.output()


async def _cmd_regs(args):
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
        "cat": _cmd_cat,
        "write": _cmd_write,
        "touch": _cmd_touch,
        "rm": _cmd_rm,
        "disk": _cmd_disk,
        "asm": _cmd_asm,
        "run": _cmd_run,
        "regs": _cmd_regs,
        "mem": _cmd_mem,
        "reset": _cmd_reset,
        "screen": _cmd_screen,
        "cls": _cmd_cls,
        "key": _cmd_key,
        "keys": _cmd_keys,
        "clear": _cmd_clear,
    }

    handler = commands.get(cmd)
    if handler is None:
        return f"{cmd}: command not found"
    return await handler(args)


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
    print("=" * 44)
    print("             ChatCPU 2.1")
    print("=" * 44)
    print()
    print("MiniCPU:       16-bit")
    print("RAM:           64 KiB")
    print("ROM:           64 KiB")
    print("I/O:           256 ports")
    print(f"SCREEN:        {SCREEN_W}x{SCREEN_H}")
    print("FILESYSTEM:    persistent")
    print()
    print("shell() READY")
    print()

    try:
        for path, data in DEFAULT_FILES.items():
            if not await exists(path):
                await write_file(path, data)
    except Exception as e:
        print(f"DISK WARNING: {type(e).__name__}: {e}")

    cpu.load(assemble(DEMO))
    cpu.run()
    print(hardware.render())
    print()

    print("=== SHELL DEMO ===")
    print()
    print(await shell("help"))
    print()
    print("=== REGISTERS ===")
    print(await shell("regs"))
    print()
    print("USAGE: append commands to cpu.py and run together, e.g.")
    print("  await shell('run /programs/hello.asm')")
    print("  await shell('regs')")
    print("  await shell('screen')")


try:
    await boot()
except Exception as e:
    print(f"BOOT ERROR: {type(e).__name__}: {e}")
    print(f"DETAILS: {e}")
