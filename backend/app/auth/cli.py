"""Local account maintenance. Passwords are never command-line arguments."""

import argparse
import getpass

from sqlalchemy.exc import OperationalError

from app.auth.service import AuthService
from app.config import load_config
from app.infrastructure.database.session import Database


def read_password() -> str:
    password = getpass.getpass("密码（8～20 个字符）：")
    if password != getpass.getpass("再次输入密码："):
        raise ValueError("两次密码不一致。")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="本机账号维护")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in (
        "create-admin",
        "reset-password",
        "disable-user",
        "enable-user",
        "revoke-sessions",
    ):
        commands.add_parser(name).add_argument("username")
    commands.add_parser("cleanup-sessions")
    args = parser.parse_args()
    config = load_config()
    database = Database(config.database)
    try:
        service = AuthService(database, config.auth)
        if args.operation == "cleanup-sessions":
            print(f"已清理 {service.cleanup()} 条失效会话。")
        elif args.operation == "create-admin":
            service.initialize_admin(args.username, read_password())
            print("管理员已创建。")
        else:
            password = read_password() if args.operation == "reset-password" else None
            service.maintain_user(args.username, args.operation, password)
            print("账号已更新，旧会话已撤销。")
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    except OperationalError:
        parser.exit(1, "数据库不可用，请先执行迁移并检查数据库是否被占用。\n")
    finally:
        database.close()


if __name__ == "__main__":
    main()
