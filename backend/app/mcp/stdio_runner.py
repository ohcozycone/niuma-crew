"""子进程退出后仍保留进程组所有者，直到后代清理完成；不提供宿主隔离。"""

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
