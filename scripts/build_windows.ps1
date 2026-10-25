param([switch]$Check)

$ErrorActionPreference = 'Stop'
$RepoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))

if ($env:OS -ne 'Windows_NT') {
    throw 'Run this build on Windows.'
}

$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
foreach ($Required in @('beytarchiver.py', 'beyt_core.py', 'lan_transfer\__init__.py',
                        'lan_transfer\panel.py', 'scripts\beytarchiver-requirements.txt',
                        'logo.ico', 'logo.png')) {
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot $Required) -PathType Leaf)) {
        throw "Required project file missing: $Required"
    }
}
if ($Check) {
    Write-Host "Project paths OK: $RepoRoot"
    Write-Host "Python present: $(Test-Path -LiteralPath $Python -PathType Leaf)"
    return
}

Push-Location -LiteralPath $RepoRoot
try {
if (-not (Test-Path $Python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}

& $Python -m pip install -r scripts\beytarchiver-requirements.txt 'pyinstaller==6.22.3' 'nuitka==4.3.1'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

$NuitkaDir = Join-Path $RepoRoot 'build\nuitka_mod'
$ResolvedNuitkaDir = [System.IO.Path]::GetFullPath($NuitkaDir)
if (-not $ResolvedNuitkaDir.StartsWith($RepoRoot + [System.IO.Path]::DirectorySeparatorChar,
                                     [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build output must stay inside the repository.'
}
foreach ($BuildPath in @((Join-Path $RepoRoot 'build'), $ResolvedNuitkaDir)) {
    if ((Test-Path -LiteralPath $BuildPath) -and
        ((Get-Item -LiteralPath $BuildPath -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing to clean a linked build directory: $BuildPath"
    }
}
if (Test-Path -LiteralPath $ResolvedNuitkaDir) {
    Remove-Item -LiteralPath $ResolvedNuitkaDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $NuitkaDir | Out-Null

    & $Python -m nuitka --mode=module beytarchiver.py `
        --include-package=lan_transfer `
        --include-module=beyt_core `
        --output-dir="$NuitkaDir" `
        --remove-output --no-pyi-file --assume-yes-for-downloads
    if ($LASTEXITCODE -ne 0) { throw 'Nuitka native C compilation failed.' }

$Launcher = Join-Path $NuitkaDir 'run_beytarchiver.py'
@'
import base64, ctypes, gzip, hashlib, json, ntpath, os, shutil, socket, ssl, stat, subprocess, sys, tarfile, tempfile, threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, ttk, messagebox, simpledialog

import customtkinter
import psutil
import py7zr
import pyzipper
import qrcode
from cryptography import x509
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from PIL import Image
from tkinterdnd2 import DND_FILES, TkinterDnD

import beytarchiver
import beyt_core

if __name__ == "__main__":
    app = beytarchiver.BeytarchiverApp()
    app.mainloop()
'@ | Set-Content -Path $Launcher -Encoding UTF8

& $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name Beytarchiver --icon logo.ico --add-data "logo.ico;." --add-data "logo.png;." `
    --distpath dist --workpath build `
    --paths "$NuitkaDir" --paths "$RepoRoot" --hidden-import beytarchiver `
    --hidden-import beyt_core --collect-submodules lan_transfer `
    --collect-all customtkinter --collect-all tkinterdnd2 --collect-all qrcode `
    --exclude-module torch --exclude-module scipy --exclude-module sklearn `
    --exclude-module matplotlib --exclude-module pandas --exclude-module sympy `
    --exclude-module notebook --exclude-module IPython --exclude-module pytest `
    "$Launcher"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

Write-Host 'Native-protected EXE ready: dist\Beytarchiver\Beytarchiver.exe'
Write-Host 'Test the EXE, then compile scripts\setup_scriss.iss with Inno Setup.'
} finally {
    Pop-Location
}
