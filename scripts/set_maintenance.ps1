param(
    [ValidateSet("on", "off", "toggle", "auto")]
    [string]$State = "toggle"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StatusFile = Join-Path $RepoRoot "docs\status.json"

function Get-GitHubToken {
    $cred = "protocol=https`nhost=github.com`n`n" | git credential fill
    $line = ($cred -split "`n" | Where-Object { $_ -like "password=*" })
    if ($line) { return $line.Substring(9).Trim() }
    return $null
}

function Set-RemoteMaintenance([bool]$IsMaint) {
    $payloadObj = @{
        maintenance = $IsMaint
        target_version = "4.0.2"
        updated_at = (Get-Date).ToString("o")
    }
    $jsonText = $payloadObj | ConvertTo-Json
    if (Test-Path (Split-Path $StatusFile -Parent)) {
        [System.IO.File]::WriteAllText($StatusFile, $jsonText, (New-Object System.Text.UTF8Encoding $false))
    }

    $token = Get-GitHubToken
    if (-not $token) {
        Write-Host "GitHub kimlik bilgisi bulunamadi; yalnizca yerel status.json guncellendi." -ForegroundColor Yellow
        return
    }

    $headers = @{
        Authorization = "Bearer $token"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
    $uri = "https://api.github.com/repos/Beytarchiver/beytarchiver.github.io/contents/status.json"
    $sha = $null
    try {
        $existing = Invoke-RestMethod -Method Get -Uri $uri -Headers $headers
        $sha = $existing.sha
    } catch {}

    $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($jsonText))
    $body = @{
        message = if ($IsMaint) { "chore: enable maintenance mode (active in VS Code)" } else { "chore: disable maintenance mode (site live)" }
        content = $b64
    }
    if ($sha) { $body.sha = $sha }

    $null = Invoke-RestMethod -Method Put -Uri $uri -Headers $headers -Body ($body | ConvertTo-Json) -ContentType "application/json"
    if ($IsMaint) {
        Write-Host "🛠️ [BAKIM MODU AKTIF] https://beytarchiver.github.io su anda 'Bakim & Guncelleme Yapiliyor' ekraninda!" -ForegroundColor Yellow
    } else {
        Write-Host "🟢 [SITE CANLIDA] https://beytarchiver.github.io normal gorunume dondu!" -ForegroundColor Green
    }
}

if ($State -eq "on") {
    Set-RemoteMaintenance $true
} elseif ($State -eq "off") {
    Set-RemoteMaintenance $false
} elseif ($State -eq "toggle") {
    $cur = $false
    if (Test-Path $StatusFile) {
        try { $cur = (Get-Content $StatusFile -Raw | ConvertFrom-Json).maintenance } catch {}
    }
    Set-RemoteMaintenance (-not $cur)
} elseif ($State -eq "auto") {
    Set-RemoteMaintenance $true
    Write-Host "VS Code acik oldugu surece bakim modu aktif kalacak." -ForegroundColor Cyan
    Write-Host "Bakim modunu kapatmak icin bu terminalde Ctrl+C veya Enter tusuna basabilirsiniz..." -ForegroundColor Cyan
    try {
        $null = Read-Host
    } finally {
        Set-RemoteMaintenance $false
    }
}
