# Gera os PNGs das maquetes desta pasta com o Edge headless (1440x900).
# Uso: powershell -File renderizar.ps1 [nome-sem-extensao ...]
param([string[]]$Nomes)
$pasta = $PSScriptRoot
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$perfil = Join-Path $env:TEMP "edge-maquetes"
if (-not $Nomes) { $Nomes = (Get-ChildItem $pasta -Filter *.html).BaseName }
foreach ($nome in $Nomes) {
  $url = "file:///" + ($pasta -replace '\\', '/') + "/$nome.html"
  $argumentos = @("--headless=new", "--disable-gpu", "--hide-scrollbars",
    "--force-device-scale-factor=1", "--window-size=1440,900", "--virtual-time-budget=3000",
    "--user-data-dir=$perfil", "--screenshot=$pasta\$nome.png", $url)
  Start-Process -FilePath $edge -ArgumentList $argumentos -Wait -NoNewWindow
}
