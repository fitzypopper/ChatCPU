# ChatCPU

**ChatCPU is a homemade 16 bit computer built entirely in Python and designed to run inside ChatGPT's Python code runner**

> ⚠️ **Very early access / proof of concept**

ChatCPU contains a custom CPU, RAM, ROM, assembler, shell, persistent filesystem and memory mapped I/O.

It does **not** require external packages or a server. The project is specifically designed around the sandboxed Python environment available in ChatGPT.

The persistent filesystem uses the browser's **Cache Storage API**, meaning files can survive between separate Python runs even though the Python runtime itself is reset.

## Getting started

ChatCPU is a single file (`cpu.py`) that you paste directly into the Python code runner.

1. Open ChatGPT's Python code runner
2. Paste the whole `cpu.py` content and run it (it only *defines* the system — no output yet)
3. Boot it and it installs itself into the persistent filesystem (silently):
   ```python
   await boot()
   ```
    This writes `/minios/cpu.py` plus the default files to the cache. `boot()` prints nothing — run commands via `shell()` or the prompt-style `cmd()`.
4. From then on, you don't paste `cpu.py` again — just use this small loader, and add your commands after it:
   ```python
   import js
   exec(await (await (await js.caches.open('ChatCPU-OS-V21')).match(js.Request.new('https://ChatCPU.local/minios/cpu.py'))).text())
   await boot()
   print(await cmd('ls'))
   print(await cmd('snake'))
   ```
   `cmd('...')` returns the output prefixed with a terminal prompt:
   ```
   MiniOS@ChatCPU~$ ls
   minios/
   prog/
   MiniOS@ChatCPU~$ snake
   === ChatCPU Snake ===
   ...
   ```
   Use `shell('...')` when you want the raw output without the prompt.
   (Single-line form: `import js;exec(await (await (await js.caches.open('ChatCPU-OS-V21')).match(js.Request.new('https://ChatCPU.local/minios/cpu.py'))).text());await boot();print(await cmd('ls'))`)

### How the self-install works

The sandbox never gives pasted code a readable `__file__`, so `boot()` cannot read its own source from disk to save it. Instead, `cpu.py` carries a gzip+base64 copy of itself (`_CPU_SRC`); `boot()` uses the real file when it can and falls back to the embedded copy otherwise, so the cache save always succeeds.

If you edit `cpu.py`, refresh the embedded copy before pasting it again:

```
python3 tools/embed_src.py
```

`test_cpu.py` verifies the embedded copy is up to date (and that a loader-run `boot()` can re-save itself), so the test suite will fail loudly if you forget.

The important thing to understand is that **the Python namespace is reset between every run** — so `boot()` and all shell commands must run in the *same code block* as the loader (or `cpu.py`). The persistent filesystem, however, survives between runs; `boot()` only writes the default files when they are missing.

## Current status

**ChatCPU 2.x**

The project is a single-file implementation (`cpu.py`) containing:

* 16 bit CPU architecture
* A, B, C and D registers
* Program Counter and Stack Pointer
* Zero, Carry and Negative flags
* 64 KiB RAM
* 64 KiB ROM
* 16 bit addressing
* Custom assembler with labels
* Memory mapped I/O
* Text based display
* Keyboard input queue
* Random number I/O
* Persistent filesystem
* MiniOS shell
* Assembly programs
* CPU register and memory inspection

## Architecture

### CPU

ChatCPU uses a custom 16 bit CPU architecture.

The CPU contains:

```text
A   B   C   D
PC  SP
Z   CF  N
```

The CPU executes programs stored in ROM and uses RAM for runtime data.

The stack grows downward from `0xFFFF`.

### Memory

```text
RAM: 64 KiB
ROM: 64 KiB
Address size: 16 bit
```

16 bit values are stored using two bytes in little endian order.

### Display

The current text display is:

```text
32 × 16 characters
```

It is a simple text framebuffer rather than a graphical display.

### I/O

Current I/O ports include:

