; ============================================================
; Inno Setup Script for Tailscale Magic Hub
; ============================================================
; Builds a professional Windows installer (.exe)
;
; Prerequisites:
;   1. Build the app first:  pyinstaller TailscaleMagic.spec
;   2. Install Inno Setup:   https://jrsoftware.org/isinfo.php
;   3. Compile this script via Inno Setup Compiler
;
; Output: dist/TailscaleMagicSetup.exe
; ============================================================

#define MyAppName "Magic Hub"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Magic Hub"
#define MyAppURL "https://github.com/"
#define MyAppExeName "TailscaleMagic.exe"

[Setup]
AppId={{B8F4A3E2-7C1D-4F2A-9D6E-3A5B7C8D9E0F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=TailscaleMagicSetup
SetupIconFile=static\favicon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=
; Modern look and feel
WizardSizePercent=110
WizardResizable=no

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Magic Hub beim Windows-Start automatisch starten"; GroupDescription: "Automatischer Start:"; Flags: unchecked

[Files]
Source: "dist\TailscaleMagic.exe"; DestDir: "{app}"; Flags: ignoreversion
; Include any additional data files in the dist folder
Source: "dist\analytics.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "dist\projects.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MagicHub"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM TailscaleMagic.exe"; Flags: runhidden

[Code]
var
  TailscaleDomainPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  TailscaleDomainPage := CreateInputQueryPage(wpSelectTasks,
    'Tailscale Domain', 'Persönliche Tailscale Adresse für rechtliche Verlinkungen',
    'Bitte gib deine persönliche Tailscale-Adresse ein (z.B. name.tail123.ts.net), damit Impressum und Datenschutz im Portal auf DEINE Webseite verlinken. Wenn du das Feld leer lässt, wird die Adresse deines PCs automatisch erkannt.');
  TailscaleDomainPage.Add('Tailscale Adresse:', False);
end;

function IsTailscaleInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('tailscale', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then
  begin
    if not IsTailscaleInstalled() then
    begin
      MsgBox('Hinweis: Tailscale scheint nicht installiert zu sein.' + #13#10 + #13#10 +
             'Magic Hub benötigt Tailscale, um Projekte im Internet zu veröffentlichen.', 
             mbInformation, MB_OK);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: String;
  JsonStr: String;
  DomainStr: String;
begin
  if CurStep = ssPostInstall then
  begin
    DomainStr := Trim(TailscaleDomainPage.Values[0]);
    if DomainStr <> '' then
    begin
      ConfigFile := ExpandConstant('{app}\settings.json');
      JsonStr := '{ "legal_domain": "' + DomainStr + '" }';
      SaveStringToFile(ConfigFile, JsonStr, False);
    end;
  end;
end;
