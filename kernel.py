# ChatCPU MiniOS kernel

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

print("ChatCPU kernel loaded")
print(f"CPU: {CPU_NAME}")
print(f"RAM: {RAM_SIZE} bytes")
print(f"ROM: {ROM_SIZE} bytes")
print(f"I/O: {IO_PORTS} ports")
