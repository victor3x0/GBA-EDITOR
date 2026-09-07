; ---------------------------------------------------------------------
; GBA Editor - installateur Windows (NSIS), installation par utilisateur.
;
; Compile avec :
;   makensis /DVERSION=0.3.2 /DSRCDIR=<dossier GBAEditor> /DOUTFILE=<setup.exe> installer.nsi
;
; SRCDIR est le dossier produit par packaging/nuitka_build.py.
;
; Installation dans %LOCALAPPDATA%\Programs : pas d'elevation UAC, donc
; pas de prompt admin a l'installation. Les entrees de desinstallation
; vont dans HKCU en consequence.
;
; NOTE ENCODAGE : ce fichier est volontairement en ASCII pur (pas
; d'accents, meme dans les commentaires). En mode Unicode, makensis lit
; les sources sans BOM avec la page de code ANSI de la machine de build -
; un accent ici donnerait des libelles corrompus dans l'installateur, et
; seulement sur certaines machines. Les libelles accentues standard
; (Suivant, Annuler...) viennent du fichier de langue French.nlf, pas
; d'ici.
; ---------------------------------------------------------------------

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"

!define APP_NAME    "GBA Editor"
!define APP_EXE     "GBA Editor.exe"
!define APP_KEY     "GBAEditor"
; Doit rester aligne avec --company-name dans packaging/nuitka_build.py :
; c'est ce qui s'affiche dans "Applications et fonctionnalites" d'un cote,
; et dans les proprietes de l'exe de l'autre.
!define PUBLISHER   "Yasor Rovic"
!define UNINST_KEY  "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_KEY}"

; Valeurs par defaut si le script est lance a la main sans /D
!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef SRCDIR
  !define SRCDIR "..\..\build-out\GBAEditor"
!endif
!ifndef OUTFILE
  !define OUTFILE "GBAEditor-${VERSION}-windows-setup.exe"
!endif
; VIProductVersion n'accepte QUE du numerique 4 champs. VERSION peut etre
; un tag quelconque ("0.3.2-rc1"), d'ou ce define separe, calcule par
; packaging/nuitka_build.py:numeric_version().
!ifndef VIVERSION
  !define VIVERSION "0.0.0.0"
!endif

Name "${APP_NAME} ${VERSION}"
OutFile "${OUTFILE}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\${APP_KEY}"
InstallDirRegKey HKCU "Software\${APP_KEY}" "InstallDir"
SetCompressor /SOLID lzma

VIProductVersion "${VIVERSION}"
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} installer"
VIAddVersionKey "FileVersion"     "${VERSION}"
VIAddVersionKey "ProductVersion"  "${VERSION}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "LegalCopyright"  "${PUBLISHER}"

!define MUI_ICON   "..\icon.ico"
!define MUI_UNICON "..\icon.ico"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; La premiere langue declaree est celle par defaut.
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "English"


Section "GBA Editor" SecApp
  SectionIn RO

  SetOutPath "$INSTDIR"
  File /r "${SRCDIR}\*"

  WriteRegStr HKCU "Software\${APP_KEY}" "InstallDir" "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Entree "Applications et fonctionnalites" (par utilisateur -> HKCU)
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\${APP_EXE}"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1

  ; Taille affichee dans la liste des programmes installes
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"

  ; --- Association du fichier de projet (.gba-project) ---
  ; Par utilisateur : HKCU\Software\Classes est la vue HKCR propre a
  ; l'utilisateur, coherente avec une installation sans elevation. Un ProgID
  ; dedie porte l'icone et la commande d'ouverture ; l'exe ouvre le fichier
  ; passe en "%1" (main.py accepte ce chemin en argument positionnel).
  WriteRegStr HKCU "Software\Classes\.gba-project" "" "${APP_KEY}.Project"
  WriteRegStr HKCU "Software\Classes\${APP_KEY}.Project" "" "GBA Editor Project"
  WriteRegStr HKCU "Software\Classes\${APP_KEY}.Project\DefaultIcon" "" "$INSTDIR\${APP_EXE},0"
  WriteRegStr HKCU "Software\Classes\${APP_KEY}.Project\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'

  ; Prevenir le shell que les associations ont change (icone et appli a jour
  ; sans deconnexion). SHCNE_ASSOCCHANGED=0x08000000, SHCNF_IDLIST=0.
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"   "$INSTDIR\Uninstall.exe"
SectionEnd


Section /o "Raccourci sur le Bureau" SecDesktop
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd


LangString DESC_SecApp     ${LANG_FRENCH}  "L'editeur et ses fichiers."
LangString DESC_SecApp     ${LANG_ENGLISH} "The editor and its files."
LangString DESC_SecDesktop ${LANG_FRENCH}  "Ajouter une icone sur le Bureau."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Add a shortcut on the Desktop."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp}     $(DESC_SecApp)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END


Section "Uninstall"
  ; Garde-fou : $INSTDIR vient du registre ou d'une saisie utilisateur, et
  ; on s'apprete a faire un RMDir /r dessus. On ne touche a rien si le
  ; dossier ne contient pas l'executable attendu.
  IfFileExists "$INSTDIR\${APP_EXE}" proceed 0
    MessageBox MB_ICONSTOP "Dossier d'installation inattendu : $INSTDIR$\n$\nDesinstallation annulee."
    Abort
  proceed:

  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  RMDir /r "$INSTDIR"

  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\${APP_KEY}"

  ; Defaire l'association .gba-project posee a l'installation.
  DeleteRegKey HKCU "Software\Classes\${APP_KEY}.Project"
  DeleteRegKey HKCU "Software\Classes\.gba-project"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, i 0, i 0)'

  ; Volontairement conserves : les projets de l'utilisateur
  ; (%USERPROFILE%\GBAProjects) et sa configuration toolchain
  ; (%APPDATA%\GBAEditor). Une desinstallation ne doit pas detruire le
  ; travail de l'utilisateur ni ses chemins devkitPro/mGBA.
SectionEnd
