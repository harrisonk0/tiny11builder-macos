# Tiny11 Builder macOS

Choose a Windows 11 x64 ISO, pick a licensed edition, and build an installer and USB files on macOS. No Windows VM is needed. DISM runs on the installed PC for app removal and component cleanup.

**Experimental hybrid port:** app and component payloads stay in the ISO until Windows services the installed system. Windows Setup, servicing, updates, and app performance have not been verified on a target PC.

## What you need

- An Apple Silicon Mac with Xcode Command Line Tools, Homebrew, and Python 3.10 or later. The launcher installs missing Homebrew packages after you approve the prompt.
- Legitimate Windows 11 **x64** installation media and a valid license for the edition you choose. ARM64 media from the Mac is for a different processor architecture.
- About **30 GiB free** to build the ISO and USB files in one run. Large files should be downloaded and kept local; macOS may offload them from synced folders.

## Build and prepare a USB

1. Clone this fork:

   ```sh
   git clone https://github.com/harrisonk0/tiny11builder-macos.git
   ```

2. In Finder, open `tiny11builder-macos/macos` and double-click **Build-Tiny11.command**.
3. Choose the Windows ISO, the edition your license covers, and an output folder. The Mac builds the ISO and prepares the split WIM files for a UEFI USB.
4. In Disk Utility, choose **View → Show All Devices**. Select a USB drive of at least 16 GB and erase it as **MS-DOS (FAT)** with **Master Boot Record** scheme. This erases that USB drive.
5. Copy the *contents* of the generated `usb-files` folder to the USB root. Keep all `sources/install*.swm` files together. Boot the target PC using its **UEFI USB** entry. The builder prepares files; it does not format or write to the USB device.

The output folder contains `tiny11-<edition>.iso`, `usb-files`, and `USB-INSTALL.md`. Read that guide before installing. Windows Setup still asks you to select the installation drive, accept license terms, and finish account setup. Removing existing drive partitions erases their data.

## Check the Windows installation

After first boot, open elevated PowerShell and check whether deferred servicing completed:

```powershell
Get-Content "$env:WINDIR\Setup\Tiny11MacOS\servicing-state.json" -Raw
```

`complete: true` means the app and component cleanup checks succeeded. Check `servicing.log` if it is pending or failed. Then run `DISM.exe /Online /Cleanup-Image /ScanHealth`, check Windows Update, activate Windows with your license, and test your apps.

`ResetBase` prevents uninstalling superseded updates. The unsupported-hardware registry values mirror the upstream builder; they do not change Microsoft's support policy. Full feature parity and Windows Update compatibility remain unverified until a target PC installation is tested.

## Technical notes

The macOS port lives in [`macos/`](macos/README.md). See [`macos/BUILD.md`](macos/BUILD.md) for command-line use and prerequisites, [`macos/PARITY.md`](macos/PARITY.md) for feature differences, and [`CONTRIBUTING.md`](CONTRIBUTING.md) for development checks.

The MIT license in `macos/LICENSE` covers the new macOS code only. The fork keeps the upstream Windows scripts, and the upstream repository has no LICENSE file; ask its author before reusing those scripts.
