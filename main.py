"""
入口文件：演示如何使用框架
"""
import json
import sys
from core import Runtime
from core.config import get_config


def main():
    """主函数"""
    runtime = Runtime()
    
    print("=" * 50)
    print("LangGraph 聊天框架演示")
    print("=" * 50)
    print()
    print("可用的图：")
    print("  1. default     - 默认对话")
    print("  2. roleplay    - 角色扮演")
    print("  3. with_commands - 带指令解析")
    print()
    
    # 选择图
    choice = input("选择图 (1/2/3，默认1): ").strip() or "1"
    graph_map = {"1": "default", "2": "roleplay", "3": "with_commands"}
    graph_name = graph_map.get(choice, "default")
    
    # 创建会话
    conv_id = runtime.create_conversation(graph_name, title=f"测试-{graph_name}")
    print(f"\n已创建会话: {conv_id} (使用图: {graph_name})")
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
            if cmd in ["/history", "/state", "/snapshots", "/regen", "/edit", "/delete"]:
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


def demo_programmatic():
    """编程方式使用示例"""
    runtime = Runtime()
    
    # 创建会话（可以关联角色卡）
    conv_id = runtime.create_conversation(
        graph_name="roleplay",
        title="与小雪的对话",
        content_refs={"character": "xiaoxue"},  # 从 content.db 加载角色卡
    )
    
    # 执行对话
    result = runtime.run(conv_id, "你好！")
    print(result.get("last_output"))
    print(f"情绪: {result.get('mood')}")
    
    result = runtime.run(conv_id, "今天天气怎么样？")
    print(result.get("last_output"))
    print(f"情绪: {result.get('mood')}")
    
    # 查看历史（从 checkpoint 读取）
    history = runtime.get_history(conv_id)
    for msg in history:
        print(f"{msg['role']}: {msg['content']}")
    
    # 查看完整状态
    state = runtime.get_state(conv_id)
    print(f"当前情绪: {state.get('mood')}")
    print(f"角色: {state.get('character', {}).get('name')}")


def demo_with_character():
    """演示如何使用角色卡"""
    runtime = Runtime()
    
    # 先保存一个角色卡到 content.db
    runtime.contents.save("character", "luna", {
        "name": "Luna",
        "personality": "神秘、优雅、充满智慧",
        "scenario": "月光下的古老图书馆",
        "first_message": "你好，旅行者。我是 Luna，这座图书馆的守护者。"
    }, tags=["fantasy", "mysterious"])
    
    # 创建使用该角色的会话
    conv_id = runtime.create_conversation(
        graph_name="roleplay",
        title="与 Luna 的对话",
        content_refs={"character": "luna"}
    )
    
    # 开始对话
    result = runtime.run(conv_id, "你好，请问这里有什么有趣的书？")
    print(result.get("last_output"))


if __name__ == "__main__":
    main()
