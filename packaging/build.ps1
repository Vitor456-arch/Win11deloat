param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Push-Location (Join-Path $PSScriptRoot '..')
try {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Use a numeric major.minor.patch version' }
    New-Item -ItemType Directory -Force build | Out-Null
    python -m PyInstaller --noconfirm --clean --windowed --onedir --name ClearWindows packaging/launcher.py 2>&1 | Tee-Object -FilePath build/pyinstaller-release.log
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $app = (Resolve-Path 'dist/ClearWindows').Path
    Copy-Item README.md,LICENSE,THIRD-PARTY.md $app
    Copy-Item docs $app -Recurse -Force
    Copy-Item packaging/INSTALL-NOTES.txt $app
    python packaging/collect_notices.py $app
    if ($LASTEXITCODE -ne 0) { throw 'Dependency notice collection failed' }
    New-Item -ItemType Directory -Force release | Out-Null
    $output = (Resolve-Path 'release').Path
    Compress-Archive -Path $app -DestinationPath "$output/ClearWindows-$Version-Portable-x64.zip" -Force
    $compilers = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe"
    )
    $compiler = $compilers | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $compiler) { throw 'Inno Setup 6/7 is required. Install the official Inno Setup compiler first.' }
    & $compiler "/DAppVersion=$Version" "/DAppSource=$app" "/DOutputPath=$output" packaging/installer.iss 2>&1 | Tee-Object -FilePath build/installer-release.log
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed' }
    $hashes = Get-ChildItem "$output/*.exe", "$output/*.zip" | Sort-Object Name | ForEach-Object {
        $hash = Get-FileHash $_.FullName -Algorithm SHA256
        "$($hash.Hash.ToLowerInvariant())  $($_.Name)"
    }
    $hashes | Set-Content "$output/SHA256SUMS.txt" -Encoding ascii
} catch {
    $message = $_.Exception.Message
    foreach ($file in @('build/pyinstaller-release.log', 'build/installer-release.log')) {
        if (Test-Path $file) { $message += "`n" + ((Get-Content $file -Tail 30) -join "`n") }
    }
    $message = $message.Replace('%','%25').Replace("`r",'%0D').Replace("`n",'%0A')
    Write-Output "::error title=Windows packaging failed::$message"
    throw
} finally { Pop-Location }
