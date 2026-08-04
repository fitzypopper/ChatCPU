import js
import shlex
import random

# ============================================================
# MiniOS 2.1
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

CACHE_NAME = "MINIOS-OS-V21"
BASE = "https://minios.local"


# ============================================================
# PERSISTENT FILESYSTEM
# ============================================================

async def disk():
    return await js.caches.open(CACHE_NAME)


def req(path):
    if not path.startswith("/"):
        path = "/" + path

    return js.Request.new(
        BASE + path
    )


async def write_file(path, data):
    d = await disk()

    await d.put(
        req(path),
        js.Response.new(str(data))
    )


async def read_file(path):
    d = await disk()

    r = await d.match(
        req(path)
    )

    if r is None:
        raise FileNotFoundError(path)

    return await r.text()


async def exists(path):
    d = await disk()

    return (
        await d.match(
            req(path)
        )
        is not None
    )


async def delete_file(path):
    d = await disk()

    await d.delete(
        req(path)
    )


async def all_files():
    d = await disk()

    result = []

    for r in await d.keys():

        url = str(r.url)

        if url.startswith(BASE):
            result.append(
                url[len(BASE):]
            )

    return sorted(result)


async def list_dir(path="/"):

    if not path.startswith("/"):
        path = "/" + path

    path = path.rstrip("/")

    prefix = (
        path + "/"
        if path
        else "/"
    )

    result = set()

    for f in await all_files():

        if not f.startswith(prefix):
            continue

        rest = f[len(prefix):]

        if rest:
            result.add(
                rest.split("/", 1)[0]
            )

    return sorted(result)


# ============================================================
# HARDWARE
# ============================================================

class Hardware:

    def __init__(self):
        self.cpu = None
        self.reset()

    def reset(self):

        self.keys = []

        self.screen = [
            [" "] * SCREEN_W
            for _ in range(SCREEN_H)
        ]

    def attach(self, cpu):
        self.cpu = cpu

    # --------------------------------------------------------
    # KEYBOARD
    # --------------------------------------------------------

    def key(self, value):

        if value is None:
            return

        value = str(value)

        if not value:
            return

        self.keys.append(
            ord(value[0])
        )

    def keycode(self, value):

        self.keys.append(
            int(value) & 0xFF
        )

    # --------------------------------------------------------
    # PORT READ
    # --------------------------------------------------------

    def read_port(self, port):

        port &= 0xFF

        # keyboard
        if port == PORT_KEY:

            if self.keys:
                return self.keys.pop(0)

            return 0

        # keyboard state
        if port == PORT_KEY_STATE:

            return int(
                bool(self.keys)
            )

        # random
        if port == PORT_RANDOM:

            return random.randrange(
                0,
                256
            )

        return 0

    # --------------------------------------------------------
    # PORT WRITE
    # --------------------------------------------------------

    def write_port(self, port, value):

        port &= 0xFF
        value &= 0xFFFF

        if port == PORT_SCREEN:

            if self.cpu is None:
                return

            # A = character
            # B = X
            # C = Y

            x = self.cpu.B & 0xFFFF
            y = self.cpu.C & 0xFFFF

            if (
                0 <= x < SCREEN_W
                and
                0 <= y < SCREEN_H
            ):

                self.screen[y][x] = chr(
                    self.cpu.A & 0xFF
                )

    # --------------------------------------------------------
    # SCREEN
    # --------------------------------------------------------

    def clear_screen(self):

        self.screen = [
            [" "] * SCREEN_W
            for _ in range(SCREEN_H)
        ]

    def render(self):

        return "\n".join(
            "".join(row)
            for row in self.screen
        )


hardware = Hardware()


# ============================================================
# CPU
# ============================================================

