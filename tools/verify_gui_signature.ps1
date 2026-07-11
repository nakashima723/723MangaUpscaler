param(
    [string]$Path = "dist\723MangaUpscaler.exe",
    [string]$ExpectedThumbprint,
    [switch]$TestTamperDetection,
    [switch]$AllowUntrustedRootForTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "AuthenticodeTools.psm1") -Force

$ResolvedPath = (Resolve-Path -LiteralPath $Path).Path
$SignTool = Resolve-SignTool
$Signature = Get-AuthenticodeSignature -LiteralPath $ResolvedPath
if ($Signature.Status -ne "Valid" -and -not (
    $AllowUntrustedRootForTest -and
    $Signature.Status -in @("UnknownError", "NotTrusted") -and
    $Signature.SignerCertificate
)) {
    throw "Authenticode signature is not trusted and valid: $($Signature.Status)"
}
if (-not $Signature.SignerCertificate) {
    throw "The executable has no Authenticode signer certificate."
}
if (-not $Signature.TimeStamperCertificate) {
    throw "The executable has no trusted timestamp."
}

$CodeSigningOid = "1.3.6.1.5.5.7.3.3"
$HasCodeSigningEku = $Signature.SignerCertificate.EnhancedKeyUsageList |
    Where-Object { $_.ObjectId -eq $CodeSigningOid }
if (-not $HasCodeSigningEku) {
    throw "The signer certificate is not valid for code signing."
}

if ($ExpectedThumbprint) {
    $NormalizedExpected = $ExpectedThumbprint.Replace(" ", "").ToUpperInvariant()
    if ($Signature.SignerCertificate.Thumbprint -ne $NormalizedExpected) {
        throw "Unexpected signer thumbprint: $($Signature.SignerCertificate.Thumbprint)"
    }
}

$VerifyResult = Invoke-SignTool -SignToolPath $SignTool -Arguments @(
    "verify", "/pa", "/all", "/tw", "/v", $ResolvedPath
)
if ($VerifyResult.StandardOutput) {
    Write-Host $VerifyResult.StandardOutput
}
if ($VerifyResult.StandardError) {
    Write-Warning $VerifyResult.StandardError
}
if ($VerifyResult.ExitCode -ne 0 -and -not $AllowUntrustedRootForTest) {
    throw "SignTool verification failed with exit code $($VerifyResult.ExitCode)."
}
if ($VerifyResult.ExitCode -ne 0 -and $AllowUntrustedRootForTest) {
    Write-Warning "SignTool rejected the untrusted test chain as expected."
}

if ($TestTamperDetection) {
    $TamperedPath = Join-Path ([IO.Path]::GetTempPath()) (
        "723MangaUpscaler_tamper_" + [guid]::NewGuid().ToString("N") + ".exe"
    )
    try {
        Copy-Item -LiteralPath $ResolvedPath -Destination $TamperedPath
        $Stream = [IO.File]::Open($TamperedPath, "Open", "ReadWrite", "None")
        try {
            $Offset = [Math]::Min(4096, $Stream.Length - 1)
            $Stream.Position = $Offset
            $OriginalByte = $Stream.ReadByte()
            $Stream.Position = $Offset
            $Stream.WriteByte($OriginalByte -bxor 1)
        }
        finally {
            $Stream.Dispose()
        }

        $TamperedSignature = Get-AuthenticodeSignature -LiteralPath $TamperedPath
        if ($TamperedSignature.Status -ne "HashMismatch") {
            throw "Tamper detection did not report HashMismatch: $($TamperedSignature.Status)"
        }
        $TamperResult = Invoke-SignTool -SignToolPath $SignTool -Arguments @(
            "verify", "/pa", "/all", "/tw", $TamperedPath
        )
        if ($TamperResult.ExitCode -eq 0) {
            throw "SignTool accepted the tampered executable."
        }
    }
    finally {
        Remove-Item -LiteralPath $TamperedPath -Force -ErrorAction SilentlyContinue
    }
}

$Hash = Get-FileHash -LiteralPath $ResolvedPath -Algorithm SHA256
[pscustomobject]@{
    Path = $ResolvedPath
    Bytes = (Get-Item -LiteralPath $ResolvedPath).Length
    SHA256 = $Hash.Hash
    SignerSubject = $Signature.SignerCertificate.Subject
    SignerThumbprint = $Signature.SignerCertificate.Thumbprint
    TimestampSubject = $Signature.TimeStamperCertificate.Subject
    Status = $Signature.Status
}
