; Mike's Windows installer: one Mike-Setup-<version>.exe, a normal wizard.
;
; Built on GitHub's Windows runner by .github/workflows/windows-build.yml:
;   iscc /DAppVersion=1.1.1 packaging\mike.iss
;
; Installs per-user into %LOCALAPPDATA%\Programs\Mike -- the same folder
; installer/core.py uses -- so no administrator prompt, and the in-app
; updater (which unpacks the release zip over that folder) keeps working on
; a copy installed this way.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F3B2C1A-8D54-4E0B-9A77-4D2C5B8E1F30}
AppName=Mike
AppVersion={#AppVersion}
AppPublisher=Huddle Labs
AppPublisherURL=https://huddlecode.com
DefaultDirName={localappdata}\Programs\Mike
DefaultGroupName=Mike
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Mike.exe
OutputDir=..\dist
OutputBaseFilename=Mike-Setup-{#AppVersion}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
; Mike lives in the tray, so it is usually running when a newer Setup runs.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Mike\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Mike"; Filename: "{app}\Mike.exe"
Name: "{userdesktop}\Mike"; Filename: "{app}\Mike.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Mike.exe"; Description: "Start Mike"; Flags: nowait postinstall skipifsilent

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
