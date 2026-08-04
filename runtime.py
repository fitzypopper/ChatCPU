import shlex

BASE = "https://chatcpu.local"
CACHE_NAME = "CHATCPU-MINIOS"

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
        self.PC = (self.PC + 1) & 0xFFFF

        if op == 0x01:
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
            self.A = (self.A + self.B) & 0xFFFF

        elif op == 0x13:
            self.output_buffer.append(chr(self.A & 0xFF))

        elif op == 0x15:
            self.running = False

        else:
            raise RuntimeError(f"Unknown opcode {op:02X}")

        self.Z = int(self.A == 0)
        self.cycles += 1

    def run(self):
        self.running = True

        while self.running:
            if self.cycles > 100000:
                raise RuntimeError("CPU cycle limit reached")
            self.step()

    def output(self):
        return "".join(self.output_buffer)


cpu = ChatCPU()

OPS = {
    "LDIA": 0x01,
    "LDIB": 0x02,
    "ADD": 0x05,
    "OUT": 0x13,
    "HLT": 0x15,
}

def value(x):
    x = x.strip()

    if x.lower().startswith("0x"):
        return int(x, 16)

    if len(x) >= 3 and x[0] == "'" and x[-1] == "'":
        return ord(x[1:-1])

    return int(x)

def assemble(source):
    program = bytearray()

    for raw in source.splitlines():
        line = raw.split(";", 1)[0].strip()

        if not line:
            continue

        parts = line.replace(",", " ").split()
        op = parts[0].upper()

        if op not in OPS:
            raise ValueError(f"Unknown instruction: {op}")

        program.append(OPS[op])

        if op in ("LDIA", "LDIB"):
            n = value(parts[1])
            program.append(n & 0xFF)
            program.append((n >> 8) & 0xFF)

    return bytes(program)
