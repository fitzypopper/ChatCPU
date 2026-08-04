import js

BASE = "https://chatcpu.local"
CACHE_NAME = "CHATCPU-MINIOS"

async def disk():
    return await js.caches.open(CACHE_NAME)

def request(path):
    if not path.startswith("/"):
        path = "/" + path
    return js.Request.new(BASE + path)

async def load(path):
    c = await disk()
    r = await c.match(request(path))
    if r is None:
        raise FileNotFoundError(path)
    return await r.text()

async def boot():
    print("=" * 50)
    print("             ChatCPU MiniOS")
    print("=" * 50)
    print()
    print("Loading /minios/shell.py...")

    source = await load("/minios/shell.py")

    ns = {
        "__builtins__": __builtins__,
        "__name__": "__main__",
    }

    exec(
        compile(source, "/minios/shell.py", "exec"),
        ns
    )

    print()
    print("Shell loaded from persistent disk")
    print()
    print("MiniOS READY")
    print()

    return ns

minios = await boot()

command = minios["command"]
cpu = minios["cpu"]
assemble = minios["assemble"]

print("command() READY")
print()
print("Try:")
print('await command("help")')
print('await command("ls")')
print('await command("regs")')
