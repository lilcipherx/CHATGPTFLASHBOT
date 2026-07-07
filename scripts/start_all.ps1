# Запускает локально API (мини-апп + админка + REST) и Telegram-бота.
# Безопасно запускать повторно: уже работающие процессы не дублируются.
$ErrorActionPreference = "Stop"
$root = "D:\CHATGPTFLASHBOT"
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

function Running($pattern) {
  $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
       Where-Object { $_.CommandLine -like $pattern }
  return [bool]$p
}

# API
if (Running '*uvicorn*api.main*') {
  Write-Host "API уже работает." -ForegroundColor Yellow
} else {
  Write-Host "Запускаю API на http://localhost:8000 ..." -ForegroundColor Cyan
  Start-Process -FilePath $py `
    -ArgumentList "-m","uvicorn","api.main:app","--host","0.0.0.0","--port","8000","--log-level","info" `
    -WorkingDirectory $root -WindowStyle Hidden
  Start-Sleep -Seconds 3
}

# Бот
if (Running '*bot.main*') {
  Write-Host "Бот уже работает." -ForegroundColor Yellow
} else {
  Write-Host "Запускаю Telegram-бота (polling) ..." -ForegroundColor Cyan
  Start-Process -FilePath $py -ArgumentList "-m","bot.main" -WorkingDirectory $root -WindowStyle Hidden
}

Write-Host ""
Write-Host "Локально готово:" -ForegroundColor Green
Write-Host "  Mini App: http://localhost:8000/"
Write-Host "  Админка:  http://localhost:8000/admin   (создайте админа: python -m scripts.create_admin)"  # FIX: X7
Write-Host "  Бот:      @chatgpt_flashbot"
Write-Host ""
Write-Host "Чтобы дать ссылку другим людям — запустите ПОДЕЛИТЬСЯ.bat" -ForegroundColor Magenta
