"""SDK-launched POSIX shim: reap descendants even after the server exits cleanly.

The SDK creates this launcher's process group. A server may exit on stdin EOF
while leaving helpers alive; keep the group leader until all members are killed.
This is lifecycle management, not a security boundary against escaping daemons.
"""

import os
import signal
import subprocess
import sys
import time


def main():
    if os.getpid() != os.getpgrp():
        raise RuntimeError("MCP launcher requires its own SDK-created process group")
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        child = subprocess.Popen(sys.argv[1:])
        child.wait()
    finally:
        os.killpg(os.getpgrp(), signal.SIGTERM)
        time.sleep(0.2)
        os.killpg(os.getpgrp(), signal.SIGKILL)


if __name__ == "__main__":
    main()
