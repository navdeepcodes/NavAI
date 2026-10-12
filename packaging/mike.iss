; Mike's Windows installer: one Mike-Setup-<version>.exe, a normal wizard.
;
; Built on GitHub's Windows runner by .github/workflows/windows-build.yml,
; after build_windows.py has produced dist\Mike\:
;
;     iscc /DAppVersion=1.1.2 packaging\mike.iss
;
; Decisions that matter, each learned from how Mike already installs and
; updates himself (installer\core.py, installer\updates.py):
;
;   * Per-user, no administrator, into %LOCALAPPDATA%\Programs\Mike -- the same
;     folder the in-app installer uses, so the in-app updater (which unpacks
;     the release zip over that folder) keeps working on a copy installed this
;     way, and this can be run over an existing install.
;   * The AppId below shipped in 1.1.1 and must NEVER change: it is how Windows
;     knows "this is the same Mike", so an upgrade replaces the Apps & features
;     entry instead of adding a second one.
;   * New installs keep the uninstaller OUTSIDE the program folder. In-app
;     updates replace the whole folder by renaming it; an uninstaller kept
;     inside would vanish on the first update and leave a dead entry. (Copies
;     installed by 1.1.1 have it inside; installer\core.copy_tree now carries
;     unins*.* across an update so those survive too.)
;   * Mike's data (chats, memory, preferences) is in %LOCALAPPDATA%\Mike, not
;     here, so removing or replacing the program folder never touches it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change this GUID -- it shipped in 1.1.1.
AppId={{6F3B2C1A-8D54-4E0B-9A77-4D2C5B8E1F30}
AppName=Mike
AppVersion={#AppVersion}
AppVerName=Mike {#AppVersion}
AppPublisher=Huddle Labs
AppPublisherURL=https://huddlecode.com
AppSupportURL=https://huddlecode.com
AppUpdatesURL=https://huddlecode.com
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Mike
UninstallFilesDir={localappdata}\Programs\Mike Uninstall
DefaultGroupName=Mike
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Mike.exe
UninstallDisplayName=Mike
OutputDir=..\dist
OutputBaseFilename=Mike-Setup-{#AppVersion}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
; Mike lives in the tray, so it is usually running when a newer Setup runs.
CloseApplications=yes
RestartApplications=no
; An unsigned installer is a disclosed early-access tradeoff (see
; packaging\build_windows.py); signing is added by the release workflow, not here.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; Replace the program folder cleanly so an older version's files can't linger
; beside the new ones. Safe: nothing the user owns lives in here. (The
; uninstaller of a 1.1.1 install lives here too; Setup recreates it.)
Type: filesandordirs; Name: "{app}\*"

[Files]
Source: "..\dist\Mike\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Mike"; Filename: "{app}\Mike.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Mike"; Filename: "{app}\Mike.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Mike.exe"; Description: "Start Mike"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Updates swap the folder from outside Inno's knowledge, so remove it by name
; rather than by the list of files Inno remembers installing.
Type: filesandordirs; Name: "{app}"

[Code]
function OllamaPresent: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'))
         or FileExists(ExpandConstant('{commonpf}\Ollama\ollama.exe'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if (CurStep = ssPostInstall) and (not WizardSilent) and (not OllamaPresent) then
  begin
    if MsgBox('Mike needs Ollama (a free app) to think on your PC, and it was not found.'#13#10#13#10 +
              'Open the Ollama download page now? Install it, then start Mike.',
              mbInformation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://ollama.com/download', '', '', SW_SHOWNORMAL, ewNoWait, Code);
  end;
end;
