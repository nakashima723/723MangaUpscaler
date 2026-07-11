# 14. 公開・配布ライセンス監査

## 結論

アプリ本体のApache-2.0と、現在同梱する主要Pythonライブラリのライセンスは
両立する。署名対象へproprietaryアプリ、AI model、Potrace本体は同梱しない。
Microsoft Visual C++ / OpenMP runtimeだけは、SignPathが許容するSystem Library
としてMicrosoftの再配布条件に従って同梱する。

グレースケールの相対的な線画・階調分離、PNG分離出力、グレースケールPSD出力を
追加した後に再監査した。新規モジュールは標準ライブラリと既存のNumPy、SciPy、
Pillowだけを使用しており、`pyproject.toml`と`requirements-release.txt`に依存追加はない。
PSDはプロジェクト内のwriterで生成し、Adobe SDK、`psd-tools`、追加codecを使用しない。

## 公開対象から除外したもの

`images/input/`、その派生比較画像`docs/assets/`、`reviews/`には、現時点で公開
再配布できることを示すprovenance記録がない。このため`.gitignore`で除外した。
公開用sampleとtest fixtureはプロジェクト内で生成した合成線画へ置換した。

## 配布物の依存関係

配布EXEにはCPython、Tcl/Tk、NumPy/OpenBLAS、SciPy、Pillow、PyYAML、
CustomTkinter、darkdetect、DIPlib、packaging、PyInstaller bootloader、Roboto、
Microsoft Visual C++ / OpenMP runtimeを含む。各ライセンスの概要は
`THIRD_PARTY_NOTICES.md`、原文はEXE内`licenses/third_party`へ収録する。

PyInstaller bootloaderはGPL-2.0-or-later with bootloader exceptionであり、生成EXEを
Apache-2.0で配布できる。RobotoはApache-2.0で、Google copyright noticeと原文を
別途収録する。不要な`win32pdh`をPyInstallerから除外し、pywin32 runtimeがEXEへ
入らないことをarchive検査で確認する。

更新後のone-file EXEについてもPyInstaller archiveを検査し、グレースケール分離と
PSD出力の新規モジュールが収録される一方、外部upscaler、Potrace、AI model、追加EXE、
pywin32 runtimeが収録されていないことを確認した。CPythonのOpenSSL/libffi通知、
Pillowの画像codec通知、NumPy/SciPyのOpenBLAS/LAPACK/GCC runtime exceptionを含め、
実際の収録物と`THIRD_PARTY_NOTICES.md`およびライセンス原文の対応漏れはない。

Microsoft runtimeは任意のPATHから取得せず、Visual Studio Installerが管理する
最新x64 Redistributableからだけ取得する。ビルド時にMicrosoft Authenticode署名、
signer organization、CompanyNameを検証し、ImageMagick等から収集した場合は失敗
させる。Visual Studioを利用するbuild担当者はMicrosoftの再配布条件を満たす必要が
ある。

## 外部ツール境界

PotraceはGPL版と商用版があるが、ソース、EXE、model、libraryを一切同梱しない。
利用者が明示設定した別installのCLIとinteropするだけであり、SignPath署名対象の
componentではない。Real-CUGAN、waifu2x、Real-ESRGANも同様に非同梱である。

## 再現性と供給網

`requirements-release.txt`はWindows x64 / CPython 3.11向けのruntime、test、build
dependencyをversionとwheel SHA-256で固定する。GitHub Actionsもrelease workflowで
使用するcommit SHAへ固定する。lock、workflow、build scriptの変更は通常コードより
強いreview対象とする。

## 残る確認

- 初回unsigned public releaseによるSignPathのReleased要件充足
- GitHubとSignPathにおけるMFA有効化の管理者確認
- SignPath Foundationによる最終的な適格性判断
- 審査後に発行される証明書、slug、organization IDの実値確認