class MiniCPU:

    def __init__(self):

        self.reset()

        hardware.attach(
            self
        )

    def reset(self):

        self.ram = bytearray(
            RAM_SIZE
        )

        self.rom = bytearray(
            ROM_SIZE
        )

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

    # ========================================================
    # FETCH
    # ========================================================

    def fetch8(self):

        value = self.rom[
            self.PC
        ]

        self.PC = (
            self.PC + 1
        ) & 0xFFFF

        return value

    def fetch16(self):

        lo = self.fetch8()
        hi = self.fetch8()

        return (
            lo |
            (hi << 8)
        )

    # ========================================================
    # FLAGS
    # ========================================================

    def flags(self, value):

        value &= 0xFFFF

        self.Z = int(
            value == 0
        )

        self.N = int(
            bool(value & 0x8000)
        )

    # ========================================================
    # MEMORY
    # ========================================================

    def read8(self, address):

        return self.ram[
            address & 0xFFFF
        ]

    def write8(self, address, value):

        self.ram[
            address & 0xFFFF
        ] = value & 0xFF

    def read16(self, address):

        lo = self.read8(
            address
        )

        hi = self.read8(
            address + 1
        )

        return (
            lo |
            (hi << 8)
        )

    def write16(self, address, value):

        self.write8(
            address,
            value
        )

        self.write8(
            address + 1,
            value >> 8
        )

    # ========================================================
    # STACK
    # ========================================================

    def push16(self, value):

        value &= 0xFFFF

        self.ram[
            self.SP
        ] = value & 0xFF

        self.SP = (
            self.SP - 1
        ) & 0xFFFF

        self.ram[
            self.SP
        ] = (
            value >> 8
        ) & 0xFF

        self.SP = (
            self.SP - 1
        ) & 0xFFFF

    def pop16(self):

        self.SP = (
            self.SP + 1
        ) & 0xFFFF

        hi = self.ram[
            self.SP
        ]

        self.SP = (
            self.SP + 1
        ) & 0xFFFF

        lo = self.ram[
            self.SP
        ]

        return (
            lo |
            (hi << 8)
        )

    # ========================================================
    # LOAD
    # ========================================================

    def load(self, program):

        self.reset()

        if len(program) > ROM_SIZE:

            raise ValueError(
                "PROGRAM TOO LARGE"
            )

        self.rom[
            :len(program)
        ] = program

    # ========================================================
    # STEP
    # ========================================================

    def step(self):

        op = self.fetch8()

        # ----------------------------------------------------
        # BASIC
        # ----------------------------------------------------

        if op == 0x00:
            pass

        elif op == 0x01:

            self.A = self.fetch16()

            self.flags(
                self.A
            )

        elif op == 0x02:

            self.B = self.fetch16()

        elif op == 0x03:

            self.C = self.fetch16()

        elif op == 0x04:

            self.D = self.fetch16()

        # ----------------------------------------------------
        # MATH
        # ----------------------------------------------------

        elif op == 0x05:

            value = (
                self.A +
                self.B
            )

            self.CF = int(
                value > 0xFFFF
            )

            self.A = (
                value &
                0xFFFF
            )

            self.flags(
                self.A
            )

        elif op == 0x06:

            value = (
                self.A -
                self.B
            )

            self.CF = int(
                value < 0
            )

            self.A = (
                value &
                0xFFFF
            )

            self.flags(
                self.A
            )

        elif op == 0x07:

            self.A = (
                self.A + 1
            ) & 0xFFFF

            self.flags(
                self.A
            )

        elif op == 0x08:

            self.A = (
                self.A - 1
            ) & 0xFFFF

            self.flags(
                self.A
            )

        # ----------------------------------------------------
        # MEMORY
        # ----------------------------------------------------

        elif op == 0x09:

            address = self.fetch16()

            self.write16(
                address,
                self.A
            )

        elif op == 0x0A:

            address = self.fetch16()

            self.A = self.read16(
                address
            )

            self.flags(
                self.A
            )

        # ----------------------------------------------------
        # JUMPS
        # ----------------------------------------------------

        elif op == 0x0B:

            self.PC = (
                self.fetch16()
            )

        elif op == 0x0C:

            address = (
                self.fetch16()
            )

            if self.Z:
                self.PC = address

        elif op == 0x0D:

            address = (
                self.fetch16()
            )

            if not self.Z:
                self.PC = address

        elif op == 0x0E:

            self.flags(
                self.A -
                self.B
            )

        # ----------------------------------------------------
        # STACK
        # ----------------------------------------------------

        elif op == 0x0F:

            self.push16(
                self.A
            )

        elif op == 0x10:

            self.A = (
                self.pop16()
            )

            self.flags(
                self.A
            )

        elif op == 0x11:

            address = (
                self.fetch16()
            )

            self.push16(
                self.PC
            )

            self.PC = address

        elif op == 0x12:

            self.PC = (
                self.pop16()
            )

        # ----------------------------------------------------
        # CONSOLE
        # ----------------------------------------------------

        elif op == 0x13:

            self.output_buffer.append(
                chr(
                    self.A & 0xFF
                )
            )

        elif op == 0x14:

            self.A = 0

            self.flags(
                self.A
            )

        elif op == 0x15:

            self.running = False

        # ----------------------------------------------------
        # MOVES
        # ----------------------------------------------------

        elif op == 0x16:

            self.A = self.B

            self.flags(
                self.A
            )

        elif op == 0x17:

            self.B = self.A

        # ----------------------------------------------------
        # EXTRA MATH
        # ----------------------------------------------------

        elif op == 0x18:

            value = (
                self.A +
                self.C
            )

            self.CF = int(
                value > 0xFFFF
            )

            self.A = (
                value &
                0xFFFF
            )

            self.flags(
                self.A
            )

        elif op == 0x19:

            value = (
                self.A +
                self.D
            )

            self.CF = int(
                value > 0xFFFF
            )

            self.A = (
                value &
                0xFFFF
            )

            self.flags(
                self.A
            )

        elif op == 0x1A:

            value = (
                self.A -
                self.C
            )

            self.CF = int(
                value < 0
            )

            self.A = (
                value &
                0xFFFF
            )

            self.flags(
                self.A
            )

        elif op == 0x1B:

            value = (
                self.A -
                self.D
            )

            self.CF = int(
                value < 0
            )

            self.A = (
                value &
                0xFFFF
            )

            self.flags(
                self.A
            )

        # ----------------------------------------------------
        # LOGIC
        # ----------------------------------------------------

        elif op == 0x1C:

            self.A ^= self.B

            self.flags(
                self.A
            )

        elif op == 0x1D:

            self.A &= self.B

            self.flags(
                self.A
            )

        elif op == 0x1E:

            self.A |= self.B

            self.flags(
                self.A
            )

        elif op == 0x1F:

            self.A = (
                ~self.A
            ) & 0xFFFF

            self.flags(
                self.A
            )

        # ----------------------------------------------------
        # I/O
        # ----------------------------------------------------

        elif op == 0x20:

            port = self.fetch8()

            self.A = (
                hardware.read_port(
                    port
                )
            )

            self.flags(
                self.A
            )

        elif op == 0x21:

            port = self.fetch8()

            hardware.write_port(
                port,
                self.A
            )

        else:

            raise RuntimeError(
                f"INVALID OPCODE "
                f"{op:02X} AT "
                f"{self.PC - 1:04X}"
            )

        self.cycles += 1

    # ========================================================
    # RUN
    # ========================================================

    def run(self, limit=1_000_000):

        self.running = True

        while self.running:

            if self.cycles >= limit:

                self.running = False

                raise RuntimeError(
                    "CPU CYCLE LIMIT"
                )

            self.step()

    def output(self):

        return "".join(
            self.output_buffer
        )


