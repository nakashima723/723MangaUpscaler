param(
    [string]$Path = "dist\723MangaUpscaler.exe",
    [Parameter(Mandatory = $true)]
    [string]$CertificateThumbprint,
    [ValidateSet("CurrentUser", "LocalMachine")]
    [string]$StoreLocation = "CurrentUser",
    [uri]$TimestampServer = "http://timestamp.digicert.com",
    [switch]$ReplaceExistingSignature,
    [switch]$AllowUntrustedRootForTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "AuthenticodeTools.psm1") -Force

$ResolvedPath = (Resolve-Path -LiteralPath $Path).Path
$CurrentSignature = Get-AuthenticodeSignature -LiteralPath $ResolvedPath
if ($CurrentSignature.Status -ne "NotSigned" -and -not $ReplaceExistingSignature) {
    throw "The executable is already signed. Use -ReplaceExistingSignature explicitly."
}

$Thumbprint = $CertificateThumbprint.Replace(" ", "").ToUpperInvariant()
$CertificatePath = "Cert:\$StoreLocation\My\$Thumbprint"
$Certificate = Get-Item -LiteralPath $CertificatePath -ErrorAction Stop
if (-not $Certificate.HasPrivateKey) {
    throw "The signing certificate has no accessible private key."
}
if ($Certificate.NotBefore.ToUniversalTime() -gt [DateTime]::UtcNow -or
    $Certificate.NotAfter.ToUniversalTime() -le [DateTime]::UtcNow) {
    throw "The signing certificate is not currently valid."
}
$CodeSigningOid = "1.3.6.1.5.5.7.3.3"
$HasCodeSigningEku = $Certificate.EnhancedKeyUsageList |
    Where-Object { $_.ObjectId -eq $CodeSigningOid }
if (-not $HasCodeSigningEku) {
    throw "The selected certificate does not have the Code Signing EKU."
}

$SignTool = Resolve-SignTool
$StagePath = Join-Path (Split-Path $ResolvedPath -Parent) (
    "." + [IO.Path]::GetFileNameWithoutExtension($ResolvedPath) + "." +
    [guid]::NewGuid().ToString("N") + ".signing.exe"
)
$BackupPath = Join-Path (Split-Path $ResolvedPath -Parent) (
    "." + [IO.Path]::GetFileNameWithoutExtension($ResolvedPath) + "." +
    [guid]::NewGuid().ToString("N") + ".unsigned-backup.exe"
)
try {
    Copy-Item -LiteralPath $ResolvedPath -Destination $StagePath
    $SignArguments = @(
        "sign", "/v", "/fd", "SHA256", "/sha1", $Thumbprint,
        "/s", "My", "/tr", $TimestampServer.AbsoluteUri,
        "/td", "SHA256", "/d", "723 Manga Upscaler"
    )
    if ($StoreLocation -eq "LocalMachine") {
        $SignArguments += "/sm"
    }
    $SignArguments += $StagePath

    $SignResult = Invoke-SignTool -SignToolPath $SignTool -Arguments $SignArguments
    if ($SignResult.StandardOutput) {
        Write-Host $SignResult.StandardOutput
    }
    if ($SignResult.StandardError) {
        Write-Warning $SignResult.StandardError
    }
    if ($SignResult.ExitCode -ne 0) {
        throw "SignTool signing failed with exit code $($SignResult.ExitCode)."
    }

    $StageVerifyArguments = @{
        Path = $StagePath
        ExpectedThumbprint = $Thumbprint
        AllowUntrustedRootForTest = $AllowUntrustedRootForTest
    }
    & (Join-Path $PSScriptRoot "verify_gui_signature.ps1") @StageVerifyArguments | Out-Null

    [IO.File]::Replace($StagePath, $ResolvedPath, $BackupPath, $true)
    Remove-Item -LiteralPath $BackupPath -Force
}
finally {
    Remove-Item -LiteralPath $StagePath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BackupPath -Force -ErrorAction SilentlyContinue
}

$FinalVerifyArguments = @{
    Path = $ResolvedPath
    ExpectedThumbprint = $Thumbprint
    TestTamperDetection = $true
    AllowUntrustedRootForTest = $AllowUntrustedRootForTest
}
& (Join-Path $PSScriptRoot "verify_gui_signature.ps1") @FinalVerifyArguments
