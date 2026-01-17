"""
CLI 聊天入口：从 main.py 拆出，便于日常使用
"""
import json
import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core import Runtime
from core.config import get_config


def main():
    """主函数"""
    runtime = Runtime()

    print("=" * 50)
    print("LangGraph 聊天框架演示")
    print("=" * 50)
    print()
    mode = input("选择模式 (1 新建 / 2 历史，默认1): ").strip() or "1"
    if mode == "2":
        conv_id, graph_name = _select_conversation(runtime)
        if not conv_id:
            mode = "1"
    if mode != "2":
        print("可用的图：")
        print("  1. default       - 默认对话")
        print("  2. roleplay      - 角色扮演")
        print("  3. with_commands - 带指令解析")
        print("  4. with_worldinfo - 世界观检索")
        print()

        # 选择图
        choice = input("选择图 (1/2/3/4，默认1): ").strip() or "1"
        graph_map = {
            "1": "default",
            "2": "roleplay",
            "3": "with_commands",
            "4": "with_worldinfo",
        }
        graph_name = graph_map.get(choice, "default")

        # 创建会话
        content_refs = None
        if graph_name == "with_worldinfo":
            # 加载 TestBook 世界观条目作为本次会话的 world_info
            testbook_items = runtime.contents.list("world_info", tags=["testbook"])
            testbook_ids = [item["id"] for item in testbook_items]
            content_refs = {"world_info": testbook_ids}
            if not testbook_ids:
                print("⚠️ 未找到 testbook 世界观条目，请先导入 worldinfo.json")

        conv_id = runtime.create_conversation(
            graph_name,
            title=f"测试-{graph_name}",
            content_refs=content_refs,
        )
        print(f"\n已创建会话: {conv_id} (使用图: {graph_name})")
    else:
        print(f"\n已进入历史会话: {conv_id} (使用图: {graph_name})")
    print("-" * 50)

    if graph_name == "with_commands":
        print("支持的指令：")
        print("  /设定 心情：开心")
        print("  /设定 场景：咖啡厅")
        print("  /记住 我喜欢猫")
        print("  /忘记 猫")
        print("-" * 50)

    print("系统命令：")
    print("  /history    - 查看对话历史（带序号）")
    print("  /edit <序号> - 编辑指定消息")
    print("  /delete <序号> - 删除指定消息")
    print("  /state      - 查看完整状态（调试用）")
    print("  /snapshots  - 查看状态快照历史")
    print("  /export     - 导出当前 state 到文件")
    print("  /regen      - 重新生成最后回复")
    print("-" * 50)

    print("输入 'quit' 退出\n")

    last_state = {}  # 保存最后一次的 state 用于调试

    while True:
        user_input = input("你: ").strip()

        if user_input.lower() == "quit":
            print("再见！")
            break

        if not user_input:
            continue

        # 处理系统命令
        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            if cmd in ["/history", "/state", "/snapshots", "/regen", "/edit", "/delete", "/export"]:
                handle_system_command(runtime, conv_id, user_input, last_state)
                continue

        try:
            config = get_config()

            if config.llm.stream:
                # 流式输出模式
                print("\nAI: ", end="", flush=True)

                def stream_print(chunk: str):
                    print(chunk, end="", flush=True)

                result = runtime.run(conv_id, user_input, stream_callback=stream_print)
                print("\n")  # 流式结束后换行
            else:
                # 普通模式
                result = runtime.run(conv_id, user_input)
                output = result.get("last_output", "")
                if output:
                    print(f"\nAI: {output}\n")
                else:
                    print("\n(无回复)\n")

            last_state = result  # 保存 state

            # 如果是角色扮演，显示情绪
            if graph_name == "roleplay":
                mood = result.get("mood", "")
                if mood:
                    print(f"  [情绪: {mood}]")
                thought = result.get("inner_thought", "")
                if thought:
                    print(f"  [内心: {thought}]")
                print()

        except Exception as e:
            print(f"\n错误: {e}\n")
            import traceback
            traceback.print_exc()


