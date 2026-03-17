; PyProxy Inno Setup Script
; No exe launcher - uses VBScript to silently start pythonw

#define AppName      "Avik Proxy"
#define AppVersion   "1.0.0"
#define AppURL       "https://github.com"

[Setup]
AppId={{B4C2D1E3-7F8A-4B9C-A1D2-E3F4G5H6I7J8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=AvikProxySetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
SetupIconFile=avik_proxy.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "Create a desktop shortcut";         GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startupentry"; Description: "Start PyProxy when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Main scripts
Source: "avik_proxy.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "avik_proxy.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "tray_app.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "main.py";                  DestDir: "{app}"; Flags: ignoreversion
Source: "config.yaml";              DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "requirements_runtime.txt"; DestDir: "{app}"; Flags: ignoreversion

; Proxy package
Source: "proxy\__init__.py";    DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\bandwidth.py";   DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\cache.py";       DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\config.py";      DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\filters.py";     DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\ftp_handler.py"; DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\handler.py";     DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\http_parser.py"; DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\logger.py";      DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\server.py";      DestDir: "{app}\proxy"; Flags: ignoreversion
Source: "proxy\stats.py";       DestDir: "{app}\proxy"; Flags: ignoreversion

[Icons]
; Start Menu shortcut → launches via wscript (no console, no antivirus trigger)
Name: "{group}\PyProxy"; \
    Filename: "{sys}\wscript.exe"; \
    Parameters: """{app}\start.vbs"""; \
    WorkingDir: "{app}"; \
    Comment: "Start PyProxy proxy server"

Name: "{group}\Uninstall PyProxy"; Filename: "{uninstallexe}"

; Desktop shortcut
Name: "{userdesktop}\PyProxy"; \
    Filename: "{sys}\wscript.exe"; \
    Parameters: """{app}\start.vbs"""; \
    WorkingDir: "{app}"; \
    Tasks: desktopicon

[Registry]
; Auto-start via wscript — no exe, no antivirus
Root: HKCU; \
    Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; \
    ValueName: "PyProxy"; \
    ValueData: """wscript.exe"" ""{app}\start.vbs"""; \
    Flags: uninsdeletevalue; \
    Tasks: startupentry

[Run]
; Install Python dependencies
Filename: "{cmd}"; \
    Parameters: "/c python -m pip install pystray Pillow PyYAML --quiet"; \
    WorkingDir: "{app}"; \
    StatusMsg: "Installing dependencies..."; \
    Flags: runhidden waituntilterminated

; Launch after install via wscript
Filename: "{sys}\wscript.exe"; \
    Parameters: """{app}\start.vbs"""; \
    WorkingDir: "{app}"; \
    Description: "Launch PyProxy now"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /f /im pythonw.exe /fi ""WINDOWTITLE eq PyProxy"""; Flags: runhidden

[Code]
// Write start.vbs into the install directory
procedure CurStepChanged(CurStep: TSetupStep);
var
  VBSFile: String;
  Lines: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    VBSFile := ExpandConstant('{app}\start.vbs');
    SetArrayLength(Lines, 4);
    Lines[0] := 'Set objShell = CreateObject("WScript.Shell")';
    Lines[1] := 'strDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)';
    Lines[2] := 'objShell.CurrentDirectory = strDir';
    Lines[3] := 'objShell.Run "pythonw """ & strDir & "\tray_app.py""", 0, False';
    SaveStringsToFile(VBSFile, Lines, False);
  end;
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if not Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if MsgBox(
      'Python was not found on this machine.' + #13#10 +
      'PyProxy requires Python 3.10 or newer.' + #13#10 + #13#10 +
      'Download from: https://python.org/downloads' + #13#10 + #13#10 +
      'Do you want to continue anyway?',
      mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;
