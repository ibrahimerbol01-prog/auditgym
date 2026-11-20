# AuditGym one-line installer for Windows (PowerShell 5.1 or 7).
#
#   Private repo (team, GitHub CLI logged in):
#     gh release download -R ibrahimerbol01-prog/auditgym -p install.ps1 -O - | Out-String | iex
#   Public repo:
#     irm https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.ps1 | iex
#
# Installs into %LOCALAPPDATA%\Programs\AuditGym (no admin rights), checks the download against the release's
# SHA256SUMS.txt, adds a Start menu shortcut and starts the app.
# Options (environment variables): AUDITGYM_VERSION=v1.0.0 (default: latest release), AUDITGYM_NO_LAUNCH=1,
# AUDITGYM_ZIP=C:\path\AuditGym-windows-x64.zip (install a local build, for testing), AUDITGYM_BASE_URL=<mirror>.
& {
    # Scoped to this block, so running the one-liner does not change the caller's session settings.
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is much faster without the progress bar
    $Repo = 'ibrahimerbol01-prog/auditgym'
    $Version = if ($env:AUDITGYM_VERSION) { $env:AUDITGYM_VERSION } else { 'latest' }
    function Say([string]$Message) { Write-Host "AuditGym installer: $Message" }
    function Fail([string]$Message) { throw "AuditGym installer: error: $Message" }

    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($arch -ne 'AMD64') { Fail "no Windows build for $arch yet; run from source instead: see desktop/README.md" }
    $Asset = 'AuditGym-windows-x64.zip'

    $Tmp = Join-Path ([IO.Path]::GetTempPath()) ("auditgym-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $Tmp | Out-Null
    try {
        $zip = Join-Path $Tmp $Asset
        $sums = Join-Path $Tmp 'SHA256SUMS.txt'
        $gh = Get-Command gh -ErrorAction SilentlyContinue
        $ghReady = $false
        if ($gh -and -not $env:AUDITGYM_BASE_URL) { & gh auth status *> $null; $ghReady = ($LASTEXITCODE -eq 0) }

        if ($env:AUDITGYM_ZIP) {
            Say "installing local build $($env:AUDITGYM_ZIP)"
            Copy-Item $env:AUDITGYM_ZIP $zip
        } elseif ($ghReady) {
            Say "downloading $Asset ($Version) with the GitHub CLI"
            $tagArgs = @(); if ($Version -ne 'latest') { $tagArgs = @($Version) }
            & gh release download @tagArgs -R $Repo -p $Asset -p 'SHA256SUMS.txt' -D $Tmp
            if ($LASTEXITCODE -ne 0) { Fail 'gh release download failed' }
        } else {
            $base = if ($env:AUDITGYM_BASE_URL) { $env:AUDITGYM_BASE_URL } elseif ($Version -eq 'latest') { "https://github.com/$Repo/releases/latest/download" } else { "https://github.com/$Repo/releases/download/$Version" }
            Say "downloading $Asset ($Version)"
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "$base/$Asset" -OutFile $zip
                Invoke-WebRequest -UseBasicParsing -Uri "$base/SHA256SUMS.txt" -OutFile $sums
            } catch { Fail 'download failed (a private repo needs the GitHub CLI: gh auth login)' }
        }

        if (Test-Path $sums) {
            $line = Get-Content $sums | Where-Object { $_ -match ([regex]::Escape($Asset) + '$') } | Select-Object -First 1
            if (-not $line) { Fail "$Asset is not listed in SHA256SUMS.txt" }
            $want = ($line -split '\s+')[0].ToLowerInvariant()
            $have = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLowerInvariant()
            if ($have -ne $want) { Fail "checksum mismatch for $Asset; not installing" }
            Say 'checksum OK'
        }

        $dest = Join-Path $env:LOCALAPPDATA 'Programs\AuditGym'
        Get-Process -Name AuditGym -ErrorAction SilentlyContinue | Stop-Process -Force
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null   # %LOCALAPPDATA%\Programs may not exist yet
        $unpacked = Join-Path $Tmp 'x'
        Expand-Archive -Path $zip -DestinationPath $unpacked
        Move-Item (Join-Path $unpacked 'AuditGym') $dest
        $exe = Join-Path $dest 'AuditGym.exe'
        if (-not (Test-Path $exe)) { Fail 'AuditGym.exe missing from the download' }

        $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
        New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut((Join-Path $startMenu 'AuditGym.lnk'))
        $lnk.TargetPath = $exe
        $lnk.WorkingDirectory = $dest
        $lnk.Description = 'AuditGym: RL environment for audit agents (offline)'
        $lnk.Save()

        Say "installed $dest (Start menu: AuditGym)"
        Say 'the app is not code-signed: if SmartScreen asks, choose More info, then Run anyway'
        if (-not $env:AUDITGYM_NO_LAUNCH) { Start-Process -FilePath $exe -WorkingDirectory $dest }
        Say 'done'
    } finally {
        Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
    }
}
