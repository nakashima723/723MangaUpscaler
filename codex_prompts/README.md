# Codexプロンプト

Codexに貼るプロンプトは `docs/09_codex_task_prompts.md` にまとめてある。

推奨順は以下だ。

1. Task 0: リポジトリ初期化
2. Task 1: 設定読み込み
3. Task 2: 画像I/Oとグレースケール
4. Task 3〜4: 線画マスク抽出
5. Task 5: SDFレンダラー
6. Task 6〜9: 合成・tone_source・外部アップスケーラー・統合

一度に全機能を依頼せず、pytestとruffが通る小さい単位で進めるのが前提だ。
