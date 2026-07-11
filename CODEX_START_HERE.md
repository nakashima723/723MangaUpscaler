# Codex開始用ブリーフ

## 目的

漫画家が用意した白地黒線の漫画背景線画を、ローカルPCで高解像度化するCLIツールを作る。Webサービスは使わない。教師あり学習もしない。

MVPスコープは `docs/00_mvp_scope.md` を正とする。

## 最重要品質

細い電線、柵、窓枠、建築線を欠けさせないことを最優先する。次に、線画がジャギらないこと、線がガタつかないこと、線幅が不自然に変わらないことを優先する。写真のディテール復元やリアルな質感生成は優先しない。

## 基本設計

MVPでは入力画像をそのまま拡大して終わりにしない。線画をマスクとして抽出し、SDFで高解像度に再レンダリングする。

```text
入力
  → グレースケール正規化
  → 線画マスク抽出
  → SDF/距離場で高解像度line_alpha生成
  → 白キャンバスへ黒線として合成
  → 最終PNG
```

グレー階調、tone_source、Real-CUGANなどの外部アップスケーラー、PotraceはMVP後の拡張とする。

## 開発制約

- Python 3.11以上を想定する。
- MVPはCLIのみとする。
- 学習処理は作らない。
- モデルファイルや外部バイナリはリポジトリに同梱しない。
- 外部バイナリ連携はMVP後の任意機能とし、ユーザー設定でパス指定する。
- Windowsを主対象にしつつ、Linuxでも動くようにパス処理を抽象化する。
- 画像の中間結果はデバッグオプションで保存できるようにする。
- 画質パラメータは設定ファイルで再現可能にする。
- 設定ディレクトリ名は `config/` に統一する。

## 推奨リポジトリ構成

```text
manga-lineart-upscaler/
  pyproject.toml
  README.md
  src/mlu/
    __init__.py
    cli.py
    config.py
    io.py
    grayscale.py
    mask_extract.py
    sdf_render.py
    tone_source.py
    upscaler_external.py
    composite.py
    debug_layers.py
    pipeline.py
  tests/
    test_mask_extract.py
    test_sdf_render.py
    test_composite.py
    test_pipeline_smoke.py
    fixtures/
  config/
    presets/
  docs/
```

## MVPの完了条件

以下を満たしたらMVP完了とする。

- `mlu upscale input.png -o output.png --scale 4 --debug-dir debug` が動く。
- `--scale 2`, `--scale 3`, `--scale 4` が動く。
- `--invert` が動く。
- 外部アップスケーラーなしで最終PNGが出る。
- `debug`指定時に `line_prob.png`, `line_mask.png`, `line_alpha_hr.png`, `final.png` が出る。
- 合成図形テストで、斜め線と円弧の高解像度出力に明確な階段状ジャギが出ない。
- 線の平均幅が入力比で大きく変化しない。
- 2000px級入力の2x/3x/4x出力を処理できる。

## 実装順

1. CLIと設定読み込み
2. 画像I/Oとグレースケール正規化
3. 線画マスク抽出
4. SDF線再レンダリング
5. 白キャンバスへの線合成
6. PNG保存
7. デバッグレイヤー出力
8. 2x/3x/4x品質テスト
9. バッチ処理
10. グレー階調・外部アップスケーラー
11. Potraceオプション

詳細は `docs/05_development_roadmap.md` を読む。
