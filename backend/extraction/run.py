"""
抽取模块 CLI 入口

用法:
    cd backend
    
    # 从文件抽取世界书
    python -m extraction.run worldinfo input.txt -o output.json
    
    # 从文件抽取（长文本自动分块）
    python -m extraction.run worldinfo novel.txt -o worldinfo.json --chunk-size 6000
    
    # 指定模型
    python -m extraction.run worldinfo input.txt --model gpt-4o
    
    # 直接导入到 content.db
    python -m extraction.run worldinfo input.txt --import-db
"""
import argparse
import json
import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def cmd_worldinfo(args):
    """世界书抽取命令"""
    from extraction import WorldInfoExtractor
    from extraction.base import ExtractionResult
    
    print(f"📖 世界书抽取")
    print(f"   输入: {args.input}")
    
    # 创建抽取器
    extractor_kwargs = {}
    if args.model:
        extractor_kwargs["model"] = args.model
    if args.temperature:
        extractor_kwargs["temperature"] = args.temperature
    
    llm_merge_enabled = bool(args.llm_merge)
    preserve_order_enabled = bool(args.preserve_order) or llm_merge_enabled
    extractor = WorldInfoExtractor(
        enable_llm_merge=llm_merge_enabled,
        preserve_order=preserve_order_enabled,
        **extractor_kwargs
    )
    
    # 读取文件或目录
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件或目录不存在: {input_path}")
        return 1

    # 目录模式：读取该目录下的所有 .md（按文件名顺序）
    if input_path.is_dir():
        md_files = sorted(input_path.glob("*.md"))
        if not md_files:
            print(f"❌ 目录内未找到 .md 文件: {input_path}")
            return 1
        print(f"   文件数: {len(md_files)}")

        results_all = []
        for md_path in md_files:
            text = md_path.read_text(encoding="utf-8")
            print(f"   处理: {md_path.name} ({len(text)} 字符)")

            if args.chunk_size and len(text) > args.chunk_size:
                print(f"   分块处理: 每块 {args.chunk_size} 字符")
                results = extractor.extract_chunks(
                    text,
                    chunk_size=args.chunk_size,
                    overlap=args.overlap or 500
                )

                # 目录模式下避免对每个文件单独做 LLM 合并，留给全局合并处理
                if args.llm_merge:
                    prev_merge = extractor.enable_llm_merge
                    extractor.enable_llm_merge = False
                    entries = extractor.merge_results(results)
                    extractor.enable_llm_merge = prev_merge
                else:
                    entries = extractor.merge_results(results)

                success_count = sum(1 for r in results if r.success)
                print(f"   分块结果: {success_count}/{len(results)} 成功")
            else:
                print(f"   抽取中...")
                result = extractor.extract(text)
                if not result.success:
                    print(f"❌ 抽取失败: {result.error}")
                    return 1
                entries = result.data

            results_all.append(ExtractionResult(
                success=True,
                data=entries,
                source=str(md_path),
            ))

        # 目录模式合并所有文件（按文件顺序）
        entries = extractor.merge_results(results_all)
    else:
        # 文件模式
        text = input_path.read_text(encoding="utf-8")
        print(f"   文本长度: {len(text)} 字符")

        # 执行抽取
        if args.chunk_size and len(text) > args.chunk_size:
            print(f"   分块处理: 每块 {args.chunk_size} 字符")
            results = extractor.extract_chunks(
                text,
                chunk_size=args.chunk_size,
                overlap=args.overlap or 500
            )
            entries = extractor.merge_results(results)

            # 统计成功/失败
            success_count = sum(1 for r in results if r.success)
            print(f"   分块结果: {success_count}/{len(results)} 成功")
        else:
            print(f"   抽取中...")
            result = extractor.extract(text)

            if not result.success:
                print(f"❌ 抽取失败: {result.error}")
                return 1

            entries = result.data
    
    print(f"✅ 抽取完成: {len(entries)} 个条目")
    
    # 输出结果
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"   已保存到: {output_path}")
    else:
        # 打印到控制台
        print("\n" + "=" * 50)
        print(json.dumps(entries, ensure_ascii=False, indent=2))
    
    # 导入到数据库
    if args.import_db:
        from core.storage import SQLiteContentStore
        from core.config import get_config
        
        config = get_config()
        store = SQLiteContentStore(config.database.content_path)
        
        for entry in entries:
            # 使用 name 作为数据库 ID，如果没有则用序号兜底
            entry_id = entry.get("name") or f"wi_{input_path.stem}_{entries.index(entry)}"
            store.save("world_info", entry_id, entry, tags=["extracted"])
        
        print(f"   已导入到 content.db: {len(entries)} 个条目")
    
    return 0


def cmd_list(args):
    """列出可用的抽取器"""
    print("可用的抽取器:")
    print("  worldinfo  - 世界书条目抽取（从小说/设定文本中提取世界观）")
    print()
    print("用法示例:")
    print("  python -m extraction.run worldinfo input.txt -o output.json")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="LLM 数据抽取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出可用的抽取器")
    list_parser.set_defaults(func=cmd_list)
    
    # worldinfo 命令
    wi_parser = subparsers.add_parser("worldinfo", help="世界书条目抽取")
    wi_parser.add_argument("input", help="输入文件路径")
    wi_parser.add_argument("-o", "--output", help="输出 JSON 文件路径")
    wi_parser.add_argument("--model", help="LLM 模型名称")
    wi_parser.add_argument("--temperature", type=float, help="生成温度")
    wi_parser.add_argument("--chunk-size", type=int, help="分块大小（字符数），用于处理长文本")
    wi_parser.add_argument("--overlap", type=int, default=500, help="分块重叠大小")
    wi_parser.add_argument("--llm-merge", action="store_true", help="启用跨 chunk 的 LLM 合并/消歧（会额外调用一次 LLM）")
    wi_parser.add_argument("--preserve-order", action="store_true", help="保留条目顺序（不按优先级排序）")
    wi_parser.add_argument("--import-db", action="store_true", help="直接导入到 content.db")
    wi_parser.set_defaults(func=cmd_worldinfo)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
