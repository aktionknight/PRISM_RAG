# start.ps1
Write-Host "Starting PRISM_RAG Docker Stack (Engine + Observability + Ollama)..."
docker compose up -d

Write-Host "Waiting for Ollama to initialize..."
$ollamaReady = $false
$retries = 0
while (-not $ollamaReady -and $retries -lt 30) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $ollamaReady = $true
        }
    } catch {
        Start-Sleep -Seconds 2
        $retries++
    }
}

if ($ollamaReady) {
    Write-Host "Ollama is ready! Pulling the qwen2.5:7b-instruct model (this might take a few minutes depending on network speed)..."
    docker compose exec ollama ollama pull qwen2.5:7b-instruct
    Write-Host "`nAll services are up and running!"
    Write-Host "---------------------------------------------------"
    Write-Host "Main Web Interface: http://localhost:8000"
    Write-Host "Grafana Dashboard:  http://localhost:3000 (admin/slrag)"
    Write-Host "Prometheus Metrics: http://localhost:9090"
    Write-Host "---------------------------------------------------"
} else {
    Write-Host "Warning: Ollama failed to start within the expected time."
}
