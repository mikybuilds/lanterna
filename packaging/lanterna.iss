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
; Updating from inside Lanterna: the running app is closed so its files can be replaced.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Program files of the old version (libraries change between versions); user data lives elsewhere.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Lanterna\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
; "Start with Windows" is written by Lanterna itself (only when the user turns it on); the uninstaller removes it.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Lanterna"; Flags: dontcreatekey uninsdeletevalue

[Icons]
Name: "{group}\Lanterna"; Filename: "{app}\Lanterna.exe"
Name: "{group}\{cm:UninstallProgram,Lanterna}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Lanterna"; Filename: "{app}\Lanterna.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lanterna.exe"; Description: "{cm:LaunchProgram,Lanterna}"; Flags: nowait postinstall skipifsilent
; Lanterna's own update runs the installer silently with RELAUNCH=1: open the new version when it is done.
Filename: "{app}\Lanterna.exe"; Flags: nowait; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;
