# AuditGym one-line installer for Windows (PowerShell 5.1 or 7).
#
#   irm is.gd/auditgym | iex
#
# Without the short link:  irm https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.ps1 | iex
# (the short link points there; the Release workflow publishes every tagged build to this public repository)
#   Team, newest CI build of a branch (GitHub CLI logged in):
#     $env:AUDITGYM_BRANCH='main'; gh api "repos/ibrahimerbol01-prog/auditgym/contents/desktop/install.ps1?ref=main" -H "Accept: application/vnd.github.raw" | Out-String | iex
#
# Installs into %LOCALAPPDATA%\Programs\AuditGym (no admin rights), checks the download against the release's
# SHA256SUMS.txt, adds a Start menu shortcut, puts the `auditgym` terminal command on the user PATH, and starts the app.
# Options (environment variables): AUDITGYM_VERSION=v1.0.0 (default: latest release), AUDITGYM_NO_LAUNCH=1,
# AUDITGYM_BRANCH=<branch> (the newest successful "Desktop app" CI build of that branch instead of a release),
# AUDITGYM_ZIP=C:\path\AuditGym-windows-x64.zip (install a local build, for testing), AUDITGYM_BASE_URL=<mirror>.
& {
    # Scoped to this block, so running the one-liner does not change the caller's session settings.
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is much faster without the progress bar
    $Repo = 'ibrahimerbol01-prog/auditgym'                 # CI branch builds (AUDITGYM_BRANCH; artifacts need gh)
    $Public = $Repo                                        # releases: the default, plain HTTPS, no login
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
        $stamp = Join-Path $Tmp 'BUILD.txt'
        $Branch = $env:AUDITGYM_BRANCH
        $gh = Get-Command gh -ErrorAction SilentlyContinue
        $ghReady = $false
        if ($gh -and -not $env:AUDITGYM_BASE_URL -and -not $env:AUDITGYM_ZIP) {  # also needed for AUDITGYM_BRANCH
            & gh auth status *> $null
            $ghReady = ($LASTEXITCODE -eq 0)
        }

        if ($env:AUDITGYM_ZIP) {
            Say "installing local build $($env:AUDITGYM_ZIP)"
            Copy-Item $env:AUDITGYM_ZIP $zip
        } elseif ($Branch) {
            if (-not $ghReady) { Fail 'installing a branch build needs the GitHub CLI, logged in (gh auth login)' }
            $runId = & gh run list -R $Repo --workflow desktop.yml --branch $Branch --status success --limit 1 --json databaseId --jq '.[0].databaseId'
            if ($LASTEXITCODE -ne 0 -or -not $runId) { Fail "no successful desktop build of branch '$Branch' yet (see the Actions tab)" }
            Say "downloading $Asset from the newest build of branch '$Branch' (run $runId)"
            & gh run download $runId -R $Repo -n ($Asset -replace '\.zip$', '') -D $Tmp
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $zip)) { Fail "run $runId has no $Asset (it may have expired; push again or run the workflow)" }
        } else {
            $base = if ($env:AUDITGYM_BASE_URL) { $env:AUDITGYM_BASE_URL } elseif ($Version -eq 'latest') { "https://github.com/$Public/releases/latest/download" } else { "https://github.com/$Public/releases/download/$Version" }
            Say "downloading $Asset ($Version)"
            try {
                Invoke-WebRequest -UseBasicParsing -Uri "$base/$Asset" -OutFile $zip
                Invoke-WebRequest -UseBasicParsing -Uri "$base/SHA256SUMS.txt" -OutFile $sums
            } catch { Fail "download failed: $($_.Exception.Message)" }
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
        Get-Process -Name AuditGym, auditgym -ErrorAction SilentlyContinue | Stop-Process -Force
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
        $cliDir = Join-Path $dest 'cli'
        if (Test-Path (Join-Path $cliDir 'auditgym.exe')) {
            # The terminal command: add its folder to the user PATH once (no admin rights), and to this window now.
            $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
            if (-not (($userPath -split ';') -contains $cliDir)) {
                $newPath = if ($userPath) { $userPath.TrimEnd(';') + ';' + $cliDir } else { $cliDir }
                [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
            }
            if (-not (($env:Path -split ';') -contains $cliDir)) { $env:Path = $env:Path.TrimEnd(';') + ';' + $cliDir }
            Say 'terminal command: auditgym   (try: auditgym run-agent --policy reconcile)'
        }
        if (Test-Path $stamp) { Say "version: $((Get-Content $stamp -Raw).Trim())" } elseif (-not $env:AUDITGYM_ZIP) { Say "version: $Version release" }
        Say 'the app is not code-signed: if SmartScreen asks, choose More info, then Run anyway'
        if (-not $env:AUDITGYM_NO_LAUNCH) { Start-Process -FilePath $exe -WorkingDirectory $dest }
        Say 'done'
        # Success: do not leave a native command's exit code (e.g. "gh auth status" = 1 when logged out) behind
        # for the caller; CI steps and scripts read $LASTEXITCODE.
        $global:LASTEXITCODE = 0
    } finally {
        Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
    }
}
