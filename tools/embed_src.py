#!/usr/bin/env python3
"""Embed cpu.py's own source into cpu.py as _CPU_SRC (gzip + base64).

In the ChatGPT sandbox, pasted code has no readable __file__, so boot()
cannot recover its source from disk to save it to the cache. This script
keeps a compressed copy of cpu.py inside cpu.py; boot() falls back to it.

Usage:
    python3 tools/embed_src.py [cpu.py]

Run again after editing cpu.py. test_cpu.py verifies the blob is fresh.
"""
import base64
import gzip
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "cpu.py"

with open(PATH, encoding="utf-8") as f:
    src = f.read()

m = re.search(r"(?m)^_CPU_SRC = .*$\n?", src)
if m:
    body = src[:m.start()] + src[m.end():]
else:
    body = src

blob = base64.b64encode(gzip.compress(body.encode("utf-8"), 9)).decode("ascii")
line = f'_CPU_SRC = "{blob}"\n'

if m:
    out = src[:m.start()] + line + src[m.end():]
else:
    out = src + line

with open(PATH, "w", encoding="utf-8") as f:
    f.write(out)

print(f"embedded {len(blob)} chars of gzip+base64 source into {PATH}")
