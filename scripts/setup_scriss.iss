#define MyAppVersion "4.0.2"
#ifndef BuildRoot
  #define BuildRoot "."
#endif

[Setup]
AppId=Beytarchiver Pro Enterprise
AppName=Beytarchiver Pro Enterprise
AppVersion={#MyAppVersion}
VersionInfoVersion=4.0.2.0
AppPublisher=Beytarchiver Inc.
DefaultDirName={autopf}\Beytarchiver
DefaultGroupName=Beytarchiver
OutputDir={#BuildRoot}\Output
OutputBaseFilename=Beytarchiver_v{#MyAppVersion}_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupIconFile={#BuildRoot}\logo.ico
UninstallDisplayIcon={app}\Beytarchiver.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#BuildRoot}\dist\Beytarchiver\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Beytarchiver Pro"; Filename: "{app}\Beytarchiver.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\Beytarchiver Pro"; Filename: "{app}\Beytarchiver.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Beytarchiver.exe"; Description: "Beytarchiver Başlat"; Flags: nowait postinstall skipifsilent
