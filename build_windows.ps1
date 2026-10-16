$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if ($env:OS -ne 'Windows_NT') {
    throw 'Run this build on Windows.'
}

$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}

& $Python -m pip install -r beytarchiver-requirements.txt 'pyinstaller==6.22.3'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

& $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name Beytarchiver --icon logo.ico --add-data "logo.ico;." --add-data "logo.png;." --distpath dist --workpath build `
    --collect-all customtkinter --collect-all tkinterdnd2 --collect-all qrcode `
    'venv\Akıllı_Dosya_Yöneticisi\beytarchiver.py'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

Write-Host 'EXE ready: dist\Beytarchiver\Beytarchiver.exe'
Write-Host 'Test the EXE, then compile setup_scriss.iss with Inno Setup 6.'
