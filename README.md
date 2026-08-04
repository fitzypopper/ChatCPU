# ChatCPU

### A homemade 16 bit computer built inside ChatGPT's Python code runner

> **Very early access · Proof of concept**

ChatCPU is a homemade 16 bit computer built entirely in Python and designed to run inside ChatGPT's built in Python code runner

It includes its own CPU, RAM, ROM, assembler, shell, persistent filesystem and I/O system

There is no external server and no third party runtime required

The project runs inside the sandboxed browser based Python environment provided by ChatGPT rather than as a normal local Python application

Its persistent filesystem uses the browser's Cache Storage API, allowing files and game state to survive between separate executions as long as the cache is not cleared

This repository is primarily a backup of the development process and source code from a long conversation with an AI assistant

> if big ai gets mad and removes me from the face of the earth at least the code survives

---

## Status

**ChatCPU 2.1 — current version**

ChatCPU currently has:

* 16 bit CPU
* 64 KiB RAM
* 64 KiB ROM
* 16 bit addressing
* Registers `A`, `B`, `C`, `D`, `PC` and `SP`
* `Z`, `CF` and `N` flags
* Custom assembler
* Labels and two pass assembly
* 8 bit and 16 bit instruction arguments
* I/O ports
* Text screen
* Keyboard input layer
* Random number I/O
* Shell
* Persistent filesystem
* Program loading and execution
* Memory and register inspection
* Persistent game state

And yes

**ChatCPU can already run games**

We have successfully built a persistent Snake prototype using ChatCPU's RAM and I/O model

The current Snake prototype supports:

* Snake movement
* Direction changes
* Food
* Score
* Growth
* Wall collision
* Self collision
* Persistent save state
* Persistent input through the filesystem
* Keyboard I/O abstraction

Physical browser keyboard input is not wired directly into the CPU yet

---

# Architecture

## CPU

The CPU is implemented as a fetch decode execute loop

Programs are loaded into ROM and executed using the program counter

Most instructions are one opcode byte followed by either no argument, an 8 bit argument or a 16 bit argument

The stack grows downward from `0xFFFF`

Arithmetic and logic instructions update the CPU flags where appropriate

### Registers

| Register | Purpose                  |
| -------- | ------------------------ |
| `A`      | Main accumulator         |
| `B`      | General purpose register |
| `C`      | General purpose register |
| `D`      | General purpose register |
| `PC`     | Program counter          |
| `SP`     | Stack pointer            |
| `Z`      | Zero flag                |
| `CF`     | Carry flag               |
| `N`      | Negative flag            |

---

# Memory

ChatCPU has:

```text
64 KiB RAM
64 KiB ROM
```

Both use 16 bit addressing

RAM is used for program data, game state, variables and other runtime information

ROM contains the currently loaded program

16 bit reads and writes are constructed from two 8 bit operations using little endian byte order

---

# I/O

ChatCPU uses port based I/O

|   Port | Name             | Description                               |
| -----: | ---------------- | ----------------------------------------- |
| `0x00` | `PORT_KEY`       | Read the next key from the keyboard queue |
| `0x01` | `PORT_KEY_STATE` | Check whether a key is waiting            |
| `0x10` | `PORT_SCREEN`    | Write to the text screen                  |
| `0x20` | `PORT_RANDOM`    | Random value from `0–255`                 |

The screen is currently a **32×16 text based display**

There are no real graphics or colors yet

---

# Assembler

ChatCPU has a custom two pass assembler

### Pass 1

The assembler:

* Reads the source
* Calculates instruction sizes
* Tracks the program counter
* Registers labels

### Pass 2

The assembler:

* Resolves labels
* Parses arguments
* Emits machine code

The assembler supports both 8 bit and 16 bit arguments depending on the instruction

Character literals are supported:

```asm
LDIA 'H'
```

which loads the ASCII value of `H`

---

# Filesystem

ChatCPU has a persistent virtual filesystem backed by the browser's Cache Storage API

Files are stored as `Request` / `Response` pairs under a fixed cache

The filesystem behaves approximately like a tiny virtual disk

Example paths:

```text
/minios/version.txt
/minios/config.cfg
/minios/kernel.py
/minios/shell.py
/minios/programs/hello.asm
/minios/programs/snake.hex
/minios/snake.save
```

The important distinction is:

**The filesystem persists**

**The Python namespace does not**

Variables such as:

```python
cpu
hardware
shell
```

disappear when a new execution starts

Files written to Cache Storage remain available

Because of this, the bootstrap/runtime code must be loaded again when starting a new Python execution

---

# Shell

MiniOS currently provides a shell with commands including:

```text
help
ls
cat
write
touch
rm
disk
version
asm
run
regs
mem
reset
screen
cls
key
keys
clear
```

Example:

```text
minios:~$ ls
```

Programs can be assembled and executed through the shell

---

# Instruction Set

## ChatCPU 2.1

