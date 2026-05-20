# Sends a sample payload to the n8n webhook.
# Usage:
#   .\send-payload.ps1 -File sample-payloads\01-valid-high-acme.json
#   .\send-payload.ps1 -File sample-payloads\09-idempotency-replay.json -Repeat 3
#
# Override the webhook URL with -Url or the WEBHOOK_URL env var.
param(
    [Parameter(Mandatory = $true)][string]$File,
    [int]$Repeat = 1,
    [string]$Url = $(if ($env:WEBHOOK_URL) { $env:WEBHOOK_URL } else { "http://localhost:5678/webhook/lead-intake" })
)

if (-not (Test-Path $File)) {
    Write-Error "payload file not found: $File"
    exit 1
}

$body = Get-Content $File -Raw

for ($i = 1; $i -le $Repeat; $i++) {
    Write-Host "`n--- request $i/$Repeat -> $Url ---" -ForegroundColor Cyan
    try {
        $resp = Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json" -Body $body
        $resp | ConvertTo-Json -Depth 5
    }
    catch {
        Write-Host "HTTP error: $($_.Exception.Message)" -ForegroundColor Yellow
        if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message }
    }
}