def handle_system_command(runtime, conv_id: str, command: str, last_state: dict = None):
    """处理系统命令"""
    parts = command.split(maxsplit=1)
    cmd = parts[0].lower()

    try:
        if cmd == "/state":
            print("\n===== 当前 State =====")
            state = runtime.get_state(conv_id)
            if not state:
                print("(暂无 state，先发送一条消息)")
            else:
                # 完整格式化输出
                print(json.dumps(state, ensure_ascii=False, indent=2, default=str))
            print("======================\n")

        elif cmd == "/history":
            messages = runtime.get_history(conv_id)
            print("\n对话历史：")
            if not messages:
                print("  (暂无消息)")
            else:
                for i, msg in enumerate(messages):
                    role_icon = "👤" if msg.get("role") == "user" else "🤖"
                    content = msg.get("content", "").replace("\n", " ")
                    content_preview = content[:60] + "..." if len(content) > 60 else content
                    print(f"  [{i}] {role_icon} {content_preview}")
            print()

        elif cmd == "/edit":
            arg = parts[1] if len(parts) > 1 else ""
            if not arg:
                print("用法: /edit <序号>  (序号从0开始，用 /history 查看)\n")
                return

            try:
                idx = int(arg)
            except ValueError:
                print("序号必须是数字\n")
                return

            messages = runtime.get_history(conv_id)
            if idx < 0 or idx >= len(messages):
                print(f"序号超出范围 (0-{len(messages)-1})\n")
                return

            old_content = messages[idx].get("content", "")
            print(f"\n当前内容: {old_content[:100]}{'...' if len(old_content) > 100 else ''}")
            print("输入新内容 (直接回车取消):")
            new_content = input("> ").strip()

            if not new_content:
                print("已取消\n")
                return

            success = runtime.edit_message(conv_id, idx, new_content)
            if success:
                print(f"✓ 消息 [{idx}] 已修改（未创建新 checkpoint）\n")
            else:
                print("✗ 修改失败\n")

        elif cmd == "/delete":
            arg = parts[1] if len(parts) > 1 else ""
            if not arg:
                print("用法: /delete <序号>  (序号从0开始，用 /history 查看)\n")
                return

            try:
                idx = int(arg)
            except ValueError:
                print("序号必须是数字\n")
                return

            messages = runtime.get_history(conv_id)
            if idx < 0 or idx >= len(messages):
                print(f"序号超出范围 (0-{len(messages)-1})\n")
                return

            success = runtime.delete_message(conv_id, idx)
            if success:
                print(f"✓ 消息 [{idx}] 已删除（未创建新 checkpoint）\n")
            else:
                print("✗ 删除失败\n")

        elif cmd == "/snapshots":
            snapshots = runtime.get_state_history(conv_id, limit=5)
            print("\n状态快照历史（最近5个）：")
            if not snapshots:
                print("  (暂无快照)")
            else:
                for s in snapshots:
                    step = s.get("step", "?")
                    checkpoint_id = s.get("checkpoint_id", "?")[:8]
                    msg_count = len(s.get("values", {}).get("messages", []))
                    print(f"  Step {step}: {checkpoint_id}... ({msg_count} 条消息)")
            print()

        elif cmd == "/export":
            state = runtime.get_state(conv_id)
            if not state:
                print("暂无 state，先发送一条消息\n")
                return
            filename = f"state_{conv_id}.json"
            path = Path.cwd() / filename
            path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"已导出: {path}\n")

        elif cmd == "/regen":
            print("重新生成中...")
            result = runtime.regenerate(conv_id)
            output = result.get("last_output", "")
            if output:
                print(f"\nAI: {output}\n")
            else:
                print("重新生成失败\n")

        else:
            print(f"未知命令: {cmd}\n")

    except Exception as e:
        print(f"错误: {e}\n")
        import traceback
        traceback.print_exc()


def _select_conversation(runtime: Runtime) -> tuple[str | None, str | None]:
    conversations = runtime.list_conversations()
    if not conversations:
        print("暂无历史会话，改为新建。")
        return None, None

    print("\n历史会话：")
    for i, conv in enumerate(conversations):
        title = conv.get("title") or ""
        graph = conv.get("graph_name") or ""
        print(f"  [{i}] {conv.get('id')}  {graph}  {title}")
    choice = input("选择序号(留空取消): ").strip()
    if choice == "":
        return None, None
    try:
        idx = int(choice)
    except ValueError:
        print("序号必须是数字")
        return None, None
    if idx < 0 or idx >= len(conversations):
        print("序号超出范围")
        return None, None
    conv = conversations[idx]
    return conv.get("id"), conv.get("graph_name")


if __name__ == "__main__":
    main()
