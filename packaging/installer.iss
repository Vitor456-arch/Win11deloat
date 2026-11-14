#ifndef AppVersion
  #error AppVersion must be provided by the build
#endif
#ifndef AppSource
  #error AppSource must point to the PyInstaller application directory
#endif
#ifndef OutputPath
  #define OutputPath "..\release"
#endif

[Setup]
AppId={{A41C782B-1699-43C9-9F4F-0A0906F57762}
AppName=Clear Windows
AppVersion={#AppVersion}
AppPublisher=Clear Windows contributors
AppPublisherURL=https://github.com/Vitor456-arch/Win11deloat
AppSupportURL=https://github.com/Vitor456-arch/Win11deloat/issues
AppUpdatesURL=https://github.com/Vitor456-arch/Win11deloat/releases
DefaultDirName={localappdata}\Programs\ClearWindows
DefaultGroupName=Clear Windows
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir={#OutputPath}
OutputBaseFilename=ClearWindows-{#AppVersion}-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ClearWindows.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile=..\LICENSE
InfoBeforeFile=INSTALL-NOTES.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Clear Windows"; Filename: "{app}\ClearWindows.exe"
Name: "{group}\Uninstall Clear Windows"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Clear Windows"; Filename: "{app}\ClearWindows.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClearWindows.exe"; Description: "{cm:LaunchProgram,Clear Windows}"; Flags: nowait postinstall skipifsilent
