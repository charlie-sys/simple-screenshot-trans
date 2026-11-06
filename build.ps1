param([string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FloatTranslate --distpath $OutputDirectory --exclude-module numpy --exclude-module matplotlib --exclude-module scipy --exclude-module IPython --exclude-module pytest main.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Write-Host "Ready: $OutputDirectory\FloatTranslate.exe"
