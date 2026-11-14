# 部署/更新脚本：同步代码 → 自动选可用端口 → 重建容器
# 用法：powershell -ExecutionPolicy Bypass -File deploy.ps1
$src = "D:\Projects\ST"
$dst = "E:\server\aistudy"

# 1) 同步代码
foreach ($d in @("backend", "frontend", "deploy", "docs")) {
    if (Test-Path "$src\$d") {
        robocopy "$src\$d" "$dst\$d" /E /XD node_modules __pycache__ data dist .git /NFL /NDL /NJH /NJS | Out-Null
    }
}
foreach ($f in @("Dockerfile", "Dockerfile.full", "docker-compose.yml", ".dockerignore", "README.md")) {
    Copy-Item "$src\$f" "$dst\$f" -Force
}

# 2) 自动选可用端口（Windows WINNAT 动态排除区间会变化，故每次检测）
$ranges = @()
netsh interface ipv4 show excludedportrange protocol=tcp | ForEach-Object {
    if ($_ -match '^\s*(\d+)\s+(\d+)\s*$') { $ranges += ,@([int]$matches[1], [int]$matches[2]) }
}
function Test-FreePort($p) {
    foreach ($r in $ranges) { if ($p -ge $r[0] -and $p -le $r[1]) { return $false } }
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    return -not $conn
}
$port = $null
foreach ($c in @(28080, 25800, 18000, 9000, 5000, 8000)) {
    if (Test-FreePort $c) { $port = $c; break }
}
if (-not $port) { $port = 28080 }
Set-Content -Path "$dst\.env" -Value "APP_PORT=$port" -Encoding ASCII
Write-Output "使用端口：$port"

# 3) 重建
Set-Location $dst
docker compose up -d --build
Write-Output "部署完成：http://localhost:$port"
