Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

while ($true) {
  try {
    & "$PSScriptRoot\\run_web.ps1"
  } catch {
    Write-Host "streamlit stopped: $($_.Exception.Message)"
  }

  Write-Host "restarting in 5 seconds..."
  Start-Sleep -Seconds 5
}
