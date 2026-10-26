#ifndef AppVersion
  #error AppVersion must be provided by build runner
#endif
#ifndef SourceDir
  #error SourceDir must be provided by build runner
#endif
[Setup]
AppName=ResearchWeave
AppVersion={#AppVersion}
AppId={{A8B4CE9D-02E5-4D3B-A88D-428B711F8601}
DefaultDirName={localappdata}\Programs\ResearchWeave
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=ResearchWeave-v{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=ResearchWeave
SetupIconFile=..\..\assets\branding\researchweave.ico
[Files]
Source: "{#SourceDir}\researchweave-desktop.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\pdfium.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\PDFIUM_RUNTIME_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\assets\branding\researchweave.ico"; DestDir: "{app}"; DestName: "ResearchWeave.ico"; Flags: ignoreversion
[Icons]
Name: "{autoprograms}\ResearchWeave"; Filename: "{app}\researchweave-desktop.exe"; IconFilename: "{app}\ResearchWeave.ico"
[Run]
Filename: "{app}\researchweave-desktop.exe"; Description: "Launch ResearchWeave"; Flags: postinstall nowait skipifsilent
