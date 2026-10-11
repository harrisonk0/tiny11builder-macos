"""Read the pinned upstream's declarative choices without executing PowerShell."""
import hashlib
import re
import shlex
from pathlib import Path

UPSTREAM_COMMIT = "00e7d8a151a39ccffccab4a267bb81fb3756a01d"
UPSTREAM_SHA256 = "7a7baffa75742d9ae9512936d72887931c8bc2a91ac16ccd451a8869752b6f5e"
HIVES = {"SYSTEM": "Windows/System32/config/SYSTEM",
         "SOFTWARE": "Windows/System32/config/SOFTWARE",
         "DEFAULT": "Windows/System32/config/DEFAULT",
         "NTUSER": "Users/Default/NTUSER.DAT"}
DELETE_FILES = [
    "Program Files (x86)/Microsoft/Edge", "Program Files (x86)/Microsoft/EdgeUpdate",
    "Program Files (x86)/Microsoft/EdgeCore", "Windows/System32/Microsoft-Edge-Webview",
    "Windows/System32/OneDriveSetup.exe",
    "Windows/System32/Tasks/Microsoft/Windows/Application Experience/Microsoft Compatibility Appraiser",
    "Windows/System32/Tasks/Microsoft/Windows/Customer Experience Improvement Program",
    "Windows/System32/Tasks/Microsoft/Windows/Application Experience/ProgramDataUpdater",
    "Windows/System32/Tasks/Microsoft/Windows/Chkdsk/Proxy",
    "Windows/System32/Tasks/Microsoft/Windows/Windows Error Reporting/QueueReporting",
]


def load(upstream):
    path = Path(upstream) / "tiny11maker.ps1"
    if hashlib.sha256(path.read_bytes()).hexdigest() != UPSTREAM_SHA256:
        raise RuntimeError("Upstream script differs from the audited revision; refusing to interpret it")
    text = path.read_text(encoding="utf-8-sig")
    install = text.split('Write-Output "Bypassing system requirements(on the system image):"', 1)[1]
    install = install.split('Write-Host "Deleting scheduled task definition files..."', 1)[0]
    boot = text.split('Write-Output "Bypassing system requirements(on the setup image):"', 1)[1]
    boot = boot.split('Write-Output "Tweaking complete!"', 1)[0]
    result = {"upstream_commit": UPSTREAM_COMMIT,
              "script_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "files_to_delete": DELETE_FILES, "install": [], "boot": []}
    for section, body in (("install", install), ("boot", boot)):
        for line in body.splitlines():
            if line.startswith(("Set-RegistryValue ", "Remove-RegistryValue ")):
                tokens = shlex.split(line)
                if tokens[0] == "Set-RegistryValue" and len(tokens) != 5:
                    raise RuntimeError(f"Unrecognized upstream setting: {line}")
                if tokens[0] == "Remove-RegistryValue" and len(tokens) != 2:
                    raise RuntimeError(f"Unrecognized upstream deletion: {line}")
                root, hive, key = tokens[1].split("\\", 2)
                if root not in ("HKLM", "HKEY_LOCAL_MACHINE") or not hive.startswith("z"):
                    raise RuntimeError(f"Unexpected hive mapping: {tokens[1]}")
                hive = hive[1:].upper()
                if hive not in HIVES:
                    raise RuntimeError(f"Unknown hive: {hive}")
                operation = {"action": "set" if len(tokens) == 5 else "delete", "hive": hive, "key": key}
                if len(tokens) == 5:
                    operation.update(name=tokens[2], type=tokens[3], value=tokens[4])
                result[section].append(operation)
    prefixes = text.split("$packagePrefixes =", 1)[1].split("$packagesToRemove =", 1)[0]
    result["package_prefixes"] = sorted(set(re.findall(r"'([^']+)'", prefixes)))
    if len(result["install"]) != 61 or len(result["boot"]) != 10:
        raise RuntimeError(f"Unexpected upstream registry counts: {len(result['install'])}, {len(result['boot'])}")
    return result
