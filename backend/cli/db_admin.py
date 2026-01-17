"""
数据库管理脚本：查看/删除 app.db 与 content.db 条目
"""
import argparse
import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import Runtime


def list_conversations(runtime: Runtime):
    items = runtime.conversations.list_all()
    if not items:
        print("(无会话)")
        return
    for item in items:
        print(f"{item.get('id')}\t{item.get('graph_name')}\t{item.get('title')}")


def delete_conversation(runtime: Runtime, conv_id: str):
    ok = runtime.delete_conversation(conv_id)
    if ok:
        print(f"已删除会话: {conv_id}")
    else:
        print(f"未找到会话: {conv_id}")


def delete_all_conversations(runtime: Runtime, force: bool):
    if not force:
        print("请添加 --force 确认删除全部会话")
        return
    count = runtime.clear_all_conversations()
    print(f"已删除全部会话: {count} 条")


def list_contents(runtime: Runtime, content_type: str, scope: str, tags: list[str] | None):
    items = runtime.contents.list(content_type, scope=scope, tags=tags)
    if not items:
        print("(无内容)")
        return
    for item in items:
        tags_text = ",".join(item.get("tags") or [])
        print(f"{item.get('id')}\t{item.get('type')}\t{item.get('scope')}\t{tags_text}")


def delete_content(runtime: Runtime, content_type: str, content_id: str, scope: str):
    ok = runtime.contents.delete(content_type, content_id, scope=scope)
    if ok:
        print(f"已删除内容: {content_type}/{content_id} (scope={scope})")
    else:
        print(f"未找到内容: {content_type}/{content_id} (scope={scope})")


def delete_contents_by_tags(
    runtime: Runtime,
    content_type: str,
    scope: str,
    tags: list[str],
    force: bool,
):
    if not tags:
        print("请提供 tags")
        return
    if not force:
        print("请添加 --force 确认删除")
        return
    items = runtime.contents.list(content_type, scope=scope, tags=tags)
    if not items:
        print("未找到匹配内容")
        return
    deleted = 0
    for item in items:
        if runtime.contents.delete(content_type, item["id"], scope=scope):
            deleted += 1
    print(f"已删除内容: {deleted} 条 (type={content_type}, scope={scope}, tags={','.join(tags)})")


def main():
    # 无参数时进入交互式菜单
    if len(sys.argv) == 1:
        runtime = Runtime()
        menu_text = (
            "\n数据库管理菜单\n"
            "  1. 列出会话(app.db)\n"
            "  2. 删除会话(app.db)\n"
            "  3. 删除全部会话(app.db)\n"
            "  4. 列出内容(content.db)\n"
            "  5. 删除内容(content.db)\n"
            "  6. 按标签删除内容(content.db)\n"
            "  0. 退出\n"
        )
        print(menu_text)
        while True:
            choice = input("选择操作(输入 m 查看菜单): ").strip()
            if choice.lower() == "m":
                print(menu_text)
                continue
            if choice == "0":
                return
            if choice == "1":
                list_conversations(runtime)
                continue
            if choice == "2":
                conv_id = input("会话 ID: ").strip()
                if conv_id:
                    delete_conversation(runtime, conv_id)
                continue
            if choice == "3":
                confirm = input("确认删除全部会话？输入 YES: ").strip()
                delete_all_conversations(runtime, confirm == "YES")
                continue
            if choice == "4":
                content_type = input("内容类型(如 world_info/preset): ").strip()
                scope = input("scope(默认 global): ").strip() or "global"
                tags = input("tags(逗号分隔，可空): ").strip()
                list_contents(
                    runtime,
                    content_type,
                    scope,
                    tags.split(",") if tags else None,
                )
                continue
            if choice == "5":
                content_type = input("内容类型: ").strip()
                content_id = input("内容 ID: ").strip()
                scope = input("scope(默认 global): ").strip() or "global"
                if content_type and content_id:
                    delete_content(runtime, content_type, content_id, scope)
                continue
            if choice == "6":
                content_type = input("内容类型: ").strip()
                scope = input("scope(默认 global): ").strip() or "global"
                tags_text = input("tags(逗号分隔): ").strip()
                confirm = input("确认删除？输入 YES: ").strip()
                if content_type and tags_text:
                    delete_contents_by_tags(
                        runtime,
                        content_type,
                        scope,
                        tags_text.split(","),
                        confirm == "YES",
                    )
                continue
            print("无效选择")
        return

    parser = argparse.ArgumentParser(description="数据库管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub_list_app = sub.add_parser("list-app", help="列出 app.db 会话")
    sub_list_app.set_defaults(func=lambda rt, args: list_conversations(rt))

    sub_del_app = sub.add_parser("delete-app", help="删除 app.db 会话")
    sub_del_app.add_argument("id", help="会话 ID")
    sub_del_app.set_defaults(func=lambda rt, args: delete_conversation(rt, args.id))

    sub_del_all_app = sub.add_parser("delete-all-app", help="删除 app.db 全部会话")
    sub_del_all_app.add_argument("--force", action="store_true", help="确认删除全部会话")
    sub_del_all_app.set_defaults(
        func=lambda rt, args: delete_all_conversations(rt, args.force)
    )

    sub_list_content = sub.add_parser("list-content", help="列出 content.db 条目")
    sub_list_content.add_argument("type", help="内容类型，如 world_info/preset/character")
    sub_list_content.add_argument("--scope", default="global", help="作用域，默认 global")
    sub_list_content.add_argument("--tags", default=None, help="按标签筛选，逗号分隔")
    sub_list_content.set_defaults(
        func=lambda rt, args: list_contents(
            rt,
            args.type,
            args.scope,
            args.tags.split(",") if args.tags else None,
        )
    )

    sub_del_content = sub.add_parser("delete-content", help="删除 content.db 条目")
    sub_del_content.add_argument("type", help="内容类型")
    sub_del_content.add_argument("id", help="内容 ID")
    sub_del_content.add_argument("--scope", default="global", help="作用域，默认 global")
    sub_del_content.set_defaults(
        func=lambda rt, args: delete_content(rt, args.type, args.id, args.scope)
    )

    sub_del_by_tags = sub.add_parser("delete-content-by-tags", help="按标签删除 content.db 条目")
    sub_del_by_tags.add_argument("type", help="内容类型")
    sub_del_by_tags.add_argument("--scope", default="global", help="作用域，默认 global")
    sub_del_by_tags.add_argument("--tags", required=True, help="标签，逗号分隔")
    sub_del_by_tags.add_argument("--force", action="store_true", help="确认删除")
    sub_del_by_tags.set_defaults(
        func=lambda rt, args: delete_contents_by_tags(
            rt,
            args.type,
            args.scope,
            args.tags.split(","),
            args.force,
        )
    )

    args = parser.parse_args()
    runtime = Runtime()
    args.func(runtime, args)


if __name__ == "__main__":
    main()
