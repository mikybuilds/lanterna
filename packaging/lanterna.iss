; Inno Setup script: turns dist\Lanterna (PyInstaller folder build) into Lanterna-Setup-<version>.exe.
; Build:  iscc /DAppVersion=0.1.0 /DHomepage=<project page> packaging\lanterna.iss
; Installs per user (no admin rights needed), adds a Start menu shortcut and an uninstaller.
; Chats, memory and keys are NOT removed on uninstall: they live in the user's profile and the system vault.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Homepage
  #define Homepage ""
#endif

[Setup]
AppId={{6E2B7A51-3C1D-4F7A-9B57-4C8A1E0D2F61}
AppName=Lanterna
AppVersion={#AppVersion}
AppVerName=Lanterna {#AppVersion}
AppPublisher=mikybuilds
AppPublisherURL={#Homepage}
AppSupportURL={#Homepage}
AppUpdatesURL={#Homepage}
DefaultDirName={localappdata}\Programs\Lanterna
DefaultGroupName=Lanterna
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Lanterna-Setup-{#AppVersion}
SetupIconFile=lanterna.ico
UninstallDisplayIcon={app}\Lanterna.exe
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Lanterna\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Lanterna"; Filename: "{app}\Lanterna.exe"
Name: "{group}\{cm:UninstallProgram,Lanterna}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Lanterna"; Filename: "{app}\Lanterna.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lanterna.exe"; Description: "{cm:LaunchProgram,Lanterna}"; Flags: nowait postinstall skipifsilent
