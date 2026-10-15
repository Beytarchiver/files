#define MyAppVersion "3.7"

[Setup]
AppName=Beytarchiver Pro Enterprise
AppVersion={#MyAppVersion}
VersionInfoVersion=3.7.0.0
AppPublisher=Beytarchiver Inc.
DefaultDirName={autopf}\Beytarchiver
DefaultGroupName=Beytarchiver
OutputDir=Output
OutputBaseFilename=Beytarchiver_v{#MyAppVersion}_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Beytarchiver\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Beytarchiver Pro"; Filename: "{app}\Beytarchiver.exe"
Name: "{commondesktop}\Beytarchiver Pro"; Filename: "{app}\Beytarchiver.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Beytarchiver.exe"; Description: "Beytarchiver Başlat"; Flags: nowait postinstall skipifsilent
