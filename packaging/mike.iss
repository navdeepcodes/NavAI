; Inno Setup script for Mike on Windows -> dist\Mike-Setup-<version>.exe
;
; A single double-click installer, instead of "unzip, find the right file, run
; it and let it install itself". Built on the CI Windows machine after
; build_windows.py has produced dist\Mike\:
;
;     ISCC.exe /DMyAppVersion=1.1.1 packaging\mike.iss
;
; Decisions that matter, each one learned from how Mike already installs and
; updates himself (installer\core.py, installer\updates.py):
;
;   * Per-user, no administrator, into %LOCALAPPDATA%\Programs\Mike -- the exact
;     folder the in-app installer uses, so someone on 1.1.0 can run this over
;     the top and nothing moves.
;   * The uninstaller lives OUTSIDE that folder. In-app updates replace the
;     whole install folder by renaming it; an uninstaller kept inside would
;     vanish on the first update and leave a dead entry in Apps & features.
;   * Mike's data (chats, memory, preferences) is in %LOCALAPPDATA%\Mike, not
;     here, so removing or replacing the program folder never touches it.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "Mike"
#define MyAppExe "Mike.exe"
#define MyAppPublisher "Huddle Labs"
#define MyAppURL "https://huddlecode.com"

[Setup]
; Never change this GUID: it is how Windows (and a later installer) recognises
; "this is the same Mike" for upgrades and uninstall.
AppId={{6C1B0E5E-3F7A-4D58-9B2A-4D1E6A0F7C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}

PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Mike
UninstallFilesDir={localappdata}\Programs\Mike Uninstall
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
UsePreviousAppDir=no

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

OutputDir=..\dist
OutputBaseFilename=Mike-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; An unsigned installer is a disclosed early-access tradeoff (see
; packaging\build_windows.py); signing is added by the release workflow, not here.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put a Mike shortcut on the desktop"; GroupDescription: "Shortcuts:"

[InstallDelete]
; Replace the program folder cleanly so an older version's files can't linger
; beside the new ones. Safe: nothing the user owns lives in here.
Type: filesandordirs; Name: "{app}\*"

[Files]
Source: "..\dist\Mike\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Open Mike now"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Updates swap the folder from outside Inno's knowledge, so remove it by name
; rather than by the list of files Inno remembers installing.
Type: filesandordirs; Name: "{app}"
