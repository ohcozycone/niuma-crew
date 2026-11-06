"""Inspect cleanup debt and reconcile an expired ambiguous create request."""

import argparse
import json

from app.config import load_config
from app.environments.service import SandboxService
from app.infrastructure.database.session import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolve-absent")
    parser.add_argument("--confirm-absent", action="store_true")
    args = parser.parse_args()
    config = load_config()
    database = Database(config.database)
    service = SandboxService(database, config.sandbox, lambda: [])
    try:
        if args.resolve_absent:
            if not args.confirm_absent:
                parser.error("先核对 OpenSandbox 请求日志与实际资源，再使用 --confirm-absent。")
            service.confirm_absent(args.resolve_absent)
        print(json.dumps(service.resources(), ensure_ascii=False, indent=2))
    finally:
        database.close()


if __name__ == "__main__":
    main()
