# 09. Codex用プロンプト集

このファイルは、Codexに段階的に開発させるためのプロンプト案である。各プロンプトは、直前の実装が完了しテストが通っている前提で使う。

## 共通指示

各タスクの冒頭に以下を付ける。

```text
このリポジトリは漫画背景用のローカル線画アップスケーラーです。MVPスコープは docs/00_mvp_scope.md を正とし、白地黒線の純線画を対象にします。Webサービス連携と教師あり学習は実装しません。内部グレースケール表現は 0.0=黒, 1.0=白 のfloat32です。既存コードのコメントは削除しないでください。新規コメントは日本語で書いてください。変更後はテストを追加・更新し、pytestとruffが通る状態にしてください。
```

## Task 0: リポジトリ初期化

```text
Python 3.11以上のCLIパッケージとして、manga-lineart-upscalerの最小リポジトリを作成してください。src/mlu配下にパッケージを置き、cli.py, config.py, io.py, grayscale.py, mask_extract.py, sdf_render.py, tone_source.py, upscaler_external.py, composite.py, pipeline.py, debug_layers.py を作ってください。まだ中身は最小実装で構いません。pytestとruffを設定し、mlu --help が動く状態にしてください。
```

## Task 1: 設定読み込み

```text
config.pyにYAML設定読み込み、内蔵デフォルト、プリセット、ユーザーconfig、CLI overrideのマージ処理を実装してください。辞書の深いマージに対応してください。設定値の型が明らかに不正な場合はConfigErrorを出してください。tests/test_config.pyを追加してください。
```

## Task 2: 画像I/Oとグレースケール

```text
io.pyとgrayscale.pyを実装してください。PNGを優先して読み込み、内部float32の 0.0=黒, 1.0=白 に正規化してください。RGB/RGBA入力はグレースケール化し、RGBAはMVPでは白背景に合成してください。8bit PNG保存に対応してください。反転オプションも実装してください。tests/test_io_grayscale.pyを追加してください。
```

## Task 3: 固定閾値線画マスク

```text
mask_extract.pyに固定閾値による線画抽出を実装してください。grayからdarknessを作り、black_thresholdでline_maskを作り、line_probとline_softも返すLineMapsデータ構造を定義してください。debug保存用に0-1配列をPNG化できる関数も用意してください。tests/test_mask_extract.pyに斜め線fixtureを使ったテストを追加してください。
```

## Task 4: ヒステリシス・cleanup

```text
mask_extract.pyに強弱閾値のヒステリシス接続、小連結成分除去、穴埋めを追加してください。薄い線が強線に接続している場合は残り、孤立ノイズは消えるテストを追加してください。Sauvola局所閾値はMVP後に回します。
```

## Task 5: SDFレンダラー

```text
sdf_render.pyにline_maskからsigned distance fieldを作り、指定scaleで高解像度line_alphaを生成する処理を実装してください。insideを正、outsideを負にしてください。resize後に距離値へscaleを掛ける処理を忘れないでください。width_bias_source_px、aa_radius_hr_px、soft_alpha_mode、soft_gainを設定で制御してください。斜め線と円弧のテストを追加してください。
```

## Task 6: 合成処理

```text
composite.pyにtone_hrとline_alpha_hrを合成する処理を実装してください。内部表現は0.0=黒, 1.0=白です。基本式は final = tone_hr * (1 - line_alpha_hr * line_darkness) とし、edge_alpha_gammaとclampに対応してください。アルファチャンネルがある場合は復元できるようにしてください。tests/test_composite.pyを追加してください。
```

## Task 7: パイプライン統合

```text
pipeline.pyに、入力読み込み、グレースケール化、線画マスク抽出、SDF線生成、白キャンバス合成、PNG保存、debug出力、run JSON保存までを接続してください。外部アップスケーラーは使わず、--scale 2/3/4/6/8で動くようにしてください。tests/test_pipeline_smoke.pyを追加してください。
```

## Task 8: CLI接続

```text
cli.pyにupscale, inspect, doctorコマンドを実装してください。upscaleは単一画像処理、inspectはマスク抽出とdebug出力、doctorはPython依存関係確認を行います。MVPでは外部アップスケーラー確認は任意項目にしてください。エラー時の終了コードをdocs/04_cli_and_config_spec.mdに合わせてください。CLIスモークテストを追加してください。
```

## Task 9: 2x/3x/4x/6x/8x品質テスト

```text
合成fixtureを増やし、斜め線、円弧、窓枠風平行線、細い電線風線分について --scale 2/3/4/6/8 の出力サイズ、線幅保持、line_alphaの連続性を検証してください。漫画原稿でのシャープさと二値化耐性を優先してください。
```

## Task 10: Sauvola局所閾値（MVP後）

```text
mask_extract.pyにSauvola局所閾値を追加してください。MVP対象外の背景ムラや薄い影を扱うための拡張であり、既定は固定閾値のままにしてください。
```

## Task 11: tone_source生成（MVP後）

```text
tone_source.pyに、line_mask周辺を白側へ持ち上げるtone_source生成を実装してください。modeはwhite_canvas, lift_lines, passthroughに対応してください。lift_linesではline_maskを膨張し、blurした背景推定とlift_strengthで線領域を白側へ寄せてください。グレー階調を壊しすぎないようprotect_midtonesを実装してください。tests/test_tone_source.pyを追加してください。
```

## Task 12: 外部アップスケーラーadapter（MVP後）

```text
upscaler_external.pyに外部アップスケーラーadapterを実装してください。realcugan, waifu2x, realesrgan, lanczos, noneに対応してください。外部コマンドはsubprocess.runにリスト形式で渡してください。バイナリ未設定時はToolNotFoundErrorにしてください。ただしfallbackが設定されている場合はLanczosへ落としてください。生成したコマンドラインをrun metadataに残せるようにしてください。tests/test_upscaler_external.pyではsubprocessをモックしてください。
```

## Task 13: バッチ処理（MVP後）

```text
batchコマンドを追加してください。入力ディレクトリからpng, jpg, jpeg, tif, tiffを探索し、出力ディレクトリに同名ベースで保存してください。1ファイル失敗しても残りを継続し、summary.jsonとsummary.csvを出してください。既定workersは1にしてください。
```

## Task 14: Potraceオプション（MVP後）

```text
任意機能としてline_renderer=potraceを追加してください。line_maskをPBMに保存し、potrace CLIでSVG化し、CairoSVGまたは設定されたrasterizerで目標サイズのPNGにラスタライズしてください。Potrace未設定時は明確なエラーにしてください。SDF既定は変更しないでください。SVGとline_alpha_hrをdebugに保存してください。
```

## Task 15: compareコマンド（MVP後）

```text
compareコマンドを追加してください。YAMLで指定されたパラメータグリッドを展開し、複数設定の出力を作り、中央切り出しとコンタクトシートを生成してください。各画像に設定名をファイル名として入れてください。GUIは不要です。
```

## Task 16: README整備

```text
READMEを実用向けに整備してください。Windowsでの導入、最小コマンド、line_onlyプリセット説明、debugレイヤーの見方、よくある失敗と調整パラメータ、MVP後のReal-CUGAN/Potraceのライセンス注意を含めてください。
```
