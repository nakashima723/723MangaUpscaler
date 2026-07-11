param(
    [string]$Name = "723MangaUpscaler"
)

$ErrorActionPreference = "Stop"

function Resolve-OfficialMsvcRedistributable {
    $VsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $VsWhere)) {
        throw "Visual Studio Installer vswhere.exe was not found. Install the official VC++ x64 redistributables before building."
    }
    $VisualStudioPath = & $VsWhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Redist.14.Latest `
        -property installationPath
    if ($LASTEXITCODE -ne 0 -or -not $VisualStudioPath) {
        throw "A licensed Visual Studio installation with VC++ redistributables is required."
    }
    $RedistRoot = Join-Path $VisualStudioPath "VC\Redist\MSVC"
    $VersionDirectories = Get-ChildItem -LiteralPath $RedistRoot -Directory |
        Where-Object { $_.Name -match '^\d+(\.\d+)+$' } |
        Sort-Object { [version]$_.Name } -Descending
    foreach ($VersionDirectory in $VersionDirectories) {
        $CrtDirectory = Join-Path $VersionDirectory.FullName "x64\Microsoft.VC143.CRT"
        $OpenMpDirectory = Join-Path $VersionDirectory.FullName "x64\Microsoft.VC143.OpenMP"
        $MsvcpPath = Join-Path $CrtDirectory "msvcp140.dll"
        $VcompPath = Join-Path $OpenMpDirectory "vcomp140.dll"
        if ((Test-Path -LiteralPath $MsvcpPath) -and (Test-Path -LiteralPath $VcompPath)) {
            foreach ($BinaryPath in @($MsvcpPath, $VcompPath)) {
                $Signature = Get-AuthenticodeSignature -LiteralPath $BinaryPath
                $VersionInfo = [Diagnostics.FileVersionInfo]::GetVersionInfo($BinaryPath)
                if ($Signature.Status -ne "Valid" -or
                    $Signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation' -or
                    $VersionInfo.CompanyName -ne "Microsoft Corporation") {
                    throw "Untrusted Microsoft runtime binary: $BinaryPath"
                }
            }
            return [pscustomobject]@{
                Root = $VersionDirectory.FullName
                CrtDirectory = $CrtDirectory
                OpenMpDirectory = $OpenMpDirectory
                MsvcpPath = $MsvcpPath
                VcompPath = $VcompPath
            }
        }
    }
    throw "Official x64 MSVC and OpenMP redistributable DLLs were not found under $RedistRoot."
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $RepoRoot
try {
    $MsvcRedistributable = Resolve-OfficialMsvcRedistributable
    $OriginalPath = $env:PATH
    $env:PATH = "$($MsvcRedistributable.CrtDirectory);$($MsvcRedistributable.OpenMpDirectory);$OriginalPath"
    $CustomTkinterPath = python -c "import customtkinter, pathlib; print(pathlib.Path(customtkinter.__file__).parent)"
    if ($LASTEXITCODE -ne 0 -or -not $CustomTkinterPath) {
        throw "Could not resolve the CustomTkinter package directory."
    }
    $CustomTkinterData = "$CustomTkinterPath\assets;customtkinter\assets"
    $DiplibPath = python -c "import diplib, pathlib; print(pathlib.Path(diplib.__file__).parent)"
    if ($LASTEXITCODE -ne 0 -or -not $DiplibPath) {
        throw "Could not resolve the DIPlib package directory."
    }
    $DiplibBinary = "$DiplibPath\DIP.dll;diplib"
    $HookDirectory = Join-Path $RepoRoot "tools\pyinstaller_hooks"
    $SciPyRuntimeHook = Join-Path $HookDirectory "runtime_scipy_special_stub.py"
    $LicenseBundlePath = Join-Path $RepoRoot "build\license_bundle"
    python tools\collect_distribution_licenses.py $LicenseBundlePath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not collect third-party license files."
    }
    $LicenseBundleData = "$LicenseBundlePath;licenses\third_party"
    $VersionFile = Join-Path $RepoRoot "config\windows_version_info.txt"
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --noupx `
        --name $Name `
        --version-file $VersionFile `
        --paths src `
        --additional-hooks-dir $HookDirectory `
        --runtime-hook $SciPyRuntimeHook `
        --add-data "config;config" `
        --add-data $CustomTkinterData `
        --add-data "LICENSE;licenses" `
        --add-data "THIRD_PARTY_NOTICES.md;licenses" `
        --add-data $LicenseBundleData `
        --add-binary $DiplibBinary `
        --add-binary "$($MsvcRedistributable.MsvcpPath);." `
        --add-binary "$($MsvcRedistributable.VcompPath);." `
        --exclude-module pytest `
        --exclude-module _pytest `
        --exclude-module matplotlib `
        --exclude-module PySide6 `
        --exclude-module PyQt5 `
        --exclude-module PyQt6 `
        --exclude-module IPython `
        --exclude-module pandas `
        --exclude-module sympy `
        --exclude-module cffi `
        --exclude-module distutils `
        --exclude-module pkg_resources `
        --exclude-module psutil `
        --exclude-module pycparser `
        --exclude-module setuptools `
        --exclude-module win32pdh `
        --exclude-module PIL.AvifImagePlugin `
        --exclude-module PIL._avif `
        --exclude-module scipy.cluster `
        --exclude-module scipy.constants `
        --exclude-module scipy.datasets `
        --exclude-module scipy.fft `
        --exclude-module scipy.fftpack `
        --exclude-module scipy.integrate `
        --exclude-module scipy.interpolate `
        --exclude-module scipy.io `
        --exclude-module scipy.misc `
        --exclude-module scipy.odr `
        --exclude-module scipy.optimize `
        --exclude-module scipy.signal `
        --exclude-module scipy.special `
        --exclude-module scipy.linalg `
        --exclude-module scipy.sparse `
        --exclude-module scipy.spatial `
        --exclude-module scipy.stats `
        --exclude-module diplib.javaio `
        --exclude-module diplib.PyDIPjavaio `
        --exclude-module diplib.PyDIPviewer `
        src\mlu\gui.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed to build $Name."
    }
    $AnalysisPath = Join-Path $RepoRoot "build\$Name\Analysis-00.toc"
    $AnalysisText = (Get-Content -LiteralPath $AnalysisPath -Raw).Replace('\\', '\')
    if ($AnalysisText -match 'ImageMagick') {
        throw "The build collected a binary from ImageMagick instead of an approved build dependency."
    }
    $SpecPath = Join-Path $RepoRoot "$Name.spec"
    $SpecText = (Get-Content -LiteralPath $SpecPath -Raw).Replace('\\', '\')
    foreach ($ExpectedRuntime in @(
        $MsvcRedistributable.MsvcpPath,
        $MsvcRedistributable.VcompPath
    )) {
        if ($SpecText -notmatch [regex]::Escape($ExpectedRuntime)) {
            throw "The build did not use the verified Microsoft runtime: $ExpectedRuntime"
        }
    }
}
finally {
    if ($null -ne $OriginalPath) {
        $env:PATH = $OriginalPath
    }
    Pop-Location
}