cpu = MiniCPU()


# ============================================================
# ASSEMBLER
# ============================================================

OPS = {

    "NOP": 0x00,

    "LDIA": 0x01,
    "LDIB": 0x02,
    "LDIC": 0x03,
    "LDID": 0x04,

    "ADD": 0x05,
    "SUB": 0x06,

    "INC": 0x07,
    "DEC": 0x08,

    "STA": 0x09,
    "LDA": 0x0A,

    "JMP": 0x0B,
    "JZ": 0x0C,
    "JNZ": 0x0D,

    "CMP": 0x0E,

    "PUSH": 0x0F,
    "POP": 0x10,

    "CALL": 0x11,
    "RET": 0x12,

    "OUT": 0x13,
    "IN": 0x14,

    "HLT": 0x15,

    "MOVAB": 0x16,
    "MOVBA": 0x17,

    "ADDC": 0x18,
    "ADDD": 0x19,

    "SUBC": 0x1A,
    "SUBD": 0x1B,

    "XOR": 0x1C,
    "AND": 0x1D,
    "OR": 0x1E,
    "NOT": 0x1F,

    "INP": 0x20,
    "OUTP": 0x21,
}


ARG8_OPS = {
    "INP",
    "OUTP",
}


ARG16_OPS = {
    "LDIA",
    "LDIB",
    "LDIC",
    "LDID",
    "STA",
    "LDA",
    "JMP",
    "JZ",
    "JNZ",
    "CALL",
}