|   Port | Name             | Purpose                    |
| -----: | ---------------- | -------------------------- |
| `0x00` | `PORT_KEY`       | Read keyboard input        |
| `0x01` | `PORT_KEY_STATE` | Check whether input exists |
| `0x10` | `PORT_SCREEN`    | Write to the text display  |
| `0x20` | `PORT_RANDOM`    | Random number input        |

## Filesystem

ChatCPU uses the browser's Cache Storage API as its persistent disk.

The filesystem is represented using `Request` and `Response` objects stored inside a Cache.

Example layout (written to persistent storage by `boot()`):

```text
/minios/
├── cpu.py
├── version.txt
├── config.cfg
├── system.cfg
├── snake.save
└── programs/
    ├── demo.asm
    └── hello.asm
```

The exact files may change during development.

## Shell

MiniOS provides commands for interacting with the system.

Common commands include:

```text
help
pwd
cd <path>
ls [-l] [path]
cat <file>
write <file> <text>
append <file> <text>
touch <file>
cp <src> <dst>
mv <src> <dst>
mkdir <path>
rmdir <path>
rm [-r] <path>
echo <text>
disk

regs
mem <address> [length]
reset

asm <file>
run <file> [cycles]
step <file> [cycles]

screen
cls
key <character>
keys

snake
exec <file>

clear
```

Paths are resolved against the current directory (`/` by default): `.`, `..`, and absolute paths all work, e.g. `cd /minios/programs`, then `ls ..`, `write hello2.asm 'LDIA 65\nOUT\nHLT'`.

The working directory survives between runs — `cd` saves it to `/minios/.cwd` and `boot()` restores it, so you can `cd` in one run and continue in the next.

For example:

```text
ls
```

lists files on the persistent ChatCPU filesystem.

```text
regs
```

shows the CPU registers and flags.

```text
mem 0x0000
```

inspects RAM.

## Assembly

ChatCPU has its own assembly language.

A simple program can look like:

```asm
LDIA 'H'
OUT

LDIA 'i'
OUT

HLT
```

The assembler converts the source into ChatCPU machine code.

Programs are stored under:

```text
programs/
```

## Instruction set

The instruction set is still evolving.

Some of the currently implemented instructions include:

| Mnemonic | Opcode | Description              |
| -------- | -----: | ------------------------ |
| `NOP`    | `0x00` | No operation             |
| `LDIA`   | `0x01` | Load 16 bit value into A |
| `LDIB`   | `0x02` | Load 16 bit value into B |
| `ADD`    | `0x05` | Add B to A               |
| `SUB`    | `0x06` | Subtract B from A        |
| `INC`    | `0x07` | Increment A              |
| `DEC`    | `0x08` | Decrement A              |
| `OUT`    | `0x13` | Output A as a character  |
| `HLT`    | `0x15` | Halt CPU                 |
| `INP`    | `0x20` | Read an I/O port         |
| `OUTP`   | `0x21` | Write to an I/O port     |

The instruction set and implementation are actively changing, so this table may not always perfectly match the latest development version.

## Example

A basic Hello World program:

```asm
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
```

## Snake

One of the current test programs is a Snake implementation.

It uses ChatCPU's:

* keyboard input
* screen output
* CPU execution
* RAM
* persistent storage

The game has already been tested running inside the ChatGPT Python environment.

Current saved game state can be stored separately from the Python runtime.

## Known limitations

* ChatCPU depends on the Python environment provided by ChatGPT
* It is not currently a normal standalone Python application
* The `js` bindings used by the persistent filesystem are environment specific
* The Python namespace is reset between runs
* The Cache Storage filesystem can persist between runs
* The physical browser keyboard is not automatically connected to the CPU
* Graphics are currently limited to a text based display
* There are no proper hardware interrupts
* CPU execution has a cycle limit to prevent infinite loops from locking the runner
* The instruction set is still under development
* Some files in the development filesystem may be incomplete or experimental

## Can it run DOOM?

No.

Not *yet* anyway

A real DOOM port would require substantially more complete CPU functionality, graphics, input, memory management and a much more capable runtime environment.

Getting persistent storage working in the sandbox was already kind of insane.

## Why does this exist?

Because apparently building a fake computer inside ChatGPT's Python runner sounded like a good idea.

Also funnies :)
