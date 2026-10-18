$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $RepoRoot; Set-Location $RepoRoot

if ($env:OS -ne 'Windows_NT') {
    throw 'Run this build on Windows.'
}

$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
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
if (Test-Path $NuitkaDir) { Remove-Item -Recurse -Force $NuitkaDir }
New-Item -ItemType Directory -Force -Path $NuitkaDir | Out-Null

$AppDir = if (Test-Path (Join-Path $RepoRoot "beytarchiver.py")) { $RepoRoot } elseif (Test-Path (Join-Path $RepoRoot "app\beytarchiver.py")) { Join-Path $RepoRoot "app" } else { (Resolve-Path (Join-Path $RepoRoot "venv\Ak*")).Path }
Push-Location $AppDir
try {
    & $Python -m nuitka --mode=module beytarchiver.py `
        --include-package=lan_transfer `
        --output-dir="$NuitkaDir" `
        --remove-output --no-pyi-file --assume-yes-for-downloads
    if ($LASTEXITCODE -ne 0) { throw 'Nuitka native C compilation failed.' }
} finally {
    Pop-Location
}

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

if __name__ == "__main__":
    app = beytarchiver.BeytarchiverApp()
    app.mainloop()
'@ | Set-Content -Path $Launcher -Encoding UTF8

& $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name Beytarchiver --icon logo.ico --add-data "logo.ico;." --add-data "logo.png;." `
    --distpath dist --workpath build `
    --paths "$NuitkaDir" --hidden-import beytarchiver `
    --collect-all customtkinter --collect-all tkinterdnd2 --collect-all qrcode `
    --exclude-module torch --exclude-module scipy --exclude-module sklearn `
    --exclude-module matplotlib --exclude-module pandas --exclude-module sympy `
    --exclude-module notebook --exclude-module IPython --exclude-module pytest `
    "$Launcher"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

Write-Host 'Native-protected EXE ready: dist\Beytarchiver\Beytarchiver.exe'
Write-Host 'Test the EXE, then compile setup_scriss.iss with Inno Setup.'
