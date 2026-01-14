"""
入口文件：演示如何使用框架
"""
from core import Runtime


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
    
    print("编辑命令（所有图都支持）：")
    print("  /history     - 查看最近消息（带ID）")
    print("  /edit <id>   - 编辑指定消息")
    print("  /delete <id> - 删除指定消息")
    print("  /rollback <id> - 回滚到指定消息")
    print("  /regen       - 重新生成最后回复")
    print("-" * 50)
    
    print("输入 'quit' 退出\n")
    
    while True:
        user_input = input("你: ").strip()
        
        if user_input.lower() == "quit":
            print("再见！")
            break
        
        if not user_input:
            continue
        
        # 处理编辑命令
        if user_input.startswith("/") and user_input.split()[0].lower() in ["/history", "/edit", "/delete", "/rollback", "/regen"]:
            handle_edit_command(runtime, conv_id, user_input)
            continue
        
        try:
            result = runtime.run(conv_id, user_input)
            
            # 输出回复
            output = result.get("last_output", "")
            if output:
                print(f"\nAI: {output}\n")
            else:
                print("\n(无回复)\n")
            
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


def handle_edit_command(runtime, conv_id: str, command: str):
    """处理编辑命令"""
    parts = command.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    
    try:
        if cmd == "/history":
            messages = runtime.get_recent_messages(conv_id, 10)
            print("\n最近消息：")
            for msg in messages:
                role_icon = "👤" if msg["role"] == "user" else "🤖"
                content_preview = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]
                print(f"  [{msg['id']}] {role_icon} {content_preview}")
            print()
        
        elif cmd == "/edit":
            if not arg:
                print("用法: /edit <消息ID>")
                return
            
            msg_id = int(arg)
            print(f"编辑消息 {msg_id}，输入新内容（输入空行取消）：")
            new_content = input("> ").strip()
            
            if new_content:
                runtime.edit_message(msg_id, new_content)
                print(f"✓ 消息 {msg_id} 已更新\n")
            else:
                print("已取消\n")
        
        elif cmd == "/delete":
            if not arg:
                print("用法: /delete <消息ID>")
                return
            
            msg_id = int(arg)
            runtime.delete_message(msg_id)
            print(f"✓ 消息 {msg_id} 已删除\n")
        
        elif cmd == "/rollback":
            if not arg:
                print("用法: /rollback <消息ID>")
                return
            
            msg_id = int(arg)
            runtime.rollback_to(conv_id, msg_id)
            print(f"✓ 已回滚到消息 {msg_id}（之后的消息已删除）\n")
        
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


def demo_programmatic():
    """编程方式使用示例"""
    runtime = Runtime()
    
    # 创建会话
    conv_id = runtime.create_conversation("default")
    
    # 执行对话
    result = runtime.run(conv_id, "你好！")
    print(result.get("last_output"))
    
    result = runtime.run(conv_id, "今天天气怎么样？")
    print(result.get("last_output"))
    
    # 查看历史
    history = runtime.get_history(conv_id)
    for msg in history:
        print(f"{msg['role']}: {msg['content']}")


if __name__ == "__main__":
    main()
