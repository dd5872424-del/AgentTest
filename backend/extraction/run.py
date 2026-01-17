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
import math
import hashlib
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def cmd_worldinfo(args):
    """世界书抽取命令"""
    from extraction import WorldInfoExtractor
    from extraction.base import ExtractionResult
    from extraction.config import get_extraction_config
    
    config = get_extraction_config()

    # 检查输入参数
    if not args.input and not args.input_dir:
        if config.input_dir:
            args.input_dir = config.input_dir
        elif config.input:
            args.input = config.input
        else:
            print("❌ 请指定输入文件或使用 --input-dir 指定目录")
            return 1
    
    input_display = args.input_dir if args.input_dir else args.input
    print(f"📖 世界书抽取")
    print(f"   输入: {input_display}")
    
    # 创建抽取器
    extractor_kwargs = {}
    if args.model:
        extractor_kwargs["model"] = args.model
    if args.temperature:
        extractor_kwargs["temperature"] = args.temperature
    
    llm_merge_enabled = bool(args.llm_merge)
    if args.prompts_dir:
        extractor_kwargs["prompts_dir"] = args.prompts_dir
    extractor = WorldInfoExtractor(
        enable_llm_merge=llm_merge_enabled,
        **extractor_kwargs
    )

    def _append_jsonl(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _load_processed_chunks(jsonl_path: Path) -> dict[str, dict]:
        """
        加载已处理的 chunk 记录
        返回: {source: {chunk_index: {"hash": chunk_hash, "entries": [...]}}}
        """
        processed = {}
        if not jsonl_path.exists():
            return processed
        try:
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        source = str(Path(obj.get("source", "")))
                        chunk_index = obj.get("chunk_index")
                        chunk_hash = obj.get("chunk_hash")
                        entries = obj.get("entries", [])
                        success = obj.get("success", True)
                        if source and chunk_index is not None and chunk_hash:
                            if source not in processed:
                                processed[source] = {}
                            processed[source][chunk_index] = {
                                "hash": chunk_hash,
                                "entries": entries,
                                "success": bool(success),
                            }
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return processed
        return processed

    def _file_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _estimate_tokens(text: str) -> int:
        """
        粗略 token 估算：
        - CJK 字符按 1 token
        - 非 CJK 按 4 字符 ~ 1 token
        """
        if not text:
            return 0
        cjk = 0
        for ch in text:
            code = ord(ch)
            if (
                0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
                or 0x3400 <= code <= 0x4DBF  # CJK Extension A
                or 0x20000 <= code <= 0x2A6DF  # CJK Extension B
                or 0x2A700 <= code <= 0x2B73F  # CJK Extension C
                or 0x2B740 <= code <= 0x2B81F  # CJK Extension D
                or 0x2B820 <= code <= 0x2CEAF  # CJK Extension E
                or 0xF900 <= code <= 0xFAFF  # CJK Compatibility Ideographs
            ):
                cjk += 1
        other = len(text) - cjk
        return cjk + math.ceil(other / 4)

    def _estimate_messages_tokens(messages: list[dict]) -> int:
        return sum(_estimate_tokens(m.get("content", "")) for m in messages)

    def _estimate_file_tokens(text: str) -> dict:
        # 构建主提示词（不含模型输出）
        first_messages = extractor.build_prompt(text)
        first_tokens = _estimate_messages_tokens(first_messages)
        total_calls = 1
        total_tokens = first_tokens

        # Gleaning 额外调用（不计入 assistant 输出长度，作为保守估计）
        if extractor.enable_gleaning:
            gleaning_messages = [
                {"role": "system", "content": extractor.system_prompt},
                {"role": "user", "content": extractor.user_prompt_template.format(text=text)},
                {"role": "assistant", "content": ""},  # 估算不包含首次输出
                {"role": "user", "content": extractor.gleaning_prompt_template.format(text=text)},
            ]
            total_calls += 1
            total_tokens += _estimate_messages_tokens(gleaning_messages)

        return {
            "calls": total_calls,
            "tokens": total_tokens,
        }

    def _estimate_chunks_tokens(text: str) -> dict:
        chunks = extractor._split_text(
            text,
            args.chunk_size,
            args.overlap or 500,
            strategy=args.chunk_strategy,
            chapter_max_chars=args.chapter_max,
        )
        total_calls = 0
        total_tokens = 0
        for chunk in chunks:
            info = _estimate_file_tokens(chunk)
            total_calls += info["calls"]
            total_tokens += info["tokens"]
        return {
            "chunks": len(chunks),
            "calls": total_calls,
            "tokens": total_tokens,
        }
    
    # 读取文件或目录
    input_path = Path(args.input_dir) if args.input_dir else Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件或目录不存在: {input_path}")
        return 1

    # 目录模式：读取该目录下的所有 .md（按文件名顺序）
    if input_path.is_dir():
        pattern = "**/*.md" if args.recursive else "*.md"
        md_files = sorted(input_path.glob(pattern))
        if not md_files:
            print(f"❌ 目录内未找到 .md 文件: {input_path}")
            return 1
        print(f"   文件数: {len(md_files)}")

        # 自动设置增量文件路径（放在 input 目录内）
        if not args.output_jsonl:
            args.output_jsonl = str(input_path / ".worldinfo.partial.jsonl")
        print(f"   增量文件: {args.output_jsonl}")

        # 自动启用断点续跑（chunk 级别）
        processed_chunks = _load_processed_chunks(Path(args.output_jsonl))
        if processed_chunks:
            total_chunks_done = sum(len(v) for v in processed_chunks.values())
            print(f"   已检测到已处理: {len(processed_chunks)} 个文件, {total_chunks_done} 个 chunk")

        if args.estimate_tokens:
            total_calls = 0
            total_tokens = 0
            total_files = len(md_files)
            for idx, md_path in enumerate(md_files, start=1):
                text = md_path.read_text(encoding="utf-8")
                file_hash = _file_hash(text)
                if processed_sources.get(str(md_path)) == file_hash:
                    percent = int(idx / total_files * 100)
                    print(f"   估算: [{idx}/{total_files} {percent}%] {md_path.name} -> 已处理，跳过")
                    continue
                if args.chunk_strategy != "fixed" or (args.chunk_size and len(text) > args.chunk_size):
                    info = _estimate_chunks_tokens(text)
                    total_calls += info["calls"]
                    total_tokens += info["tokens"]
                    percent = int(idx / total_files * 100)
                    print(
                        f"   估算: [{idx}/{total_files} {percent}%] {md_path.name} -> chunks={info['chunks']}, calls≈{info['calls']}, tokens≈{info['tokens']}"
                    )
                else:
                    info = _estimate_file_tokens(text)
                    total_calls += info["calls"]
                    total_tokens += info["tokens"]
                    percent = int(idx / total_files * 100)
                    print(
                        f"   估算: [{idx}/{total_files} {percent}%] {md_path.name} -> calls≈{info['calls']}, tokens≈{info['tokens']}"
                    )
            if args.llm_merge:
                print("   估算提示: --llm-merge 的合并调用不在此估算内（取决于抽取后条目长度）。")
            print(f"   估算汇总: calls≈{total_calls}, tokens≈{total_tokens}")
            print("   估算说明: 不包含模型输出长度，仅为输入提示词的粗略估算。")
            if args.estimate_only:
                return 0

        results_all = []
        any_failed = False
        total_files = len(md_files)
        for idx, md_path in enumerate(md_files, start=1):
            text = md_path.read_text(encoding="utf-8")
            percent = int(idx / total_files * 100)
            print(f"   处理: [{idx}/{total_files} {percent}%] {md_path.name} ({len(text)} 字符)")

            # 分块处理（带 chunk 级别断点续跑）
            chunks = extractor._split_text(
                text,
                args.chunk_size,
                args.overlap or 500,
                strategy=args.chunk_strategy,
                chapter_max_chars=args.chapter_max,
            )
            chunk_count = len(chunks)
            print(
                f"   分块处理: 策略={args.chunk_strategy}, chunk_size={args.chunk_size}, chapter_max={args.chapter_max}，共 {chunk_count} 块"
            )

            file_key = str(md_path)
            file_processed_chunks = processed_chunks.get(file_key, {})
            chunk_results = []
            skipped = 0
            success = 0

            file_failed = False
            for ci, chunk in enumerate(chunks):
                chunk_hash = _file_hash(chunk)
                cached = file_processed_chunks.get(ci)
                
                # 检查是否已处理（哈希一致）
                if cached and cached.get("hash") == chunk_hash and cached.get("success"):
                    # 从缓存恢复
                    chunk_results.append(ExtractionResult(
                        success=True,
                        data=cached.get("entries", []),
                        source=f"{md_path}#chunk{ci}",
                    ))
                    skipped += 1
                    print(f"     chunk [{ci+1}/{chunk_count}] -> 已处理，跳过")
                    continue

                # 调用 LLM 抽取
                max_retries = max(1, int(args.retry_max))
                result = None
                attempts_used = 0
                for attempt in range(1, max_retries + 1):
                    attempts_used = attempt
                    print(f"     chunk [{ci+1}/{chunk_count}] 抽取中... (尝试 {attempt}/{max_retries})")
                    result = extractor.extract(chunk)
                    if result.success:
                        break
                    print(f"     chunk [{ci+1}/{chunk_count}] 抽取失败: {result.error}")
                
                if result.success:
                    success += 1
                    chunk_results.append(result)
                    # 立即写入 jsonl（chunk 级别）
                    _append_jsonl(
                        Path(args.output_jsonl),
                        {
                            "source": file_key,
                            "chunk_index": ci,
                            "chunk_hash": chunk_hash,
                            "entries": result.data,
                            "success": True,
                            "attempts": attempts_used,
                        }
                    )
                else:
                    file_failed = True
                    chunk_results.append(result)
                    _append_jsonl(
                        Path(args.output_jsonl),
                        {
                            "source": file_key,
                            "chunk_index": ci,
                            "chunk_hash": chunk_hash,
                            "entries": [],
                            "success": False,
                            "attempts": attempts_used,
                            "error": result.error or "unknown error",
                        }
                    )

            print(f"   分块结果: {success} 成功, {skipped} 跳过, {chunk_count - success - skipped} 失败")

            # 目录模式下避免对每个文件单独做 LLM 合并，留给全局合并处理
            if file_failed:
                any_failed = True
                print(f"   ⚠️ 文件存在失败 chunk，跳过该文件合并: {md_path}")
                results_all.append(ExtractionResult(
                    success=False,
                    data=[],
                    source=str(md_path),
                    error="chunk_failed",
                ))
            else:
                print(f"   合并中: {md_path.name} -> {len(chunk_results)} chunks")
                if args.llm_merge:
                    prev_merge = extractor.enable_llm_merge
                    extractor.enable_llm_merge = False
                    entries = extractor.merge_results(chunk_results)
                    extractor.enable_llm_merge = prev_merge
                else:
                    entries = extractor.merge_results(chunk_results)
                print(f"   合并完成: {md_path.name} -> {len(entries)} 条目")

                results_all.append(ExtractionResult(
                    success=True,
                    data=entries,
                    source=str(md_path),
                ))

        # 目录模式合并所有文件（按文件顺序）
        if any_failed:
            print("❌ 存在失败 chunk，已跳过最终合并。请基于 jsonl 进行重试后再合并。")
            return 2
        print(f"✅ 开始最终合并: {len(results_all)} 个文件")
        entries = extractor.merge_results(results_all)
        print(f"✅ 最终合并完成: {len(entries)} 条目")
    else:
        # 文件模式
        text = input_path.read_text(encoding="utf-8")
        print(f"   文本长度: {len(text)} 字符")

        if args.estimate_tokens:
            if args.chunk_strategy != "fixed" or (args.chunk_size and len(text) > args.chunk_size):
                info = _estimate_chunks_tokens(text)
                print(
                    f"   估算: chunks={info['chunks']}, calls≈{info['calls']}, tokens≈{info['tokens']}"
                )
            else:
                info = _estimate_file_tokens(text)
                print(
                    f"   估算: calls≈{info['calls']}, tokens≈{info['tokens']}"
                )
            if args.llm_merge:
                print("   估算提示: --llm-merge 的合并调用不在此估算内（取决于抽取后条目长度）。")
            print("   估算说明: 不包含模型输出长度，仅为输入提示词的粗略估算。")
            if args.estimate_only:
                return 0

        # 自动设置增量文件路径（放在文件同目录）
        if not args.output_jsonl:
            args.output_jsonl = str(input_path.parent / f".{input_path.stem}.partial.jsonl")
        print(f"   增量文件: {args.output_jsonl}")

        # 加载已处理的 chunk
        processed_chunks = _load_processed_chunks(Path(args.output_jsonl))
        file_key = str(input_path)
        file_processed_chunks = processed_chunks.get(file_key, {})
        if file_processed_chunks:
            print(f"   已检测到已处理: {len(file_processed_chunks)} 个 chunk")

        # 执行抽取（chunk 级别断点续跑）
        chunks = extractor._split_text(
            text,
            args.chunk_size,
            args.overlap or 500,
            strategy=args.chunk_strategy,
            chapter_max_chars=args.chapter_max,
        )
        chunk_count = len(chunks)
        print(
            f"   分块处理: 策略={args.chunk_strategy}, chunk_size={args.chunk_size}, chapter_max={args.chapter_max}，共 {chunk_count} 块"
        )

        chunk_results = []
        skipped = 0
        success = 0

        any_failed = False
        for ci, chunk in enumerate(chunks):
            chunk_hash = _file_hash(chunk)
            cached = file_processed_chunks.get(ci)

            # 检查是否已处理（哈希一致）
            if cached and cached.get("hash") == chunk_hash and cached.get("success"):
                chunk_results.append(ExtractionResult(
                    success=True,
                    data=cached.get("entries", []),
                    source=f"{input_path}#chunk{ci}",
                ))
                skipped += 1
                print(f"     chunk [{ci+1}/{chunk_count}] -> 已处理，跳过")
                continue

            # 调用 LLM 抽取
            max_retries = max(1, int(args.retry_max))
            result = None
            attempts_used = 0
            for attempt in range(1, max_retries + 1):
                attempts_used = attempt
                print(f"     chunk [{ci+1}/{chunk_count}] 抽取中... (尝试 {attempt}/{max_retries})")
                result = extractor.extract(chunk)
                if result.success:
                    break
                print(f"     chunk [{ci+1}/{chunk_count}] 抽取失败: {result.error}")

            if result.success:
                success += 1
                chunk_results.append(result)
                # 立即写入 jsonl（chunk 级别）
                _append_jsonl(
                    Path(args.output_jsonl),
                    {
                        "source": file_key,
                        "chunk_index": ci,
                        "chunk_hash": chunk_hash,
                        "entries": result.data,
                        "success": True,
                        "attempts": attempts_used,
                    }
                )
            else:
                any_failed = True
                chunk_results.append(result)
                _append_jsonl(
                    Path(args.output_jsonl),
                    {
                        "source": file_key,
                        "chunk_index": ci,
                        "chunk_hash": chunk_hash,
                        "entries": [],
                        "success": False,
                        "attempts": attempts_used,
                        "error": result.error or "unknown error",
                    }
                )

        print(f"   分块结果: {success} 成功, {skipped} 跳过, {chunk_count - success - skipped} 失败")
        if any_failed:
            print("❌ 存在失败 chunk，已跳过最终合并。请基于 jsonl 进行重试后再合并。")
            return 2
        print(f"✅ 开始合并: {len(chunk_results)} chunks")
        entries = extractor.merge_results(chunk_results)
        print(f"✅ 合并完成: {len(entries)} 条目")
    
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
    from extraction.config import get_extraction_config
    config = get_extraction_config()

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
    wi_parser.add_argument(
        "input",
        nargs="?",
        default=config.input,
        help="输入文件路径（使用 --input-dir 时可省略）",
    )
    wi_parser.add_argument(
        "--input-dir",
        default=config.input_dir,
        help="输入目录（读取目录下所有 .md 文件）",
    )
    wi_parser.add_argument(
        "--no-recursive",
        action="store_false",
        dest="recursive",
        help="不递归读取子目录（默认递归）"
    )
    wi_parser.set_defaults(recursive=config.recursive)
    wi_parser.add_argument("-o", "--output", default=config.output, help="输出 JSON 文件路径")
    wi_parser.add_argument("--model", default=config.model, help="LLM 模型名称")
    wi_parser.add_argument("--temperature", type=float, default=config.temperature, help="生成温度")
    wi_parser.add_argument(
        "--chunk-size",
        type=int,
        default=config.chunk_size,
        help="分块大小（字符数），默认 8000",
    )
    wi_parser.add_argument(
        "--chunk-strategy",
        choices=["auto", "fixed", "chapters"],
        default=config.chunk_strategy,
        help="分块策略：auto(有章节则按章节，否则固定)、fixed(固定长度)、chapters(按章节，超长章节再切)",
    )
    wi_parser.add_argument(
        "--chapter-max",
        type=int,
        default=config.chapter_max,
        help="章节块最大字符数（章节策略下生效）",
    )
    wi_parser.add_argument(
        "--retry-max",
        type=int,
        default=config.retry_max,
        help="chunk 抽取失败的最大重试次数，默认 3",
    )
    wi_parser.add_argument(
        "--prompts-dir",
        dest="prompts_dir",
        default=config.prompts_dir,
        help="提示词目录或套件名（如 shi_jiao），默认使用 extraction/prompts/xiuxian/",
    )
    wi_parser.add_argument(
        "--overlap",
        type=int,
        default=config.overlap,
        help="分块重叠大小",
    )
    wi_parser.add_argument(
        "--no-llm-merge",
        action="store_false",
        dest="llm_merge",
        help="禁用跨 chunk 的 LLM 合并/消歧（默认启用）"
    )
    wi_parser.set_defaults(llm_merge=config.llm_merge)
    wi_parser.add_argument(
        "--estimate-tokens",
        action="store_true",
        default=config.estimate_tokens,
        help="估算提示词 token（不包含模型输出）",
    )
    wi_parser.add_argument(
        "--estimate-only",
        action="store_true",
        default=config.estimate_only,
        help="只估算 token，不执行抽取",
    )
    wi_parser.add_argument(
        "--output-jsonl",
        default=config.output_jsonl,
        help="增量写入 JSONL（每个文件一行，防止进度丢失）",
    )
    wi_parser.add_argument(
        "--resume",
        action="store_true",
        default=config.resume,
        help="从 JSONL 断点续跑（跳过已处理文件）",
    )
    wi_parser.add_argument(
        "--import-db",
        action="store_true",
        default=config.import_db,
        help="直接导入到 content.db",
    )
    wi_parser.set_defaults(func=cmd_worldinfo)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
