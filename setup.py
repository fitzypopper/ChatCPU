import js
import json

BASE = "https://chatcpu.local"
CACHE_NAME = "CHATCPU-MINIOS"


async def disk():
    return await js.caches.open(CACHE_NAME)


def request(path):
    if not path.startswith("/"):
        path = "/" + path

    return js.Request.new(
        BASE + path
    )


async def write_file(path, data):
    cache = await disk()

    await cache.put(
        request(path),
        js.Response.new(data)
    )


# ============================================================
# FILES
# ============================================================

KERNEL = r'''# ChatCPU MiniOS kernel

CPU_NAME = "ChatCPU"
ARCH = "16-bit"

RAM_SIZE = 65536
ROM_SIZE = 65536

SCREEN_WIDTH = 32
SCREEN_HEIGHT = 16

IO_PORTS = 256

PORT_KEY = 0x00
PORT_KEY_STATE = 0x01
PORT_SCREEN = 0x10
PORT_RANDOM = 0x20
'''


VERSION = """ChatCPU MiniOS
Version 3.0
CPU: ChatCPU
Architecture: 16-bit
RAM: 65536
ROM: 65536
Persistent storage: Cache
"""


CONFIG = """[machine]
name=ChatCPU
os=MiniOS
version=3.0
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


SNAKE_SAVE = json.dumps({
    "length": 3,
    "segments": [
        [10, 5],
        [9, 5],
        [8, 5]
    ],
    "food": [15, 5],
    "direction": 4,
    "score": 0,
    "alive": True
})


# ============================================================
# SHELL
# ============================================================

SHELL = r'''
import js
import shlex

BASE = "https://chatcpu.local"
CACHE_NAME = "CHATCPU-MINIOS"


async def disk():
    return await js.caches.open(CACHE_NAME)


def request(path):

    if not path.startswith("/"):
        path = "/" + path

    return js.Request.new(
        BASE + path
    )


async def read_file(path):

    c = await disk()

    r = await c.match(
        request(path)
    )

    if r is None:
        raise FileNotFoundError(path)

    return await r.text()


async def list_files():

    c = await disk()

    files = []

    for r in await c.keys():

        url = str(r.url)

        if url.startswith(BASE):

            files.append(
                url[len(BASE):]
            )

    return sorted(files)


# ============================================================
# CPU
# ============================================================

class ChatCPU:

    def __init__(self):
        self.reset()


    def reset(self):

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

        self.ram = bytearray(65536)
        self.rom = bytearray(65536)

        self.running = False
        self.output_buffer = []


    def load(self, program):

        self.reset()

        self.rom[:len(program)] = program


    def step(self):

        op = self.rom[self.PC]

        self.PC += 1

        if op == 0x00:
            pass

        elif op == 0x01:

            lo = self.rom[self.PC]
            hi = self.rom[self.PC + 1]

            self.PC += 2

            self.A = lo | (hi << 8)


        elif op == 0x02:

            lo = self.rom[self.PC]
            hi = self.rom[self.PC + 1]

            self.PC += 2

            self.B = lo | (hi << 8)


        elif op == 0x05:

            result = self.A + self.B

            self.CF = int(
                result > 0xFFFF
            )

            self.A = result & 0xFFFF


        elif op == 0x06:

            result = self.A - self.B

            self.CF = int(
                result < 0
            )

            self.A = result & 0xFFFF


        elif op == 0x07:

            self.A = (
                self.A + 1
            ) & 0xFFFF


        elif op == 0x08:

            self.A = (
                self.A - 1
            ) & 0xFFFF


        elif op == 0x13:

            self.output_buffer.append(
                chr(self.A & 0xFF)
            )


        elif op == 0x15:

            self.running = False


        else:

            raise RuntimeError(
                f"Unknown opcode {op:02X} "
                f"at {self.PC - 1:04X}"
            )


        self.Z = int(
            self.A == 0
        )

        self.N = int(
            bool(self.A & 0x8000)
        )

        self.cycles += 1


    def run(self):

        self.running = True

        while self.running:

            if self.cycles >= 1000000:

                self.running = False

                raise RuntimeError(
                    "CPU cycle limit reached"
                )

            self.step()


    def output(self):

        return "".join(
            self.output_buffer
        )


cpu = ChatCPU()


# ============================================================
# ASSEMBLER
# ============================================================

OPS = {

    "NOP": 0x00,

    "LDIA": 0x01,
    "LDIB": 0x02,

    "ADD": 0x05,
    "SUB": 0x06,

    "INC": 0x07,
    "DEC": 0x08,

    "OUT": 0x13,

    "HLT": 0x15,
}


def number(x):

    x = x.strip()

    if x.lower().startswith("0x"):
        return int(x, 16)

    if x.lower().startswith("0b"):
        return int(x, 2)

    if (
        len(x) >= 3
        and x[0] == "'"
        and x[-1] == "'"
    ):
        return ord(x[1:-1])

    return int(x)


def assemble(source):

    program = bytearray()

    for raw in source.splitlines():

        line = raw.split(
            ";",
            1
        )[0].strip()

        if not line:
            continue

        parts = line.replace(
            ",",
            " "
        ).split()

        op = parts[0].upper()

        if op not in OPS:

            raise ValueError(
                f"Unknown instruction: {op}"
            )

        program.append(
            OPS[op]
        )

        if op in (
            "LDIA",
            "LDIB"
        ):

            value = number(
                parts[1]
            )

            program.append(
                value & 0xFF
            )

            program.append(
                (value >> 8) & 0xFF
            )

    return bytes(program)


# ============================================================
# COMMAND
# ============================================================

async def command(line):

    parts = shlex.split(line)

    if not parts:
        return ""

    cmd = parts[0].lower()
    args = parts[1:]


    if cmd == "help":

        return """ChatCPU MiniOS

