#!/usr/bin/env python3
"""Experimental native installer builder using the regular Tiny11 configuration.

Registry/file edits happen on macOS. Microsoft DISM provisioning and cleanup
are deferred to the destination PC; installed-system parity is unverified.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, check=True, text=True, capture_output=capture)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required command not found: {args[0]}. Install the prerequisites in README.md") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if exc.stderr else str(exc)
        raise RuntimeError(f"Command failed ({exc.returncode}): {' '.join(args)}\n{detail}") from exc


def require_tools(*names: str) -> None:
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise RuntimeError("Missing required tools: " + ", ".join(missing) + ". See README.md.")


def inspect(args: argparse.Namespace) -> int:
    require_tools("wimlib-imagex")
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise RuntimeError(f"Image not found: {image}")
    if image.suffix.lower() not in {".wim", ".esd"}:
        raise RuntimeError("Input must be an install.wim or install.esd extracted from Microsoft installation media.")
    run(["wimlib-imagex", "info", str(image)])
    return 0


def export_x64(args: argparse.Namespace) -> int:
    require_tools("wimlib-imagex")
    source = Path(args.image).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    if destination.suffix.lower() != '.wim':
        raise RuntimeError('Export output must have a .wim extension.')
    if not source.is_file():
        raise RuntimeError(f"Image not found: {source}")
    if destination.exists():
        raise RuntimeError(f"Refusing to overwrite existing output: {destination}")
    if source == destination:
        raise RuntimeError("Output must differ from input.")
    if args.index < 1:
        raise RuntimeError("Image index must be a positive integer.")
    info = run(["wimlib-imagex", "info", str(source), str(args.index)], capture=True).stdout
    if not re.search(r"(?im)^\s*Architecture:\s*(x64|amd64|x86_64)\s*$", info):
        raise RuntimeError(f"Image index {args.index} is not identified as x64/amd64 by wimlib; refusing export.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["wimlib-imagex", "export", str(source), str(args.index), str(destination),
         args.name or f"Windows x64 image {args.index}", "--compress=LZX"])
    return 0


def make_iso(args: argparse.Namespace) -> int:
    require_tools("xorriso")
    tree = Path(args.tree).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not tree.is_dir():
        raise RuntimeError(f"Windows setup tree not found: {tree}")
    required = ["sources/boot.wim", "sources/install.wim", "boot/etfsboot.com", "efi/microsoft/boot/efisys.bin"]
    missing = [item for item in required if not (tree / item).is_file()]
    if missing:
        raise RuntimeError("Not a complete Windows setup tree; missing: " + ", ".join(missing))
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    run(["xorriso", "-as", "mkisofs", "-o", str(output), "-iso-level", "3", "-J", "-joliet-long",
         "-V", args.label, "-b", "boot/etfsboot.com", "-no-emul-boot", "-boot-load-size", "8",
         "-eltorito-alt-boot", "--efi-boot", "efi/microsoft/boot/efisys.bin", "-no-emul-boot", str(tree)])
    return 0


def default_upstream() -> str:
    project = Path(__file__).resolve().parent
    candidates = (project.parent, project.parent.parent / "tiny11builder-upstream")
    for candidate in candidates:
        if (candidate / "tiny11maker.ps1").is_file():
            return str(candidate)
    return str(project.parent.parent / "tiny11builder-upstream")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an experimental x64 installer natively on macOS using Tiny11 configuration",
                                     epilog="Windows package servicing is deferred to the target PC and requires target validation.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("usb-files", help="prepare FAT32-compatible files for a UEFI USB without formatting a drive")
    p.add_argument("source", help="generated single-edition installer ISO")
    p.add_argument("--output", required=True)
    p.add_argument("--scratch", required=True)
    from usb import prepare
    p.set_defaults(func=prepare)
    p = sub.add_parser("build", help="build experimental native installer with servicing deferred to target PC")
    p.add_argument("source", help="Windows x64 ISO or mounted setup directory")
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--scratch", required=True)
    p.add_argument("--compression-level", type=int, choices=range(1, 101), default=20,
                   metavar="1-100", help="LZMS compression effort (default 20)")
    p.add_argument("--threads", type=int, choices=range(1, 33), default=1,
                   metavar="1-32", help="compression threads (default 1)")
    p.add_argument("--upstream", default=default_upstream())
    from installer import build
    p.set_defaults(func=build)
    p = sub.add_parser("inspect", help="list WIM/ESD editions and metadata")
    p.add_argument("image")
    p.set_defaults(func=inspect)
    p = sub.add_parser("export-x64", help="export one x64/amd64 image index to a new WIM")
    p.add_argument("image")
    p.add_argument("index", type=int)
    p.add_argument("output")
    p.add_argument("--name")
    p.set_defaults(func=export_x64)
    p = sub.add_parser("make-iso", help="package a prepared Windows setup tree as BIOS/UEFI ISO")
    p.add_argument("tree")
    p.add_argument("output")
    p.add_argument("--label", default="TINY11_MACOS")
    p.set_defaults(func=make_iso)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return args.func(args)
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