def number(x):

    x = x.strip()

    if x.lower().startswith("0x"):
        return int(
            x,
            16
        )

    if x.lower().startswith("0b"):
        return int(
            x,
            2
        )

    if x.lower().startswith("0o"):
        return int(
            x,
            8
        )

    if (
        len(x) >= 3
        and x.startswith("'")
        and x.endswith("'")
    ):

        return ord(
            x[1:-1]
        )

    return int(x)


def assemble(source):

    lines = []
    labels = {}
    pc = 0

    # ========================================================
    # PASS 1
    # ========================================================

    for raw in source.splitlines():

        line = raw.split(
            ";",
            1
        )[0].strip()

        if not line:
            continue

        if ":" in line:

            label, line = line.split(
                ":",
                1
            )

            labels[
                label.strip().upper()
            ] = pc

            line = line.strip()

            if not line:
                continue

        parts = line.replace(
            ",",
            " "
        ).split()

        op = parts[0].upper()

        if op not in OPS:

            raise ValueError(
                f"UNKNOWN INSTRUCTION "
                f"{op}"
            )

        pc += 1

        if op in ARG8_OPS:
            pc += 1

        elif op in ARG16_OPS:
            pc += 2

        lines.append(
            line
        )

    # ========================================================
    # PASS 2
    # ========================================================

    result = bytearray()

    for line in lines:

        if ":" in line:

            line = line.split(
                ":",
                1
            )[1].strip()

            if not line:
                continue

        parts = line.replace(
            ",",
            " "
        ).split()

        op = parts[0].upper()

        result.append(
            OPS[op]
        )

        if op in ARG8_OPS:

            value = number(
                parts[1]
            )

            result.append(
                value & 0xFF
            )

        elif op in ARG16_OPS:

            arg = parts[1]

            if arg.upper() in labels:

                value = labels[
                    arg.upper()
                ]

            else:

                value = number(
                    arg
                )

            value &= 0xFFFF

            result.append(
                value & 0xFF
            )

            result.append(
                (value >> 8) & 0xFF
            )

    return bytes(result)


# ============================================================
# SHELL
# ============================================================

