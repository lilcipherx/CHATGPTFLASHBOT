# Поднимает Redis (Memurai) + ARQ-воркеры для асинхронной генерации
# (эффекты мини-аппа, видео, музыка, аватары). Запускать ПОСЛЕ того, как в .env
# прописан рабочий ключ провайдера, иначе задачи будут падать на этапе провайдера.
$ErrorActionPreference = "Stop"
$root = "D:\CHATGPTFLASHBOT"
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

# 1. Redis на localhost:6379 — если не слушает, ставим Memurai через winget (UAC).
$redisUp = $false
try { $redisUp = (Test-NetConnection 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue).TcpTestSucceeded } catch {}
if (-not $redisUp) {
  Write-Host "Redis не запущен. Устанавливаю Memurai (потребуется согласие UAC)..." -ForegroundColor Cyan
  winget install --id Memurai.MemuraiDeveloper -e --accept-package-agreements --accept-source-agreements
  Start-Sleep -Seconds 5
  try { $redisUp = (Test-NetConnection 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue).TcpTestSucceeded } catch {}
}
if (-not $redisUp) {
  Write-Host "Redis всё ещё недоступен на 6379. Установите/запустите Redis вручную и повторите." -ForegroundColor Red
  exit 1
}
Write-Host "Redis доступен на localhost:6379." -ForegroundColor Green

# 2. Переключаем .env на реальный Redis.
$envPath = Join-Path $root ".env"
$lines = Get-Content $envPath
if ($lines -match '^REDIS_URL=') { $lines = $lines -replace '^REDIS_URL=.*', 'REDIS_URL=redis://localhost:6379' }
else { $lines += 'REDIS_URL=redis://localhost:6379' }
$lines | Set-Content $envPath -Encoding utf8
Write-Host "REDIS_URL -> redis://localhost:6379" -ForegroundColor Green

# 3. Перезапускаем API + бота, чтобы enqueue шёл в реальный Redis.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*uvicorn*api.main*' -or $_.CommandLine -like '*bot.main*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","api.main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory $root -WindowStyle Hidden
Start-Process -FilePath $py -ArgumentList "-m","bot.main" -WorkingDirectory $root -WindowStyle Hidden

# 4. Запускаем ARQ worker (обработка задач) и beat (планировщик/крон).
$arq = Join-Path $root ".venv\Scripts\arq.exe"
Start-Process -FilePath $arq -ArgumentList "workers.main.WorkerSettings" -WorkingDirectory $root -WindowStyle Hidden
Start-Process -FilePath $arq -ArgumentList "workers.main.BeatSettings" -WorkingDirectory $root -WindowStyle Hidden
Write-Host "ARQ worker + beat запущены." -ForegroundColor Green
Write-Host ""
Write-Host "Готово: async-генерация включена (нужен рабочий ключ провайдера в .env)." -ForegroundColor Yellow
