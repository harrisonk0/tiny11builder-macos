# Native macOS installer builder

This project builds an **experimental x64 Windows installer natively on Apple Silicon macOS**, using the regular Tiny11 Builder's configuration at commit `00e7d8a151a39ccffccab4a267bb81fb3756a01d`. Registry changes and file removals happen inside the WIM on the Mac. Provisioned-app removal and component cleanup are deferred to Microsoft's DISM on the destination laptop during/after Windows Setup.

This is a hybrid implementation. It is **not an independently implemented native DISM engine, and not a verified full-parity replacement for the offline upstream builder**. The remaining Appx files occupy space in the ISO until Windows removes them on the target. Compatibility with a given Windows build, OOBE, hardware bypasses, and the Windows servicing payload requires an installation test on that target.

## Prerequisites

- Apple Silicon macOS, tested on macOS 27.2 / ARM64.
- Xcode Command Line Tools, Python 3.10+, Git, and Homebrew.
- At least 20 GiB of free disk space for staging, compression, and the resulting ISO; allow more for larger media.
- A legitimately obtained Windows 11 **x64** ISO and a Windows license for the selected edition. ARM64 installation media cannot be used for an Intel x64 target.

Keep large source/build files downloaded. macOS offloaded some multi-GB files in this Documents workspace and subsequent reads timed out. If Finder shows cloud-only content, choose Download Now/Keep Downloaded first. Prefer a non-synced local location for heavy scratch files; the CLI accepts an explicit scratch path. Offloaded source ISOs are rejected before large reads begin.

```sh
cd macos
brew install wimlib hivex cdrtools xorriso autoconf automake libtool pkgconf
python3 tools/build_wimlib.py --source .deps/wimlib-source --prefix .deps/wimlib
```

Run these commands from the cloned repository root; the first changes into `macos/`. The wimlib helper checks a pinned source revision (`cd5e231c348c255ae5088873b5a66ee0eb96fa07`) and adds a small metadata-preservation patch. It builds a private ARM64 executable and does not replace Homebrew's installation. The patch retains the replaced hive's Windows security descriptor, file attributes, timestamps, extra metadata, and short name; it rejects hard-linked, multi-stream, encrypted, and reparse files. The builder compares the original and final WIM metadata and refuses to package the image if it differs.

Upstream choices are read from the audited script as data; the PowerShell builder itself is never executed on the Mac. A SHA-256 check rejects unreviewed changes to that script.

## Build

Mount your ISO in Finder and inspect `sources/install.wim` with the `inspect` subcommand to find the edition index. Pick the edition covered by your license; an existing Home license does not license Pro.

```sh
python3 tiny11-macos.py build \
  "/path/to/windows11-x64.iso" \
  --index 6 \
  --output /path/to/outputs/tiny11-macos-pro-deferred.iso \
  --scratch /path/to/work/tiny11-pro-build
```

Output and scratch paths must be new. The source is mounted read-only, and the output must be outside the scratch tree. Build failures retain staging and diagnostic files. Use a different scratch path for another attempt, or remove only the failed build's generated staging directory after inspection.

The workflow:

1. Export the selected x64 edition to index 1 in a separate WIM.
2. Apply all 61 upstream install registry operations to extracted hives using hivex, preserving unrelated values.
3. Apply all 10 upstream setup registry operations to boot.wim index 2.
4. Replace those hives through the patched wimlib and verify both their bytes and Windows metadata inside the actual WIM.
5. Delete the 10 upstream Edge/OneDrive/task paths, using Windows-style case matching, and check that those paths are absent.
6. Insert an original Windows setup payload and answer file. The answer file chooses index 1, enables compact deployment, requests upstream's OOBE choices, and runs package removal in the specialize pass before initial profile creation. Partition selection, license acceptance, and account creation remain interactive.
7. Recompress the modified image with LZMS solid compression, verify all WIM file data, then package BIOS/UEFI El Torito entries with ISO9660/Joliet/UDF using mkisofs.
8. Write a JSON build report with the output SHA-256, native validation results, and an explicit indication that target servicing has not been tested.

The build is repeatable from pinned source inputs. Byte-identical ISO output is not promised: WIM GUIDs and packaging timestamps can differ between runs.

LZMS effort defaults to level 20 with one thread to keep the Apple Silicon build practical. Override with `--compression-level 50 --threads 4` if you prefer more compression effort and have sufficient memory/time. The compression algorithm matches upstream's recovery mode; exact compressed size/bytes do not. Image work runs with macOS background policy and nice priority 19.

## Prepare FAT32 USB files

```sh
python3 tiny11-macos.py usb-files /path/to/tiny11-macos-pro-deferred.iso \
  --output /path/to/outputs/tiny11-usb-files \
  --scratch /path/to/work/tiny11-usb-conversion
```