| Mnemonic | Opcode | Argument   | Description             |
| -------- | -----: | ---------- | ----------------------- |
| `NOP`    | `0x00` | —          | Do nothing              |
| `LDIA`   | `0x01` | 16 bit     | Load constant into A    |
| `LDIB`   | `0x02` | 16 bit     | Load constant into B    |
| `LDIC`   | `0x03` | 16 bit     | Load constant into C    |
| `LDID`   | `0x04` | 16 bit     | Load constant into D    |
| `ADD`    | `0x05` | —          | `A += B`                |
| `SUB`    | `0x06` | —          | `A -= B`                |
| `INC`    | `0x07` | —          | `A += 1`                |
| `DEC`    | `0x08` | —          | `A -= 1`                |
| `STA`    | `0x09` | 16 bit     | Store A to RAM          |
| `LDA`    | `0x0A` | 16 bit     | Load RAM into A         |
| `JMP`    | `0x0B` | 16 bit     | Jump                    |
| `JZ`     | `0x0C` | 16 bit     | Jump if zero            |
| `JNZ`    | `0x0D` | 16 bit     | Jump if not zero        |
| `CMP`    | `0x0E` | —          | Compare A and B         |
| `PUSH`   | `0x0F` | —          | Push A                  |
| `POP`    | `0x10` | —          | Pop into A              |
| `CALL`   | `0x11` | 16 bit     | Call subroutine         |
| `RET`    | `0x12` | —          | Return                  |
| `OUT`    | `0x13` | —          | Output A as a character |
| `IN`     | `0x14` | —          | Input stub              |
| `HLT`    | `0x15` | —          | Halt CPU                |
| `MOVAB`  | `0x16` | —          | `A = B`                 |
| `MOVBA`  | `0x17` | —          | `B = A`                 |
| `ADDC`   | `0x18` | —          | `A += C`                |
| `ADDD`   | `0x19` | —          | `A += D`                |
| `SUBC`   | `0x1A` | —          | `A -= C`                |
| `SUBD`   | `0x1B` | —          | `A -= D`                |
| `XOR`    | `0x1C` | —          | Bitwise XOR             |
| `AND`    | `0x1D` | —          | Bitwise AND             |
| `OR`     | `0x1E` | —          | Bitwise OR              |
| `NOT`    | `0x1F` | —          | Bitwise NOT             |
| `INP`    | `0x20` | 8 bit port | Read I/O port into A    |
| `OUTP`   | `0x21` | 8 bit port | Write A to I/O port     |

---

# Example Programs

## Hello World

Character output:

```asm
LDIA 'H'
OUT

LDIA 'i'
OUT

HLT
```

This produces:

```text
Hi
```

---

## Screen Output

Write an `X` to screen position `(10, 5)`:

```asm
LDIA 'X'
LDIB 10
LDIC 5
OUTP 0x10
HLT
```

---

## Keyboard

Read a key from the keyboard queue:

```asm
INP 0x00
OUT
HLT
```

---

# Snake

One of the first actual games being developed for ChatCPU is Snake

The prototype has already demonstrated:

```text
Persistent RAM state
        ↓
Snake position
        ↓
Direction
        ↓
I/O keyboard input
        ↓
Movement
        ↓
Collision detection
        ↓
Food
        ↓
Score
        ↓
Persistent save
```

The current implementation is still a hybrid prototype, but the important parts of the architecture are already there

The long term goal is to move more of the game logic from Python into actual ChatCPU machine code

---

# Known Limitations

ChatCPU is very much a work in progress

### Browser keyboard

The keyboard input layer exists but physical browser keyboard events are not directly connected to the CPU yet

Currently the input system can be driven through the persistent sandbox filesystem

A future implementation could use something like `MessageChannel` or another browser event bridge

### `IN`

The original `IN` instruction (`0x14`) is still a stub

The actual I/O interface is currently handled through `INP` and `OUTP`

### Graphics

There is no real graphics hardware

The current display is a text based character grid

No:

* sprites
* pixels
* colors
* framebuffer
* GPU

yet

### Interrupts

There are no hardware interrupts

Programs currently use polling

### Execution limit

Programs have a cycle limit to prevent accidental infinite loops from hanging the sandbox

### Persistence

Only the Cache Storage filesystem survives between executions

The Python namespace is reset

### Environment dependency

ChatCPU relies on browser APIs exposed by the ChatGPT Python runner, including:

```text
js.caches
js.Request
js.Response
```

Because of this, it is **not currently a normal standalone Python application**

Porting ChatCPU to local Python would require replacing the persistence layer with something like:

```text
real files
SQLite
or another storage backend
```

---

# Can It Run DOOM?

**No**

Not right now 😭

DOOM would require substantially more than the current ChatCPU provides

Major missing pieces include:

* Real graphics
* A framebuffer
* Fast rendering
* More advanced CPU instructions
* Real-time input
* A proper executable format
* Much more performance
* A compatible runtime/environment

The current text display and sandboxed input system are nowhere near enough

That said

**ChatCPU can already run Snake**

So we're getting there one tiny homemade CPU at a time

---

# Why Does This Exist?

Funnies :)

Also because building a fake computer inside a Python code runner is objectively hilarious

ChatCPU started as a tiny 8 bit experiment with:

```text
256 bytes RAM
```

and eventually became:

```text
ChatCPU 2.1

16 bit CPU
64 KiB RAM
64 KiB ROM
persistent filesystem
assembler
shell
I/O
games
```

The original machine was basically:

```text
793 |

MiniCPU 8-bit

256 bytes RAM

Persistent filesystem
```

Now we're here

```text
ChatCPU MiniOS

CPU: ChatCPU

RAM: 65536 bytes
ROM: 65536 bytes

Persistent filesystem: Cache
```

And somehow Snake works

😭
