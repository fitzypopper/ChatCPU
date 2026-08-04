# ChatCPU — a 16-bit computer built inside ChatGPT's Python code runner

### **this is very early access and a proof of concept** ###
ChatCPU is a homemade 16-bit computer: CPU, RAM, ROM, assembler, shell, persistent filesystem, and memory-mapped I/O — all implemented in plain Python and runnable directly inside ChatGPT's built-in Python code interpreter (the sandboxed browser-based runner, not a local install). No external dependencies, no server. The disk is persisted via the `caches` API (Cache Storage) available in that sandbox, so state survives between separate runs/messages as long as the cache isn't cleared.

This repo exists as a backup of the development log after a long conversation with an AI assistant, in case that chat ever disappears.

## Status

**ChatCPU 2.1** — latest version in the log.

- 16-bit CPU (A, B, C, D registers, PC, SP, Z/CF/N flags)
- 64 KiB RAM + 64 KiB ROM
- 16-bit addressing (up from the original 8-bit/256 byte)
- Custom assembler with labels, two-pass assembly, 8-bit and 16-bit arguments
- Memory-mapped I/O via ports (`INP`/`OUTP`)
- Text-based screen, 32×16 characters, written via `PORT_SCREEN`
- Keyboard queue (`hardware.key(...)`) — the input layer exists, but physical browser keyboard isn't wired to it yet
- Random port (`PORT_RANDOM`)
- Shell with commands for file management, assembling, running programs, and inspecting registers/memory

## History (short version)

1. **ChatCPU 1.0** — 8-bit CPU, 256 bytes of RAM, could boot and run `hello.asm` via a simple shell on top of a persistent cache-based filesystem.
2. Discussion about running Doom on it (no, for obvious reasons — no graphics, no framebuffer, nowhere near enough RAM).
3. Decision to scale up significantly: 64 KiB RAM, 64 KiB ROM, 16-bit addressing — while keeping the instruction set close enough that old programs could still be ported.
4. **ChatCPU 2.0/2.1** — added a hardware layer: I/O ports, framebuffer (text screen), keyboard queue, random port. The assembler was updated to handle both 8-bit and 16-bit instruction arguments (`ARG8_OPS` / `ARG16_OPS`).
5. Next step in the log: connect `hardware.key()` to an actual browser keyboard (e.g. via `MessageChannel`), so games like Snake can read input live instead of having keys queued manually through shell commands.

## Architecture

### CPU (`MiniCPU`)
A fetch-decode-execute loop running against ROM. Instructions are 1 opcode byte plus an optional 1 or 2 byte argument. The stack grows downward from `0xFFFF`. Most arithmetic/logic operations update the flags.

### Memory
- `self.rom` — the program, addressed by PC
- `self.ram` — data, addressed by `STA`/`LDA` and friends
- 16-bit reads/writes (`read16`/`write16`) are built from two 8-bit operations (little-endian)

### I/O
Port-based, in the style of classic 8-bit machines:
- `PORT_KEY (0x00)` — read the next key in the queue
- `PORT_KEY_STATE (0x01)` — is there a key waiting in the queue?
- `PORT_SCREEN (0x10)` — write a character to the screen; A = character, B = x, C = y
- `PORT_RANDOM (0x20)` — random number 0–255

### Assembler
Two passes: the first pass tracks the program counter and registers labels, the second pass emits bytes. Distinguishes between instructions taking 8-bit arguments (`INP`, `OUTP`) and 16-bit arguments (`LDIA`, `STA`, `JMP`, etc).

### Filesystem
Built on top of the `caches` API available in ChatGPT's Python code runner sandbox. Each file is a `Request`/`Response` pair stored under a fixed cache (`MINIOS-OS-V21`), with paths modeled as URL paths under `https://minios.local`. Gives persistence across separate runs without a real server or disk.

Important: the Python *namespace* (variables like `cpu`, `hardware`) does **not** persist between runs — only the cache-backed disk does. That means the bootstrap cell (which defines `MiniCPU`, `Hardware`, `assemble`, `shell`, etc.) has to be re-run at the start of every new session before `shell(...)` calls will work again. Files written to disk in a previous run will still be there once it's re-run.

### Shell
A simple command interpreter (`help`, `ls`, `cat`, `write`, `touch`, `rm`, `disk`, `asm`, `run`, `regs`, `mem`, `reset`, `screen`, `cls`, `key`, `keys`, `clear`).

## Instruction set (ChatCPU 2.1)

| Mnemonic | Opcode | Argument | Description |
|---|---|---|---|
| NOP | 0x00 | — | Do nothing |
| LDIA/B/C/D | 0x01–0x04 | 16-bit | Load constant into register |
| ADD | 0x05 | — | A += B |
| SUB | 0x06 | — | A -= B |
| INC | 0x07 | — | A += 1 |
| DEC | 0x08 | — | A -= 1 |
| STA | 0x09 | 16-bit address | Write A to memory |
| LDA | 0x0A | 16-bit address | Read memory into A |
| JMP | 0x0B | 16-bit address | Jump |
| JZ | 0x0C | 16-bit address | Jump if Z |
| JNZ | 0x0D | 16-bit address | Jump if not Z |
| CMP | 0x0E | — | Set flags from A - B |
| PUSH | 0x0F | — | Push A |
| POP | 0x10 | — | Pop into A |
| CALL | 0x11 | 16-bit address | Call subroutine |
| RET | 0x12 | — | Return |
| OUT | 0x13 | — | Write A as a character to the output buffer |
| IN | 0x14 | — | (stub, currently just clears A) |
| HLT | 0x15 | — | Halt the CPU |
| MOVAB | 0x16 | — | A = B |
| MOVBA | 0x17 | — | B = A |
| ADDC/ADDD | 0x18/0x19 | — | A += C / A += D |
| SUBC/SUBD | 0x1A/0x1B | — | A -= C / A -= D |
| XOR/AND/OR/NOT | 0x1C–0x1F | — | Bitwise logic on A |
| INP | 0x20 | 8-bit port | Read from I/O port into A |
| OUTP | 0x21 | 8-bit port | Write A to I/O port |

## Examples

Write an "X" at screen position (10, 5):

```asm
LDIA 'X'
LDIB 10
LDIC 5
OUTP 0x10
HLT
```

Read a key from the queue and print it:

```asm
INP 0x00
OUT
HLT
```

## Known limitations / next steps

- The physical browser keyboard isn't wired to `hardware.key()` yet — the input layer exists but the bridge is missing (likely solution: `MessageChannel` or a similar event listener feeding `hardware.key()` live).
- The `IN` instruction (0x14) is still a stub.
- No real graphics or color, just a text-based 32×16 character grid.
- No interrupts — everything is polling via I/O ports.
- `run()` has a cycle limit (default 1,000,000) to avoid infinite loops in the sandbox.
- Only the `caches`-backed disk survives between runs — the Python namespace resets, so the bootstrap cell must be re-executed each session (see Filesystem section above).
- Tied to ChatGPT's code interpreter environment specifically (relies on `js.caches` / `js.Request` / `js.Response` bindings exposed there) — porting to a plain local Python install would need a different persistence layer (e.g. a real file on disk or SQLite).

## Why this repo exists

Funnies :)
