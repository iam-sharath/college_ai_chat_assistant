$port = 3000
$connection = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($connection) {
    $pids = $connection | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $pids) {
        Write-Host "Killing stale process on port $port (PID $processId)..." -ForegroundColor Yellow
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
} else {
    Write-Host "Port $port is free, no stale process found." -ForegroundColor Green
}
Write-Host "Starting backend..." -ForegroundColor Cyan
npm start