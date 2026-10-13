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
