param(
    [int]$Port = 8000,
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

function Get-LocalIPAddress {
    try {
        $socket = [System.Net.Sockets.Socket]::new(
            [System.Net.Sockets.AddressFamily]::InterNetwork,
            [System.Net.Sockets.SocketType]::Dgram,
            [System.Net.Sockets.ProtocolType]::Udp
        )
        $socket.Connect("8.8.8.8", 80)
        $ip = $socket.LocalEndPoint.Address.ToString()
        $socket.Close()
        return $ip
    } catch {
        return "localhost"
    }
}

function Test-MarketingBotEndpoint {
    param([int]$Port)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2
        return ($response.Content -match "Marketing Bot")
    } catch {
        return $false
    }
}

$connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($connections.Count -eq 0) {
    exit 0
}

$isMarketingBot = Test-MarketingBotEndpoint -Port $Port
$localIp = Get-LocalIPAddress

foreach ($connection in $connections) {
    $owner = [int]$connection.OwningProcess
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue
    $name = if ($process) { $process.Name } else { "unknown" }
    $commandLine = if ($process -and $process.CommandLine) { $process.CommandLine } else { "" }

    $looksLikeMarketingBot =
        $isMarketingBot -or
        (
            $name -match "python" -and
            (
                $commandLine -match "main\.py" -or
                $commandLine -match "uvicorn\s+main:app" -or
                $commandLine -match "main:app"
            )
        )

    if (-not $looksLikeMarketingBot) {
        Write-Host "Port $Port is already in use by PID $owner ($name)."
        if ($commandLine) {
            Write-Host "Command line: $commandLine"
        }
        Write-Host "Stop that process first, or choose another port."
        exit 1
    }

    if ($Restart) {
        Write-Host "Stopping existing Marketing Bot server on port $Port (PID $owner)."
        Stop-Process -Id $owner -Force
        Start-Sleep -Seconds 1
    } else {
        Write-Host "Marketing Bot server is already running on port $Port (PID $owner)."
        Write-Host "Local:   http://localhost:$Port"
        Write-Host "Network: http://$localIp`:$Port"
        Write-Host "Leaving the running server untouched."
        exit 2
    }
}

exit 0
