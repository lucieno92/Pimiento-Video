; ============================================================
;  Pimiento Video - Script d'installation (Inno Setup)
;  Compile ce fichier avec Inno Setup pour obtenir un Setup.exe
;  qui installe l'application proprement dans Program Files,
;  cree un raccourci bureau et un desinstalleur.
; ============================================================

#define MyAppName "Pimiento Video"
#define MyAppVersion "1.1"
#define MyAppPublisher "Pimiento Video"
#define MyAppURL "https://pimientovideo.com"
#define MyAppExeName "Pimiento Video.exe"

[Setup]
AppId={{8F3A1C42-7B5E-4D96-A1F8-3E7C9D2B4A61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Dossier d'installation : C:\Program Files\Pimiento Video
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Icone affichee dans "Ajouter/Supprimer des programmes"
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; Le fichier Setup.exe genere
OutputDir=installer
OutputBaseFilename=PimientoVideo-Setup-{#MyAppVersion}
SetupIconFile=assets\logo.ico

; Compression equilibree : bonne reduction sans saturer la memoire.
; (ultra64 provoque une erreur "Out of memory" sur les gros dossiers)
Compression=lzma2/normal
SolidCompression=yes
LZMADictionarySize=32768

WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Tout le contenu du dossier genere par PyInstaller
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menu Demarrer
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; Bureau (si l'utilisateur coche la case)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
; Proposer de lancer l'application a la fin de l'installation
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Nettoyer les fichiers generes par l'app lors de la desinstallation
Type: filesandordirs; Name: "{app}"
