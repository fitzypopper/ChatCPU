import asyncio
import ast
import base64
import gzip
import re
import sys
import types
from urllib.parse import urlsplit, urlunsplit

# ============================================================
# MOCK js CacheStorage
# (Replicates browser URL normalization: hosts are lowercased.)
# ============================================================

def _normalize(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, parts.query, parts.fragment))

class _Response:
    def __init__(self, text):
        self._text = text
    @classmethod
    def new(cls, text):
        return cls(text)
    async def text(self):
        return self._text

class _Cache:
    def __init__(self):
        self.store = {}
    async def put(self, request, response):
        self.store[request.url] = response
    async def match(self, request):
        return self.store.get(request.url)
    async def keys(self):
        return [types.SimpleNamespace(url=url) for url in self.store]
    async def delete(self, request):
        self.store.pop(request.url, None)

class _Request:
    def __init__(self, url):
        self.url = _normalize(url)
    @classmethod
    def new(cls, url):
        return cls(url)

class _Caches:
    def __init__(self):
        self.caches = {}
    async def open(self, name):
        return self.caches.setdefault(name, _Cache())

MOCK_CACHES = _Caches()

js = types.SimpleNamespace(
    caches=MOCK_CACHES,
    Request=_Request,
    Response=_Response,
)
sys.modules["js"] = js

# ============================================================
# LOAD cpu.py INTO A FRESH MODULE GLOBALS
# ============================================================

src = open("cpu.py").read()
g = {"__file__": "cpu.py", "__name__": "cpu"}
exec(compile(src, "cpu.py", "exec"), g)
shell = g["shell"]
boot = g["boot"]


def read_path(path):
    key = _normalize("https://ChatCPU.local" + path)
    value = MOCK_CACHES.caches["ChatCPU-OS-V21"].store.get(key)
    return value._text if value else None


passed = 0

def check(label, cond):
    global passed
    assert cond, f"FAIL: {label}"
    passed += 1
    print(f"  ok  {label}")