The command prepares files in a new directory. It does not format or write a USB device. It exports the solid LZMS image into normal LZX first because wimlib cannot split solid resources, then creates `install.swm` parts with a 3800 MiB target size. It verifies the entire split image, compares edition metadata, and rejects any file at or above FAT32's 4 GiB limit. Allow 17 GiB of free space for conversion and file preparation; the temporary LZX image is removed on success.

Format a 16 GB or larger USB as MS-DOS (FAT) / Master Boot Record in Disk Utility and copy the prepared directory's **contents** to its root. Formatting erases that selected USB. Boot the laptop's UEFI USB entry. This prepares UEFI removable-media files; it does not install a legacy BIOS USB boot sector. Keep all `install*.swm` parts together under `sources`.

To independently check a generated ISO against staging without a VM:

```sh
python3 tools/verify_media.py /path/to/output.iso \
  --tree /path/to/build-scratch/media \
  --report /path/to/media-checks.json
```

This verifies the raw El Torito validation checksum, BIOS/EFI boot image bytes, mounted WIM/answer-file/EFI-loader hashes, and x64 PE machine type. It does not execute the firmware or Windows setup.

## Windows-side servicing

The installed payload lives at `C:\Windows\Setup\Tiny11MacOS`. `Service-Tiny11.ps1 -Phase Provision` enumerates provisioned packages through Windows' DISM module, removes the identities matching upstream's 52 unique package prefixes, checks the remaining list, and registers a SYSTEM task for component cleanup. This uses Microsoft servicing rather than approximating provisioning state with file/registry deletion.

The task `Tiny11MacOS-Finalize` waits for Windows Setup to finish and runs:

```text
DISM.exe /English /Online /Cleanup-Image /StartComponentCleanup /ResetBase
```

Pending setup/update work can cause DISM to fail. Failures are recorded and the task remains available for a later boot/logon. A zero exit code and an empty remaining-package list mark completion and remove the task. The payload never initiates a reboot automatically. As with upstream's ResetBase operation, the cleanup removes the ability to uninstall superseded updates.

Inspect `servicing-state.json` and `servicing.log` in that folder. Until the state reports `complete: true`, the deferred configuration is incomplete. The project includes `target/Verify-Tiny11.ps1`, which can be copied to the PC and run from elevated Windows PowerShell. It checks servicing completion and remaining targeted packages and records service availability. It does **not** prove Windows Update or component health.

For a target validation, also run `DISM /Online /Cleanup-Image /ScanHealth`, check Windows Update, and install/test Zwift on the laptop. None of those target checks has been run here.

## Verified and unverified

Verified on this Mac: reading the supplied ISO, real Pro edition export, hive mutation and preservation of unrelated values, all setup-hive changes written back to a real boot.wim while preserving its Windows security metadata, configuration extraction, answer-file structure, native Python tests, and PowerShell structural syntax via tree-sitter. Microsoft's PowerShell runtime failed to initialize on this macOS build, so the Windows payload has not been executed here.

Windows package-removal execution, the scheduled task, OOBE/local-account behavior, firmware boot, installation, Windows Update, and Zwift performance remain unverified. Build success and a valid boot catalog do not establish those outcomes. The Core variant is excluded: it deliberately destroys servicing support and does not meet the laptop's intended use.

Check the processor, memory, storage, firmware mode, and Windows edition against your intended target. The registry values reproduce upstream's unsupported-hardware bypass; they do not make unsupported hardware officially supported. Each edition still requires a valid Windows license. This project makes no performance promise for any application on the target PC.

## Licensing

Original helper code is licensed under MIT; the wimlib source modification retains upstream's LGPL terms. Dependencies are separately licensed: wimlib tools GPLv3+, hivex LGPL/GPL, cdrtools CDDL, and xorriso GPL. Build tooling does not grant rights to redistribute Windows, bundled applications, or their installation media. Obtain Windows from Microsoft, comply with its edition's license, and keep your generated installer for your own authorized use.

No license file was present in the audited Tiny11 Builder checkout. This project does not bundle its scripts and makes no claim to license its code. The upstream configuration remains attributed to ntdevlabs; check with its authors before redistributing derivative material.

## Primary references

- [Tiny11 Builder](https://github.com/ntdevlabs/tiny11builder)
- [hivex API and write semantics](https://libguestfs.org/hivex.3.html)
- [wimlib update implementation](https://github.com/ebiggers/wimlib/blob/cd5e231c348c255ae5088873b5a66ee0eb96fa07/src/update_image.c)
- [Microsoft specialize RunSynchronous](https://learn.microsoft.com/en-us/windows-hardware/customize/desktop/unattend/microsoft-windows-deployment-runsynchronous)
- [DISM provisioned-app servicing](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/dism-app-package--appx-or-appxbundle--servicing-command-line-options)
- [Microsoft component-store cleanup](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/clean-up-the-winsxs-folder)
