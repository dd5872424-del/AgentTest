"""
CLI 入口：统一分发到各类脚本（chat/db_admin/未来更多）
"""
import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from cli import chat, db_admin


def main():
    """
    用法：
      python backend/main.py chat
      python backend/main.py db-admin <args...>
    """
    if len(sys.argv) < 2:
        print("用法:")
        print("  python backend/main.py chat")
        print("  python backend/main.py db-admin <args...>")
        return

    command = sys.argv[1]
    if command == "chat":
        chat.main()
        return
    if command == "db-admin":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        db_admin.main()
        return

    print(f"未知命令: {command}")


if __name__ == "__main__":
    main()