async def main():
    print("== BOOT ==")
    await boot()
    check("default files written", read_path("/minios/version.txt") is not None)
    check("snake.save seeded", read_path("/minios/snake.save") is not None)
    check("hello.asm seeded", read_path("/minios/programs/hello.asm") is not None)
    check("cpu.py saved to cache", read_path("/minios/cpu.py") is not None)

    fresh = re.sub(r"(?m)^_CPU_SRC = .*$\n?", "", src)
    embedded = gzip.decompress(base64.b64decode(g["_CPU_SRC"])).decode("utf-8")
    check("embedded source is fresh", embedded == fresh)

    print("== WRITE / APPEND (multi-line) ==")
    await shell("write /prog/a.asm 'LDIA 65\\nOUT\\nLDIA 66\\nOUT\\nLDIA 67\\nOUT\\nHLT'")
    text = read_path("/prog/a.asm")
    check("write converts \\n", text == "LDIA 65\nOUT\nLDIA 66\nOUT\nLDIA 67\nOUT\nHLT")
    await shell("append /prog/a.asm '; trailing\\nLDIB 1'")
    check("append adds line", read_path("/prog/a.asm").endswith("\n; trailing\nLDIB 1"))

    print("== CD / PWD / DIRS ==")
    check("cd relative", (await shell("cd /minios")) == "/minios")
    check("pwd", (await shell("pwd")) == "/minios")
    check("cd ..", (await shell("cd ..")) == "/")
    check("cd deep then ..", (await shell("cd /minios/programs")) == "/minios/programs")
    check("cd .. ..", (await shell("cd ../..")) == "/")
    check("cd missing fails", "no such directory" in await shell("cd /nope"))

    print("== CWD PERSISTENCE ==")
    await shell("cd /minios/programs")
    g4 = {"__name__": "minios_cpu_fresh"}
    exec(compile(read_path("/minios/cpu.py"), "minios/cpu.py", "exec"), g4)
    await g4["boot"]()
    check("cwd survives fresh run", (await g4["shell"]("pwd")) == "/minios/programs")
    check("relative ls after restore", "programs/" in await g4["shell"]("ls .."))
    await shell("cd /")

    out = await shell("mkdir /newdir")
    check("mkdir", out == "OK")
    out = await shell("ls /")
    check("ls shows dirs", "newdir/" in out)
    out = await shell("ls -l /minios")
    check("ls -l sizes", "cpu.py" in out and "bytes" in out)
    await shell("write /newdir/x.txt 'hello'")
    check("relative write after cd", read_path("/newdir/x.txt") == "hello")
    check("rmdir nonempty fails", "not empty" in await shell("rmdir /newdir"))
    check("rm -r", "removed" in await shell("rm -r /newdir"))
    check("rmdir after rm -r", "no such directory" in await shell("rmdir /newdir"))

    print("== MV / CP / ECHO ==")
    await shell("write /prog/src.txt 'data'")
    check("cp", (await shell("cp /prog/src.txt /prog/copy.txt")) == "OK")
    check("cp content", read_path("/prog/copy.txt") == "data")
    check("mv", (await shell("mv /prog/src.txt /prog/moved.txt")) == "OK")
    check("mv moved", read_path("/prog/moved.txt") == "data")
    check("mv removed src", read_path("/prog/src.txt") is None)
    check("echo", (await shell("echo hello world")) == "hello world")

    print("== CMD (prompt style) ==")
    out = await g["cmd"]("echo hello world")
    check("cmd echoes prompt", out == "MiniOS@ChatCPU~$ echo hello world\nhello world")

    print("== RUN / STEP ==")
    out = await shell("run /prog/a.asm")
    check("run outputs ABC", out.endswith("ABC"))
    out = await shell("run /prog/a.asm 5")
    check("run cycle limit", "CPU CYCLE LIMIT" in out)
    out = await shell("step /prog/a.asm 2")
    check("step shows PC", "PC =" in out and "STEPPED 2 CYCLES" in out)

    print("== HELLO.ASM ==")
    out = await shell("run /minios/programs/hello.asm")
    check("hello outputs", out.endswith("Hello ChatCPU"))

    print("== SNAKE ==")
    out = await shell("snake")
    check("snake tick ok", "CPU" in out)
    check("snake saved state", read_path("/minios/snake.save") is not None)
    await shell("write /minios/shell/input.txt UP")
    out = await shell("snake")
    check("snake reads input", "Input: UP" in out)

    print("== EXEC (python file) ==")
    await g["write_file"]("/prog/py.txt", 'print("from exec")')
    out = await shell("exec /prog/py.txt")
    check("exec sync python", "from exec" in out)
    await g["write_file"](
        "/prog/async.txt",
        'x = await write_file("/prog/async_made.txt", 42)\nprint("async exec ok")',
    )
    out = await shell("exec /prog/async.txt")
    check("exec async python", "async exec ok" in out)
    check("async exec wrote file", read_path("/prog/async_made.txt") is not None)

    print("== LOADER WORKFLOW ==")
    src2 = read_path("/minios/cpu.py")
    g2 = {"__name__": "minios_cpu"}
    exec(compile(src2, "minios/cpu.py", "exec"), g2)
    await g2["boot"]()
    out = await g2["shell"]("run /prog/a.asm")
    check("loader runs cpu from cache", out.endswith("ABC"))
    check("loader boot re-saves cpu.py", "_CPU_SRC =" in read_path("/minios/cpu.py"))

    print("== PASTED LOADER (exact expression) ==")
    pasted = (
        "import js\n"
        "exec(await (await (await js.caches.open('ChatCPU-OS-V21')).match(js.Request.new('https://ChatCPU.local/minios/cpu.py'))).text())\n"
        "await boot()\n"
        "await shell('run /prog/a.asm')"
    )
    g3 = {}
    loader_code = compile(pasted, "<pasted-loader>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    await eval(loader_code, g3)
    check("pasted loader defines shell", callable(g3.get("shell")))
    out = await g3["shell"]("run /prog/a.asm")
    check("pasted loader runs cpu from cache", out.endswith("ABC"))

    print()
    print(f"ALL {passed} CHECKS PASSED")


asyncio.run(main())
