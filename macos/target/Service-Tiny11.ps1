# Original installer payload. DISM servicing executes on the destination PC.
[CmdletBinding()]
param([ValidateSet('Provision', 'Finalize')][string]$Phase = 'Provision')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$statePath = Join-Path $root 'servicing-state.json'
$logPath = Join-Path $root 'servicing.log'
$taskName = 'Tiny11MacOS-Finalize'
$config = Get-Content -LiteralPath (Join-Path $root 'config.json') -Raw | ConvertFrom-Json
$state = @{ phase = $Phase; complete = $false; startedUtc = [DateTime]::UtcNow.ToString('o');
            upstreamCommit = $config.upstream_commit; removedPackages = @(); errors = @() }
if (($Phase -eq 'Finalize') -and (Test-Path -LiteralPath $statePath)) {
    $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $state.removedPackages = @($previous.removedPackages)
    $state.errors = @($previous.errors)
}

function Save-State {
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding UTF8
}

function Find-TargetPackages {
    $packages = @(Get-AppxProvisionedPackage -Online -ErrorAction Stop)
    @($packages | Where-Object {
        $identity = ($_.PackageName -split '_')[0]
        $matching = @($config.package_prefixes | Where-Object { $_ -ieq $identity })
        $matching.Count -gt 0
    })
}

try {
    Start-Transcript -Path $logPath -Append | Out-Null
    Import-Module Dism -ErrorAction Stop
    if ($Phase -eq 'Provision') {
        # specialize runs before OOBE creates the initial user profile.
        foreach ($package in @(Find-TargetPackages)) {
            Remove-AppxProvisionedPackage -Online -PackageName $package.PackageName -ErrorAction Stop | Out-Null
            $state.removedPackages += $package.PackageName
            Save-State
        }
        $remaining = @(Find-TargetPackages)
        if ($remaining.Count -gt 0) { throw 'Target provisioned packages remain after removal.' }
        $exe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
                     (Join-Path $root 'Service-Tiny11.ps1') + '" -Phase Finalize'
        $action = New-ScheduledTaskAction -Execute $exe -Argument $arguments
        # Retries at startup/logon allow pending Windows setup servicing to finish.
        $triggers = @(New-ScheduledTaskTrigger -AtStartup; New-ScheduledTaskTrigger -AtLogOn)
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
                    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
                              -Principal $principal -Settings $settings -Force | Out-Null
        $state.phase = 'provisioning-complete-cleanup-pending'
        Save-State
    } else {
        # Wait up to 30 minutes for Windows Setup to release the component store.
        $setup = 'HKLM:\SYSTEM\Setup'
        $ready = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            $values = Get-ItemProperty -LiteralPath $setup
            if (($values.SystemSetupInProgress -eq 0) -and ($values.OOBEInProgress -ne 1)) {
                $ready = $true
                break
            }
            Start-Sleep -Seconds 30
        }
        if (-not $ready) { throw 'Windows setup is still in progress; cleanup will retry on a later boot.' }
        $state.phase = 'component-cleanup'
        Save-State
        & "$env:WINDIR\System32\dism.exe" /English /Online /Cleanup-Image /StartComponentCleanup /ResetBase
        $code = $LASTEXITCODE
        $state.dismExitCode = $code
        if ($code -ne 0) { throw "DISM cleanup returned $code. A restart may be needed; scheduled task is retained." }
        $remaining = @(Find-TargetPackages)
        if ($remaining.Count -gt 0) { throw 'Target provisioned packages reappeared; inspect servicing.log.' }
        $state.phase = 'complete'
        $state.complete = $true
        $state.finishedUtc = [DateTime]::UtcNow.ToString('o')
        Save-State
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    }
    Stop-Transcript | Out-Null
    exit 0
} catch {
    $state.errors += $_.Exception.Message
    $state.phase = 'failed-' + $Phase
    Save-State
    Write-Error $_ -ErrorAction Continue
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}
