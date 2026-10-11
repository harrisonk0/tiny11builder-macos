[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:WINDIR 'Setup\Tiny11MacOS'
$config = Get-Content -LiteralPath (Join-Path $root 'config.json') -Raw | ConvertFrom-Json
$state = Get-Content -LiteralPath (Join-Path $root 'servicing-state.json') -Raw | ConvertFrom-Json
$packages = @(Get-AppxProvisionedPackage -Online | Where-Object {
    $config.package_prefixes -icontains (($_.PackageName -split '_')[0])
})
$services = @('wuauserv', 'TrustedInstaller', 'WinDefend') | ForEach-Object {
    $service = Get-CimInstance Win32_Service -Filter "Name='$_'"
    @{ name = $_; found = ($null -ne $service); startMode = $service.StartMode; state = $service.State }
}
$report = @{ servicingComplete = $state.complete; servicingPhase = $state.phase;
             unwantedProvisionedPackages = @($packages.PackageName); services = @($services);
             upstreamCommit = $config.upstream_commit; checkedUtc = [DateTime]::UtcNow.ToString('o') }
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $root 'verification.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 8
$badServices = @($services | Where-Object { (-not $_.found) -or ($_.startMode -eq 'Disabled') })
if (-not $state.complete -or $packages.Count -gt 0 -or $badServices.Count -gt 0) { exit 1 }
Write-Output 'Configuration checks passed. Next verify DISM /Online /Cleanup-Image /ScanHealth and Windows Update on this PC.'
exit 0
