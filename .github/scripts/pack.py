# -*- coding: utf-8 -*-
"""把构建产物打成发布 zip。

用法：python pack.py <tag>   # tag 形如 v2.2.1
产出：GeZi-<tag>-win64.zip

打包规则（与原版发布保持一致，见 v2.2.0 资产结构）：
- 顶层目录：鸽子下载/
- 包含：GeZi.exe / GeZi.Core.dll / GeZi.exe.config / zxing.dll / Runtime/**
- 排除：*.pdb（调试符号）、zxing.xml（文档）、GeZi.config.xml / GeZi.state.json
        （用户状态，绝不能被误打包）、startup-error.log
"""
import pathlib
import sys
import zipfile

# 【2026-10-13 修复】强制 stdout/stderr 走 UTF-8。
#
# 背景：本脚本在本地（终端为 UTF-8）一切正常，但在 GitHub Actions 的
# Windows runner 上首次发版时崩溃（run 38347218262）：
#     UnicodeEncodeError: 'charmap' codec can't encode characters in position 0-3
# Windows 上被重定向到管道的 stdout 默认使用系统 ANSI 代码页（cp1252 / cp936
# 等）而非 UTF-8，打印任何中文都会抛异常。
#
# ⚠️ 这个异常尤其阴险：它发生在最后一句 print 上，此时 zip **已经写好了**，
# 却让整个步骤以 exit 1 结束 —— 现场表现为"打包失败"，实际产物完好，
# 极易把排查方向带偏。故此处从根上杜绝，而不是改掉中文提示。
#
# errors="replace" 是第二道保险：即便某些环境 reconfigure 后仍无法编码，
# 也只会把字符替换成 '?'，绝不至于让发版流程失败。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 极老的 Python 或已被包装过的流
        pass

TOP_DIR = "鸽子下载"
# 顶层必需文件（与原版一致；zxing.xml 为文档，不发）
TOP_FILES = ["GeZi.exe", "GeZi.Core.dll", "GeZi.exe.config", "zxing.dll"]
# 需要排除的目录内文件模式（相对 bin 目录）
EXCLUDE_SUFFIXES = (".pdb", ".xml", ".json", ".log", ".qmeta")
EXCLUDE_NAMES = {"GeZi.config.xml", "GeZi.state.json", "startup-error.log"}


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "dev"
    bin_dir = pathlib.Path("src/GeZi/bin/Release/net48")
    if not bin_dir.is_dir():
        print(f"错误：构建产物目录不存在 {bin_dir}")
        return 1

    out = pathlib.Path(f"GeZi-{tag}-win64.zip")

    entries = []
    for name in TOP_FILES:
        p = bin_dir / name
        if not p.is_file():
            print(f"错误：缺少必需文件 {p}")
            return 1
        entries.append((p, f"{TOP_DIR}/{name}"))

    runtime = bin_dir / "Runtime"
    if runtime.is_dir():
        for p in sorted(runtime.rglob("*")):
            if not p.is_file():
                continue
            if p.name in EXCLUDE_NAMES or p.name.endswith(EXCLUDE_SUFFIXES):
                continue
            rel = p.relative_to(bin_dir).as_posix()
            entries.append((p, f"{TOP_DIR}/{rel}"))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, arcname in entries:
            z.write(src, arcname)

    size_mb = out.stat().st_size / 1000 / 1000
    print(f"打包完成: {out}（{len(entries)} 个文件，{size_mb:.2f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
