# Делает локальный проект доступным по публичной ссылке (для теста другими людьми).
# Запускает cloudflared-туннель -> получает https-ссылку -> прописывает её в .env
# (MINIAPP_URL) -> перезапускает бота, чтобы кнопка "Открыть приложение" вела на
# этот адрес. Держите окно ОТКРЫТЫМ — пока оно открыто, ссылка работает.
$ErrorActionPreference = "Stop"
$root = "D:\CHATGPTFLASHBOT"
Set-Location $root

$cf = Join-Path $root "cloudflared.exe"
$py = Join-Path $root ".venv\Scripts\python.exe"
$errLog = Join-Path $root "tunnel_share.err.log"
$outLog = Join-Path $root "tunnel_share.out.log"
foreach ($f in @($errLog, $outLog)) { if (Test-Path $f) { Remove-Item $f -Force } }

Write-Host "1/4  Запускаю туннель cloudflared..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $cf `
  -ArgumentList "tunnel","--url","http://localhost:8000","--no-autoupdate" `
  -RedirectStandardError $errLog -RedirectStandardOutput $outLog -PassThru -WindowStyle Hidden

# cloudflared печатает адрес в stderr — ждём появления ссылки
$url = $null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  foreach ($f in @($errLog, $outLog)) {
    if (Test-Path $f) {
      $m = Select-String -Path $f -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($m) { $url = $m.Matches[0].Value; break }
    }
  }
  if ($url) { break }
}
if (-not $url) {
  Write-Host "Не удалось получить ссылку. Смотрите $errLog" -ForegroundColor Red
  exit 1
}
Write-Host "2/4  Публичная ссылка: $url" -ForegroundColor Green

# Прописываем MINIAPP_URL в .env (заменяем строку или добавляем)
$envPath = Join-Path $root ".env"
$lines = Get-Content $envPath
if ($lines -match '^MINIAPP_URL=') {
  $lines = $lines -replace '^MINIAPP_URL=.*', "MINIAPP_URL=$url"
} else {
  $lines += "MINIAPP_URL=$url"
}
$lines | Set-Content $envPath -Encoding utf8
Write-Host "3/4  .env обновлён (MINIAPP_URL)." -ForegroundColor Green

# Перезапускаем бота, чтобы он подхватил новый MINIAPP_URL
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*bot.main*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
Start-Process -FilePath $py -ArgumentList "-m","bot.main" -WorkingDirectory $root -WindowStyle Hidden
Write-Host "4/4  Бот перезапущен." -ForegroundColor Green

Write-Host ""
Write-Host "================ ГОТОВО — отправляйте ссылки ================" -ForegroundColor Yellow
Write-Host "Mini App (в браузере):   $url"
Write-Host "Админка:                 $url/admin"
Write-Host "Telegram-бот:            @chatgpt_flashbot (кнопка 'Открыть приложение' ведёт сюда)"
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "НЕ ЗАКРЫВАЙТЕ это окно — пока оно открыто, ссылка работает." -ForegroundColor Magenta
Write-Host "Чтобы остановить доступ — закройте это окно (Ctrl+C)." -ForegroundColor Magenta

# Держим скрипт живым, пока жив туннель
Wait-Process -Id $proc.Id
