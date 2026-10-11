#!/usr/bin/env python3
"""Pick an ISO and edition, then build the ISO and UEFI USB files."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import plistlib
import platform
import re
import shutil
import stat
import subprocess
import sys

PROJECT = Path(__file__).resolve().parent
DIALOGS = PROJECT / "Tiny11Dialogs.applescript"
DEPENDENCIES = ("python", "wimlib", "hivex", "cdrtools", "xorriso", "autoconf", "automake", "libtool", "pkgconf", "coreutils")
DATAless = getattr(stat, "SF_DATALESS", 0x40000000)


class Cancelled(Exception):
    pass


def background(args: list[str]) -> list[str]:
    taskpolicy = shutil.which("taskpolicy")
    return [taskpolicy, "-b", "nice", "-n", "19", *args] if taskpolicy else args


def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(background(args), check=True, text=True,
                              capture_output=capture, cwd=PROJECT)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        if exc.returncode == -2:
            detail = "Interrupted. Any completed ISO is preserved."
        raise RuntimeError(f"{Path(args[0]).name} stopped ({exc.returncode}). {detail}") from exc


def dialog(action: str, *args: str) -> str:
    result = subprocess.run(["osascript", str(DIALOGS), action, *args],
                            check=True, text=True, capture_output=True)
    choice = result.stdout.strip()
    if choice == "__CANCELLED__":
        raise Cancelled
    return choice


def ensure_homebrew_tools() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("The guided builder runs on macOS.")
    if subprocess.run(["xcrun", "--find", "clang"], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode != 0:
        raise RuntimeError("Xcode Command Line Tools are required. Run `xcode-select --install` in Terminal and reopen the builder.")
    brew = shutil.which("brew")
    if not brew:
        for candidate in (Path("/opt/homebrew/bin/brew"), Path("/usr/local/bin/brew")):
            if candidate.is_file():
                brew = str(candidate)
                break
    if not brew:
        raise RuntimeError("Homebrew is required. Install it from https://brew.sh, then reopen Build-Tiny11.command.")
    prefix = subprocess.check_output([brew, "--prefix"], text=True).strip()
    os.environ["PATH"] = f"{prefix}/bin:{prefix}/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    missing = [name for name in DEPENDENCIES if subprocess.run(
        [brew, "list", "--versions", name], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL).returncode != 0]
    if missing:
        response = dialog("confirm-dependencies",
                          "Install these command-line tools with Homebrew?\n\n" + ", ".join(missing))
        if response != "Install":
            raise Cancelled
        print("Installing required Homebrew tools…", flush=True)
        run([brew, "install", *missing])


def check_resident(path: Path) -> None:
    if getattr(path.stat(), "st_flags", 0) & DATAless:
        raise RuntimeError(f"{path.name} is offloaded. In Finder choose Download Now / Keep Downloaded and try again.")


def mount_iso(image: Path) -> Path:
    check_resident(image)
    result = run(["hdiutil", "attach", "-readonly", "-nobrowse", "-plist", str(image)], capture=True)
    entities = plistlib.loads(result.stdout.encode())["system-entities"]
    mounts = [Path(item["mount-point"]) for item in entities if "mount-point" in item]
    mount = next((p for p in mounts if (p / "sources").is_dir()), None)
    if mount is None:
        raise RuntimeError("Could not find Windows setup files on the mounted ISO.")
    return mount


def editions(info: str) -> list[tuple[int, str, str]]:
    starts = list(re.finditer(r"(?m)^Index:\s*(\d+)\s*$", info))
    available = []
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(info)
        block = info[match.start():end]
        name = re.search(r"(?m)^Name:\s*(.+?)\s*$", block)
        arch = re.search(r"(?m)^Architecture:\s*(.+?)\s*$", block)
        if name and arch and arch.group(1).lower() in {"x86_64", "amd64", "x64"}:
            available.append((int(match.group(1)), re.sub(r"\s+", " ", name.group(1)), arch.group(1)))
    return available


def safe_slug(edition_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", edition_name.lower()).strip("-") or "windows-x64"


def choose_edition(media: Path) -> tuple[int, str]:
    wimlib = PROJECT / ".deps/wimlib/bin/wimlib-imagex"
    source = next((media / "sources" / filename for filename in ("install.wim", "install.esd")
                   if (media / "sources" / filename).is_file()), None)
    if source is None:
        raise RuntimeError("No sources/install.wim or sources/install.esd exists in this ISO.")
    check_resident(source)
    info = run([str(wimlib), "info", str(source)], capture=True).stdout
    options = editions(info)
    if not options:
        raise RuntimeError("No x64 Windows editions were found in this ISO.")
    labels = [f"{index} | {name} ({architecture})" for index, name, architecture in options]
    selected = dialog("choose-edition", *labels)
    index_text, _, _ = selected.partition(" | ")
    try:
        index = int(index_text)
    except ValueError as exc:
        raise RuntimeError("The edition choice could not be read. Please run the builder again.") from exc
    name = next(name for item_index, name, _ in options if item_index == index)
    return index, name


def make_run_folder(parent: Path, edition_name: str) -> Path:
    safe = safe_slug(edition_name)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = parent / f"tiny11-{safe}-{stamp}"
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{base.name}-{suffix}"
        suffix += 1
    candidate.mkdir()
    return candidate


def build_wimlib_if_needed() -> Path:
    binary = PROJECT / ".deps/wimlib/bin/wimlib-imagex"
    if not binary.is_file():
        dialog("notice", "One-time setup", "Building the pinned native image tool. This can take a few minutes.")
        run([sys.executable, str(PROJECT / "tools/build_wimlib.py"),
             "--source", str(PROJECT / ".deps/wimlib-source"),
             "--prefix", str(PROJECT / ".deps/wimlib")])
    if not binary.is_file():
        raise RuntimeError("The native image tool was not created.")
    return binary


def run_wizard() -> int:
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or later is required. Install it, then reopen Build-Tiny11.command.")
    ensure_homebrew_tools()
    iso_text = dialog("choose-iso")
    if Path(iso_text).suffix.lower() != ".iso":
        raise RuntimeError("Choose a Windows .iso file.")
    iso = Path(iso_text).resolve()
    output_text = dialog("choose-folder")
    output_parent = Path(output_text).resolve()
    if getattr(output_parent.stat(), "st_flags", 0) & DATAless:
        raise RuntimeError("Choose a local, downloaded output folder. macOS reports this folder as offloaded.")
    if shutil.disk_usage(output_parent).free < 20 * 1024**3:
        raise RuntimeError("At least 20 GiB of free space is needed to build the installer in this folder.")
    build_wimlib_if_needed()

    mounted = mount_iso(iso)
    try:
        index, edition_name = choose_edition(mounted)
        if platform.machine() != "arm64":
            dialog("notice", "Platform note", "This builder is tested on Apple Silicon. This Mac reports a different processor architecture.")
        output = make_run_folder(output_parent, edition_name)
        slug = safe_slug(edition_name)
        image = output / f"tiny11-{slug}.iso"
        work = output / "work"
        usb = output / "usb-files"
        print(f"Building {edition_name} from {iso.name}…", flush=True)
        run([sys.executable, str(PROJECT / "tiny11-macos.py"), "build", str(mounted),
             "--index", str(index), "--output", str(image), "--scratch", str(work / "image")])
        print("The ISO is ready. Preparing FAT32-compatible USB files…", flush=True)
        try:
            run([sys.executable, str(PROJECT / "tiny11-macos.py"), "usb-files", str(image),
                 "--output", str(usb), "--scratch", str(work / "usb")])
            shutil.copy2(PROJECT / "target/Verify-Tiny11.ps1", usb / "Verify-Tiny11.ps1")
            shutil.copy2(PROJECT / "USB-INSTALL.md", output / "USB-INSTALL.md")
            shutil.copy2(PROJECT / "USB-INSTALL.md", usb / "USB-INSTALL.md")
            shutil.rmtree(work)
            summary = (f"Installer and USB files are ready.\n\nISO: {image}\n\n"
                       f"USB files: {usb}\n\nRead USB-INSTALL.md before formatting a USB. "
                       "Boot, Windows servicing, and Windows Update still need PC testing.")
            print(summary, flush=True)
            dialog("notice", "Installer ready", summary)
        except Exception as exc:
            summary = (f"The ISO is ready:\n{image}\n\nUSB preparation stopped: {exc}\n\n"
                       f"Build files are in {work}. The ISO is preserved.")
            print(summary, flush=True)
            dialog("notice", "ISO ready; USB preparation needs attention", summary)
        subprocess.run(["open", "-R", str(output)], check=False)
        return 0
    finally:
        subprocess.run(["hdiutil", "detach", str(mounted)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    try:
        return run_wizard()
    except Cancelled:
        print("Cancelled. No USB device was changed.")
        return 0
    except Exception as exc:
        message = str(exc)
        print(f"Build stopped: {message}", file=sys.stderr)
        try:
            dialog("notice", "Tiny11 builder stopped", message)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
