param(
    [string]$CertificateThumbprint = $env:UPSCALER_SIGNING_CERT_THUMBPRINT,
    [ValidateSet("CurrentUser", "LocalMachine")]
    [string]$StoreLocation = "CurrentUser",
    [uri]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

if (-not $CertificateThumbprint) {
    throw "Set -CertificateThumbprint or UPSCALER_SIGNING_CERT_THUMBPRINT."
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StageName = "723MangaUpscaler_unsigned_stage"
$StagePath = Join-Path $RepoRoot "dist\$StageName.exe"
$FinalPath = Join-Path $RepoRoot "dist\723MangaUpscaler.exe"
$StageSpec = Join-Path $RepoRoot "$StageName.spec"
$StageBuild = Join-Path $RepoRoot "build\$StageName"
$BackupPath = Join-Path $RepoRoot (
    "dist\.723MangaUpscaler." + [guid]::NewGuid().ToString("N") + ".previous-release.exe"
)

try {
    & (Join-Path $PSScriptRoot "build_gui_exe.ps1") -Name $StageName
    if (-not (Test-Path -LiteralPath $StagePath)) {
        throw "Unsigned-stage build failed."
    }

    & (Join-Path $PSScriptRoot "sign_gui_exe.ps1") `
        -Path $StagePath `
        -CertificateThumbprint $CertificateThumbprint `
        -StoreLocation $StoreLocation `
        -TimestampServer $TimestampServer | Out-Null

    if (Test-Path -LiteralPath $FinalPath) {
        [IO.File]::Replace($StagePath, $FinalPath, $BackupPath, $true)
        Remove-Item -LiteralPath $BackupPath -Force
    }
    else {
        Move-Item -LiteralPath $StagePath -Destination $FinalPath
    }

    & (Join-Path $PSScriptRoot "verify_gui_signature.ps1") `
        -Path $FinalPath `
        -ExpectedThumbprint $CertificateThumbprint `
        -TestTamperDetection
}
finally {
    foreach ($CleanupPath in @($StagePath, $StageSpec, $StageBuild, $BackupPath)) {
        $AbsoluteCleanupPath = [IO.Path]::GetFullPath($CleanupPath)
        if (-not $AbsoluteCleanupPath.StartsWith(
            $RepoRoot.TrimEnd("\") + "\",
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Refusing cleanup outside the repository: $AbsoluteCleanupPath"
        }
    }
    Remove-Item -LiteralPath $StagePath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StageSpec -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StageBuild -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
}
