# Tiny11 Builder macOS port

An experimental native macOS path for building a Windows 11 x64 installer from the regular Tiny11 Builder configuration. No Windows VM is used. DISM still runs on the target PC for Appx removal and component cleanup.

This fork preserves the upstream Windows builder. The macOS port is in [`macos/`](macos/README.md), with its own scoped [license](macos/LICENSE), setup guide, parity audit, and test suite. The upstream repository has no LICENSE file; check with its author before reusing its scripts.

Native Windows 11 x64 image edits and ISO structure passed local checks. Target-side servicing, booting, installation, and Windows Update still need testing on a PC. See [`macos/BUILD.md`](macos/BUILD.md) before using the experimental installer.

The macOS port isn't a full offline feature-parity replacement: Appx and component-store cleanup happens on the installed PC, so those payloads remain in the ISO. The report and parity audit say exactly which checks ran and which remain unverified.
