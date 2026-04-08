param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw "ASSERT FAILED: $Message"
    }
}

function Post-Incident {
    param(
        [string]$BaseUrl,
        [string]$TenantId,
        [string]$ReporterEmail,
        [string]$Description,
        [string]$AttachmentPath = ""
    )

    $args = @(
        "-s",
        "-X", "POST",
        "$BaseUrl/api/incidents/submit",
        "-F", "tenant_id=$TenantId",
        "-F", "reporter_email=$ReporterEmail",
        "-F", "description=$Description"
    )

    if ($AttachmentPath -ne "") {
        $args += @("-F", "attachment=@$AttachmentPath;type=text/plain")
    }

    $raw = & curl.exe @args
    if (-not $raw) {
        throw "No response from submit endpoint."
    }
    return $raw | ConvertFrom-Json
}

Write-Host "Running AURA E2E smoke test against $BaseUrl" -ForegroundColor Cyan

$health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
Assert-True ($health.status -eq "ok") "Health endpoint is not ok"

$runId = Get-Date -Format "yyyyMMddHHmmss"
$tenantA = "smoke-a-$runId"
$tenantB = "smoke-b-$runId"

$tenantBodyA = @{ tenant_id = $tenantA; name = "Smoke Tenant A" } | ConvertTo-Json
$tenantBodyB = @{ tenant_id = $tenantB; name = "Smoke Tenant B" } | ConvertTo-Json

Invoke-RestMethod -Uri "$BaseUrl/api/tenants/register" -Method Post -ContentType "application/json" -Body $tenantBodyA | Out-Null
Invoke-RestMethod -Uri "$BaseUrl/api/tenants/register" -Method Post -ContentType "application/json" -Body $tenantBodyB | Out-Null

$tmpFile = Join-Path $env:TEMP "aura-smoke-$runId.txt"
Set-Content -Path $tmpFile -Value "Checkout failed with HTTP 500 during smoke test"

try {
    $a1 = Post-Incident -BaseUrl $BaseUrl -TenantId $tenantA -ReporterEmail "a1@demo.com" -Description "Checkout outage with coupon and payment 500" -AttachmentPath $tmpFile
    $a2 = Post-Incident -BaseUrl $BaseUrl -TenantId $tenantA -ReporterEmail "a2@demo.com" -Description "Auth timeout after login refresh token"
    $b1 = Post-Incident -BaseUrl $BaseUrl -TenantId $tenantB -ReporterEmail "b1@demo.com" -Description "Catalog product listing degraded"

    Assert-True ($a1.tenant_id -eq $tenantA) "Tenant A incident 1 has wrong tenant_id"
    Assert-True ($a2.tenant_id -eq $tenantA) "Tenant A incident 2 has wrong tenant_id"
    Assert-True ($b1.tenant_id -eq $tenantB) "Tenant B incident has wrong tenant_id"

    $resolvedA1 = Invoke-RestMethod -Uri "$BaseUrl/api/incidents/$($a1.incident_id)/resolve" -Method Post
    Assert-True ($resolvedA1.status -eq "resolved") "Incident A1 was not resolved"

    $dashA = Invoke-RestMethod -Uri "$BaseUrl/api/tenants/$tenantA/dashboard" -Method Get
    $dashB = Invoke-RestMethod -Uri "$BaseUrl/api/tenants/$tenantB/dashboard" -Method Get

    Assert-True ($dashA.total_incidents -eq 2) "Tenant A total incidents should be 2"
    Assert-True ($dashA.resolved_incidents -eq 1) "Tenant A resolved incidents should be 1"
    Assert-True ($dashA.open_incidents -eq 1) "Tenant A open incidents should be 1"
    Assert-True ($dashB.total_incidents -eq 1) "Tenant B total incidents should be 1"
    Assert-True ($dashB.resolved_incidents -eq 0) "Tenant B resolved incidents should be 0"

    $summary = [PSCustomObject]@{
        status         = "PASS"
        tenant_a       = $tenantA
        tenant_b       = $tenantB
        incident_ids   = @($a1.incident_id, $a2.incident_id, $b1.incident_id)
        tenant_a_dash  = $dashA
        tenant_b_dash  = $dashB
    }

    $summary | ConvertTo-Json -Depth 8
}
finally {
    Remove-Item -Force $tmpFile -ErrorAction SilentlyContinue
}
