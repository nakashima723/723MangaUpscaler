# 12. コード署名ポリシー

## 1. 結論

公開配布の `723MangaUpscaler.exe` には、Windowsが信頼できる証明書チェーンを持つAuthenticode署名とRFC 3161タイムスタンプを付ける。自己署名証明書はローカル試験に限り、公開配布物へは使用しない。

現時点で費用なしに信頼済みAuthenticode署名を得られる現実的な候補は、条件を満たすオープンソースプロジェクト向けのSignPath Foundationである。本プロジェクトを公開リポジトリへ移し、SignPath Foundationの審査とプロジェクト登録が完了した後、GitHub Actionsの成果物をSignPathへ送って署名する。

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

## 2. 署名対象

- 対象は最終の `dist/723MangaUpscaler.exe` だけとする。
- PyInstallerビルド、ライセンス収集、全自動テスト、静的検査、画像一致確認を終えてから署名する。
- 署名後は圧縮、リネーム以外の書換え、リソース編集を行わない。
- 公開するSHA-256は署名とタイムスタンプの後に計算する。

## 3. 暗号要件

- Authenticode file digest: SHA-256
- Timestamp: RFC 3161、timestamp digest SHA-256
- Windows検証ポリシー: Authenticode `/pa`
- 全署名とタイムスタンプを `/all /tw` で検証する
- 証明書はCode Signing EKU `1.3.6.1.5.5.7.3.3` を持つこと

## 4. 秘密鍵

- PFX、P12、PEM、秘密鍵、パスワードをリポジトリやCI環境変数へ保存しない。
- ローカル証明書を使う場合はWindows証明書ストアの非exportable key、可能ならTPM/HSMを使用し、公開情報であるthumbprintだけをビルドへ渡す。
- SignPath Foundation利用時はSignPath管理のHSMを使う。GitHub ActionsのSubmitter専用API tokenは保護environmentのsecretに保存し、SignPath GitHub AppとGitHub connectorによるrepository・workflow・artifactの出所検証を使う。

## 5. 承認

- 署名要求を提出するGitHub ActionsのCI userと、SignPath上で手動承認するinteractive maintainer accountを分離する。別人であることは必須としない。
- 署名要求はタグ付きリリースに限定し、SignPath上でも手動承認する。
- 未レビューのfork、任意バイナリ、ローカル差分をSignPathへ送らない。
- SignPathとソースホスティングの両方でMFAを有効にする。

本プロジェクトはsingle-maintainer projectとして次の役割を公開する。

- Authors: [nakashima723](https://github.com/nakashima723)
- Reviewers: [nakashima723](https://github.com/nakashima723)。外部contributorの変更をreviewする。
- Approvers: [nakashima723](https://github.com/nakashima723)。CIが提出した署名要求を手動承認する。

## 6. 検証

署名後に以下をすべて満たすこと。

1. `tools/verify_gui_signature.ps1` が終了コード0になる。
2. signer thumbprint、Code Signing EKU、RFC 3161 timestampが期待値と一致する。
3. 一時コピーの1 byte改変を署名検証が拒否する。
4. 空の一時フォルダへEXEだけを置き、`--version`、`--check-config`、`--check-ui` が成功する。
5. `--check-upscale` のPNGが署名前と画素完全一致する。
6. 署名後の最終SHA-256を開発ログとリリースページへ記録する。

## 7. プライバシー

723 Manga Upscalerはローカル画像処理アプリケーションであり、テレメトリ、利用統計、広告、アカウント機能を持たず、画像や設定を開発者へ送信しない。利用者が任意に設定した外部アップスケーラーはローカルCLIとして呼び出し、その外部ツールの通信・プライバシー条件は各提供者に従う。

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

Microsoft Visual C++ / OpenMP runtimeは、Visual Studio公式x64 Redistributable由来を署名と発行元まで検証し、System Libraryとして同梱する。Potrace、Real-CUGAN、waifu2x、Real-ESRGANは任意の別install CLIであり、署名対象へ同梱しない。

## 8. 無料署名サービス導入の残作業

1. [公開リポジトリ](https://github.com/nakashima723/723MangaUpscaler)で機能と依存関係を安定させる。
2. グレースケール対応など、次回公開版の機能範囲と配布metadataを確定する。
3. GitHub-hosted buildから同じone-file形式のunsigned releaseを公開する。
4. SignPath Foundationの条件、役割、MFA、privacy policyを再確認して申請する。
5. SignPath GitHub Appを接続し、Project、Artifact Configuration、Signing Policyを作成する。
6. `SIGNPATH_SUBMISSION_ENABLED=true`を審査完了後に設定し、CIから署名要求する。
7. 返却された署名済みEXEを本書第6節の手順で検証して公開する。

自己署名証明書の公開配布、利用者へのルート証明書install要求、PFXのリポジトリ保存は行わない。
