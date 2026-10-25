#ifndef AppVersion
  #error AppVersion must be supplied by packaging/windows/build.ps1
#endif
#ifndef SourceDir
  #error SourceDir must be supplied by packaging/windows/build.ps1
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by packaging/windows/build.ps1
#endif

#define AppName "ResearchWeave"
#define AppPublisher "ResearchWeave"
#define AppURL "https://github.com/aradmanamnaoon/researchweave"
#define AppExeName "ResearchWeave.exe"

[Setup]
AppId={{F7B76908-298C-4FC3-AC64-16A6B23024B8}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=ResearchWeave-v{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\assets\branding\researchweave.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