SYSTEM
  help
  version
  clear

FILES
  ls
  cat <file>
  disk

CPU
  regs
  reset
  mem <address> [length]

PROGRAMS
  asm <file>
  run <file>

GAMES
  snake
"""


    if cmd == "version":

        return await read_file(
            "/minios/version.txt"
        )


    if cmd == "ls":

        return "\n".join(
            await list_files()
        )


    if cmd == "disk":

        files = await list_files()

        return (
            "ChatCPU persistent disk\n"
            f"{len(files)} files\n\n"
            +
            "\n".join(files)
        )


    if cmd == "cat":

        if not args:

            return "usage: cat <file>"

        return await read_file(
            args[0]
        )


    if cmd == "asm":

        if not args:

            return "usage: asm <file>"

        source = await read_file(
            args[0]
        )

        program = assemble(
            source
        )

        return (
            f"ASSEMBLED "
            f"{len(program)} BYTES\n\n"
            +
            " ".join(
                f"{x:02X}"
                for x in program
            )
        )


    if cmd == "run":

        if not args:

            return "usage: run <file>"

        source = await read_file(
            args[0]
        )

        program = assemble(
            source
        )

        cpu.load(
            program
        )

        cpu.run()

        return (
            f"HALTED "
            f"({cpu.cycles} cycles)\n\n"
            +
            cpu.output()
        )


    if cmd == "regs":

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


    if cmd == "reset":

        cpu.reset()

        return "ChatCPU RESET OK"


    if cmd == "mem":

        address = (
            number(args[0])
            if args
            else 0
        )

        length = (
            number(args[1])
            if len(args) > 1
            else 64
        )

        data = cpu.ram[
            address:
            address + length
        ]

        return (
            f"{address:04X}: "
            +
            " ".join(
                f"{x:02X}"
                for x in data
            )
        )


    if cmd == "clear":

        return "\n" * 40


    if cmd == "snake":

        return await read_file(
            "/minios/snake.save"
        )


    return (
        f"{cmd}: command not found"
    )


print("ChatCPU shell loaded")
print("CPU:", type(cpu).__name__)
print("Commands ready")
'''


# ============================================================
# BOOT
# ============================================================

BOOT = r'''import js

BASE = "https://chatcpu.local"
CACHE_NAME = "CHATCPU-MINIOS"


async def disk():

    return await js.caches.open(
        CACHE_NAME
    )


def request(path):

    if not path.startswith("/"):
        path = "/" + path

    return js.Request.new(
        BASE + path
    )


async def load(path):

    cache = await disk()

    response = await cache.match(
        request(path)
    )

    if response is None:

        raise FileNotFoundError(
            path
        )

    return await response.text()


async def boot():

    print("=" * 50)
    print("             ChatCPU MiniOS")
    print("=" * 50)
    print()

    print(
        "Loading /minios/shell.py..."
    )

    source = await load(
        "/minios/shell.py"
    )

    namespace = {
        "__builtins__": __builtins__,
        "__name__": "__main__",
    }

    exec(
        compile(
            source,
            "/minios/shell.py",
            "exec"
        ),
        namespace
    )

    print()
    print(
        "Shell loaded from persistent disk"
    )

    print()
    print("MiniOS READY")
    print()

    return namespace


minios = await boot()

command = minios["command"]
cpu = minios["cpu"]
assemble = minios["assemble"]

print("command() READY")
print("cpu READY")
print("assemble() READY")
'''


# ============================================================
# WRITE EVERYTHING
# ============================================================

FILES = {

    "/minios/boot.py":
        BOOT,

    "/minios/kernel.py":
        KERNEL,

    "/minios/shell.py":
        SHELL,

    "/minios/runtime.py":
        SHELL,

    "/minios/version.txt":
        VERSION,

    "/minios/config.cfg":
        CONFIG,

    "/minios/system.cfg":
        CONFIG,

    "/minios/programs/hello.asm":
        HELLO,

    "/minios/snake.save":
        SNAKE_SAVE,
}


print("=" * 60)
print("             ChatCPU MiniOS SETUP")
print("=" * 60)
print()

print(
    f"Installing {len(FILES)} files..."
)

for path, data in FILES.items():

    await write_file(
        path,
        data
    )

    print(
        "INSTALLED:",
        path
    )


print()
print("=" * 60)
print("SETUP COMPLETE")
print("=" * 60)
print()

print(
    "Persistent MiniOS files have been created."
)

print()
print()
print("SETUP COMPLETE")
print("Next: run boot.py")