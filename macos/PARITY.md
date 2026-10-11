# Parity with regular Tiny11 Builder

Reference: ntdevlabs/tiny11builder at `00e7d8a151a39ccffccab4a267bb81fb3756a01d`, regular `tiny11maker.ps1`. Core is excluded.

| Upstream operation | Current implementation | Verification |
|---|---|---|
| WIM/ESD image selection | Native wimlib x64 image export | Real Windows 11 Pro index 6 exported and read back |
| Copy installation media | Read-only ISO attachment and separate staging | Used in actual build |
| Install-image registry configuration | All 61 upstream set/delete operations using hivex | Each committed hive checked, then WIM contents read back; Windows metadata compared |
| Setup-image registry configuration | All 10 operations in boot.wim index 2 | Actual boot WIM mutation, metadata, and content checks passed |
| Edge/OneDrive/task files | All 10 upstream paths removed through WIM archive update | Case-insensitive archive absence checks |
| Provisioned Appx removal | Upstream's 52 unique package identities supplied to Windows DISM during specialize | Deferred; target execution unverified |
| Component cleanup / ResetBase | Windows DISM after setup, via SYSTEM scheduled task | Deferred; target execution unverified |
| Unattend and compact installation | Original answer file with index 1, Compact and OOBE settings | XML structure checked; Windows processing unverified |
| Recovery compression | LZMS solid compression after native modifications | Native build step; source/image GUIDs differ from DISM |
| BIOS + EFI installer ISO | Native mkisofs with UDF/ISO9660/Joliet and dual El Torito boot entries | Catalog and media checks; firmware boot unverified |
| Windows Update and feature servicing | Component store retained; Microsoft DISM used for deferred cleanup | Actual updates/features not tested |

## Exact differences

The port creates the installer entirely on macOS but performs Appx deprovisioning and ResetBase on the installed Windows system. Upstream performs those operations offline before ISO creation. Therefore the generated ISO still carries those Appx/component bytes and is not the same offline image as upstream's Tiny11 output.

The upstream answer file places `ConfigureChatAutoInstall` outside a settings pass. This port does not reproduce that malformed/undocumented placement; it applies the upstream Chat/Teams registry policies and uses documented OOBE settings. LZMS compression effort is configurable and defaults to 20/one thread; byte/size parity is not claimed.

Registry/file operations are applied before setup, with Windows metadata preserved. The package-removal configuration uses exact package identities corresponding to upstream's prefixes; upstream's PowerShell substring selection has ambiguous matching behavior. Runtime package choices and servicing results need confirmation on the target.

No VM is required. Windows DISM still runs on the destination laptop. This is an experimental hybrid solution, not full macOS-native offline feature parity. Native structural verification cannot establish firmware boot, OOBE, Windows servicing, update compatibility, or application performance.
