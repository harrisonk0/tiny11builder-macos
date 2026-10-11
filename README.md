# Tiny11 Builder macOS

Build a Windows 11 x64 installer on Apple Silicon without a Windows VM. The Mac applies the regular Tiny11 registry settings and selected file removals. Microsoft DISM removes provisioned apps and cleans the component store on the target PC during setup.

**This is an experimental hybrid port, not full offline feature parity.** App and component payloads remain in the ISO until Windows services the installed system. The generated installer, Windows servicing, Windows Update, and Zwift must still be tested on the target PC.

The fork preserves the [upstream Tiny11 Builder](https://github.com/ntdevlabs/tiny11builder) scripts. The macOS code in [`macos/`](macos/) has its own [MIT license](macos/LICENSE). The upstream checkout has no LICENSE file; ask its author about reusing the original scripts.

## Requirements

- Apple Silicon Mac, Python 3.10+, Xcode Command Line Tools, Git, and Homebrew.
- At least 20 GiB free during the build. USB preparation later needs 17 GiB free for a temporary non-solid WIM conversion and split image parts.
- Windows 11 x64 installation media and a license for the Windows edition you select. An ARM64 image from the Mac is not for an Intel PC.

## Build the installer

Clone the fork and enter the macOS project:

```sh
git clone https://github.com/harrisonk0/tiny11builder-macos.git
cd tiny11builder-macos/macos
```

Install the Mac tools and build the pinned wimlib helper:

```sh
brew install wimlib hivex cdrtools xorriso autoconf automake libtool pkgconf
python3 tools/build_wimlib.py --source .deps/wimlib-source --prefix .deps/wimlib
```

Open the Windows ISO in Finder to mount it. List its editions using the mounted `sources/install.wim` (or `install.esd`):

```sh
python3 tiny11-macos.py inspect "/path/to/mounted-media/sources/install.wim"
```

Choose the index for the edition your license covers. Edition indexes differ between images. Then create a new scratch directory and output folder, and build the ISO:

```sh
mkdir -p work build-output
python3 tiny11-macos.py build "/path/to/windows11-x64.iso" \
  --index 6 \
  --output build-output/tiny11-macos.iso \
  --scratch work/tiny11-build
```

Replace `6` with the index you selected. This changes the answer file to install that single exported edition at index 1. The command preserves the source ISO and refuses existing output or scratch paths. It uses low thread counts and macOS background priority. If Finder shows a cloud-only icon for the ISO or build files, choose **Download Now / Keep Downloaded** before starting; macOS may offload large files from synced folders.

Read [`macos/BUILD.md`](macos/BUILD.md) for the complete workflow, compression options, limitations, and troubleshooting. [`macos/PARITY.md`](macos/PARITY.md) maps each upstream operation to its Mac or target-side implementation.

## Prepare a USB on the Mac

The install image is solid-compressed and larger than FAT32's 4 GiB single-file limit. Prepare split WIM files for a UEFI USB:

```sh
python3 tiny11-macos.py usb-files build-output/tiny11-macos.iso \
  --output build-output/tiny11-usb-files \
  --scratch work/tiny11-usb-conversion
```

Use a USB drive of 16 GB or larger. In Disk Utility, show all devices, select the USB, and erase it as **MS-DOS (FAT)** with **Master Boot Record** scheme. This erases the selected USB. Copy the *contents* of `build-output/tiny11-usb-files` to its root, keeping all `sources/install*.swm` parts together. Boot the PC from the USB's **UEFI** entry. The prepared files support UEFI removable-media boot; legacy BIOS USB boot is not prepared.

In Windows Setup, choose the intended install drive. Removing its existing partitions erases its data. Setup still asks you to accept the license and complete account setup. The builder does not activate Windows; use a valid license for the edition you selected.

## Check the Windows installation

After first boot, open an elevated Windows PowerShell and read the servicing state:

```powershell
Get-Content "$env:WINDIR\Setup\Tiny11MacOS\servicing-state.json" -Raw
```

`complete: true` means the scheduled DISM cleanup returned success and the targeted provisioned packages were absent on its final check. Pending or failed status means the deferred work is incomplete. See `servicing.log` in the same folder for errors. The target task can retry at the next boot or logon.

Copy [`macos/target/Verify-Tiny11.ps1`](macos/target/Verify-Tiny11.ps1) to the PC and run it from elevated PowerShell. Then check component health and Windows Update:

```powershell
DISM.exe /Online /Cleanup-Image /ScanHealth
```

Also test installing and running Zwift on the target PC. Firmware boot, setup/OOBE, DISM execution, Windows Update, activation, and Zwift performance have not been verified by the Mac build. `ResetBase` prevents uninstalling superseded updates.

## Development

```sh
cd macos
python3 -m py_compile ./*.py tools/*.py
python3 -m unittest discover -s tests -v
```

GitHub Actions runs these syntax and unit checks on macOS. The upstream scripts remain at the fork root; the macOS port discovers the pinned regular builder there.