async def shell(line):

    parts = shlex.split(
        line
    )

    if not parts:
        return ""

    cmd = parts[0].lower()
    args = parts[1:]

    # --------------------------------------------------------
    # HELP
    # --------------------------------------------------------

    if cmd == "help":

        return """MiniOS 2.1

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

    # --------------------------------------------------------
    # LS
    # --------------------------------------------------------

    if cmd == "ls":

        path = (
            args[0]
            if args
            else "/"
        )

        result = await list_dir(
            path
        )

        return (
            "\n".join(result)
            or "(empty)"
        )

    # --------------------------------------------------------
    # CAT
    # --------------------------------------------------------

    if cmd == "cat":

        return await read_file(
            args[0]
        )

    # --------------------------------------------------------
    # WRITE
    # --------------------------------------------------------

    if cmd == "write":

        await write_file(
            args[0],
            " ".join(
                args[1:]
            )
        )

        return "OK"

    # --------------------------------------------------------
    # TOUCH
    # --------------------------------------------------------

    if cmd == "touch":

        await write_file(
            args[0],
            ""
        )

        return "OK"

    # --------------------------------------------------------
    # RM
    # --------------------------------------------------------

    if cmd == "rm":

        await delete_file(
            args[0]
        )

        return "OK"

    # --------------------------------------------------------
    # DISK
    # --------------------------------------------------------

    if cmd == "disk":

        result = await all_files()

        return (
            "\n".join(result)
            or "(empty)"
        )

    # --------------------------------------------------------
    # ASM
    # --------------------------------------------------------

    if cmd == "asm":

        source = await read_file(
            args[0]
        )

        program = assemble(
            source
        )

        return (
            f"ASSEMBLED "
            f"{len(program)} BYTES\n"
            +
            " ".join(
                f"{x:02X}"
                for x in program
            )
        )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    if cmd == "run":

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
            f"({cpu.cycles} cycles)\n"
            + cpu.output()
        )

    # --------------------------------------------------------
    # REGISTERS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # MEMORY
    # --------------------------------------------------------

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

        address &= 0xFFFF

        lines = []

        for offset in range(
            0,
            length,
            16
        ):

            addr = (
                address +
                offset
            ) & 0xFFFF

            data = cpu.ram[
                addr:
                addr + 16
            ]

            lines.append(
                f"{addr:04X}: "
                +
                " ".join(
                    f"{x:02X}"
                    for x in data
                )
            )

        return "\n".join(
            lines
        )

    # --------------------------------------------------------
    # RESET
    # --------------------------------------------------------

    if cmd == "reset":

        cpu.reset()
        hardware.reset()

        return "RESET OK"

    # --------------------------------------------------------
    # SCREEN
    # --------------------------------------------------------

    if cmd == "screen":

        return (
            "\n"
            +
            hardware.render()
            +
            "\n"
        )

    # --------------------------------------------------------
    # CLEAR SCREEN
    # --------------------------------------------------------

    if cmd == "cls":

        hardware.clear_screen()

        return "SCREEN CLEARED"

    # --------------------------------------------------------
    # KEY
    # --------------------------------------------------------

    if cmd == "key":

        if not args:
            return "usage: key <character>"

        hardware.key(
            args[0][0]
        )

        return (
            f"KEY QUEUED: "
            f"{args[0][0]}"
        )

    # --------------------------------------------------------
    # KEYS
    # --------------------------------------------------------

    if cmd == "keys":

        return (
            f"QUEUED: "
            f"{len(hardware.keys)}"
        )

    # --------------------------------------------------------
    # CLEAR CACHE
    # --------------------------------------------------------

    if cmd == "clear":

        d = await disk()

        for r in await d.keys():

            await d.delete(
                r
            )

        return "DISK CLEARED"

    return (
        f"{cmd}: command not found"
    )


# ============================================================
# DEMO PROGRAM
# ============================================================

DEMO = """
; MiniCPU 2.1
; Draw X at screen coordinate 10,5

LDIA 'X'
LDIB 10
LDIC 5
OUTP 0x10

HLT
"""


async def boot():

    if not await exists(
        "/programs/demo.asm"
    ):

        await write_file(
            "/programs/demo.asm",
            DEMO
        )

    print(
        "=" * 44
    )

    print(
        "             MiniOS 2.1"
    )

    print(
        "=" * 44
    )

    print()

    print(
        "MiniCPU:       16-bit"
    )

    print(
        "RAM:           64 KiB"
    )

    print(
        "ROM:           64 KiB"
    )

    print(
        "I/O:           256 ports"
    )

    print(
        f"SCREEN:        "
        f"{SCREEN_W}x{SCREEN_H}"
    )

    print(
        "FILESYSTEM:    persistent"
    )

    print()

    print(
        "shell() READY"
    )

    print()

    # test screen
    cpu.load(
        assemble(
            DEMO
        )
    )

    cpu.run()

    print(
        hardware.render()
    )

    print()

    print(
        "Try:"
    )

    print(
        "await shell('help')"
    )

    print(
        "await shell('screen')"
    )

    print(
        "await shell('key w')"
    )


await boot()
