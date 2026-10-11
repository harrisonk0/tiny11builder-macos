# Install from the USB

1. Use a USB drive with at least 16 GB capacity. In Disk Utility, choose View → Show All Devices, select the USB device, and erase it as **MS-DOS (FAT)** with **Master Boot Record** scheme. Erasing removes existing files on that USB.
2. Copy the *contents* of the `usb-files` folder to the USB root. Keep every `sources/install*.swm` file together.
3. Connect the USB to the target PC and boot its **UEFI USB** entry. The prepared drive targets UEFI; it doesn't install a legacy BIOS USB boot sector.
4. In Windows Setup, select the intended installation drive and edition covered by your license. Removing old partitions erases their data. Setup still asks you to accept the license and complete account setup.
5. After the first boot, open elevated Windows PowerShell and inspect the servicing state:

   ```powershell
   Get-Content "$env:WINDIR\Setup\Tiny11MacOS\servicing-state.json" -Raw
   ```

   `complete: true` means deferred cleanup succeeded. If it is pending or failed, check `servicing.log` in the same folder. Use `Verify-Tiny11.ps1` from the USB or repository to check the configuration. Then run `DISM.exe /Online /Cleanup-Image /ScanHealth`, check Windows Update, and test the applications you need.

If setup or servicing fails, keep the error and local `servicing.log`. Redact usernames and local paths before sharing diagnostics publicly.
