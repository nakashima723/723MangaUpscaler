# 13. 公開リポジトリ化・SignPath Foundation導入手順

## 現在の状態

公開用ファイル、ハッシュ固定依存、GitHub Actions、SignPath Artifact
Configuration、privacy/security/contribution文書までは準備済みである。
[GitHub公開リポジトリ](https://github.com/nakashima723/723MangaUpscaler)の`main`へ初回push済みである。
グレースケールの相対的な線画・階調分離、PNG分離出力、3レイヤーのグレースケールPSD出力を
次回公開版へ追加し、依存関係と実配布EXEのライセンス再監査も完了した。この更新による
新規Python依存、Adobe SDK、追加codec、AI model、第三者バイナリの導入はない。
同じone-file形式の未署名pre-release `v1.00-unsigned.1` は履歴として保持している。PSDレイヤー順と
分離プレビューを修正した最新版は履歴を置換せず `v1.00-unsigned.2` として追加公開済みであり、
その[Download URL](https://github.com/nakashima723/723MangaUpscaler/releases/tag/v1.00-unsigned.2)を使ってSignPath Foundationへ申請する段階である。
申請は進めるが、審査承認とGitHub App、Project、Artifact Configuration、Signing Policyの
設定が完了するまで実署名workflowは明示的に無効のままとする。

## 公開前ゲート

- `images/input/`、`docs/assets/`、`reviews/` は権利根拠が確定するまで公開しない。
- 公開例と回帰テストには `examples/synthetic_lineart.png` のみを使う。
- `.spec`、`build/`、`dist/`、`tmp/`、`.env*`、秘密鍵形式をcommitしない。
- Gitの初回履歴に秘密情報、個人パス、100MB超ファイルがないことを再確認する。
- GitHubの全担当者でMFAを有効にする。
- `main` のforce pushと削除を禁止し、CI成功を必須にする。外部contributorの変更はmaintainer reviewを必須にする。
- workflow、依存lock、`.signpath/`、署名スクリプトは重点review対象にする。

## 公開と初回リリース

1. 公開先を`nakashima723/723MangaUpscaler`とし、`main`へ初回pushする。
2. READMEへAuthors/Reviewers/Approversとして`nakashima723`を記載する。
3. GitHub Security Advisoriesのprivate vulnerability reportingを有効にする。
4. 機能追加とlicense再監査が完了した後、GitHub-hosted workflowからone-file形式のunsigned版を
   pre-releaseとして一度公開する。EXEが一般画像入力から線画PNG、線画・階調PNG、または
   `Line Art` / `Grayscale Tone` / `Background` のグレースケールPSDを生成できること、
   SHA-256、未署名である旨、[Code signing policy](../README.md#code-signing-policy)へのリンクを明記する。

SignPath Foundationは、署名対象と同じ形式で既に公開済みで、機能がdownload
pageに説明された保守中のOSSを要件としている。初回unsigned releaseはこの要件を
満たすために必要であり、信頼済み署名であるかのように表示してはならない。

## SignPath Foundation申請

- Project display name: `723 Manga Upscaler`
- Project slug: 審査時に作成し、GitHub variable `SIGNPATH_PROJECT_SLUG`へ設定する
- Artifact Configuration slug: `windows-onefile-v1`
- Signing Policy slug: `release-signing`
- Artifact Configuration: `.signpath/artifact-configuration.xml`
- Trusted Build System: predefined `GitHub.com`
- Certificate: SignPath Foundation
- Submitter: GitHub Actions専用CI user
- Approver: interactive account `nakashima723`、手動承認必須

- Authors: [nakashima723](https://github.com/nakashima723)
- Reviewers: [nakashima723](https://github.com/nakashima723)
- Approvers: [nakashima723](https://github.com/nakashima723)

SignPath GitHub Appは対象repositoryだけへアクセスを許可する。Organizationへ
predefined GitHub.com trusted build systemを追加し、Projectへlinkする。API tokenは
Submitter専用とし、GitHub environment `signpath-release` のsecret
`SIGNPATH_API_TOKEN`へ保存する。Organization IDは同environmentまたはrepository
variable `SIGNPATH_ORGANIZATION_ID`へ保存する。Project、Signing Policy、Artifact
Configurationのslugもそれぞれ`SIGNPATH_PROJECT_SLUG`、
`SIGNPATH_SIGNING_POLICY_SLUG`、`SIGNPATH_ARTIFACT_CONFIGURATION_SLUG`へ設定する。
審査承認とこれらの設定がすべて完了するまで`SIGNPATH_SUBMISSION_ENABLED`は未設定または`false`とする。
GitHubとSignPathの両方でMFAが有効であることも、実署名要求の前に管理者が確認する。

## 署名実行

1. review済みのprotected `main` commitへrelease tagを作る。
2. `Build and sign Windows release` workflowを`main`から手動実行する。
3. GitHub ActionsのCI userが要求を提出し、`nakashima723`がSignPath上で手動承認する。
4. 返却EXEの信頼チェーン、Code Signing EKU、timestamp、改ざん検知、単体起動、
   source版との画素一致をworkflowで検証する。
5. 署名後SHA-256をrelease pageへ記載し、検証済みEXEだけを公開する。

workflowの先行jobを含め、署名要求へ至る全工程はGitHub-hosted runnerだけを使う。
再実行ではなく、修正後の新しいworkflow runから署名要求する。
