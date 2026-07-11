# 04. CLIと設定ファイル仕様

## 1. CLI名

`mlu`

`manga-lineart-upscaler` の略称だ。

## 2. コマンド一覧

### 2.1 `upscale`

単一画像を処理する。

```bash
mlu upscale input.png -o output.png --scale 4 --preset line_only --debug-dir debug
```

主要オプション：

```text
input                       入力画像
-o, --output                出力画像
--scale                     2, 3, 4, 6, 8
--preset                    line_only / gray_tone / conservative
--config                    YAML設定ファイル
--debug-dir                 デバッグレイヤー出力先
--line-renderer             sdf / potrace
--upscaler                  none / lanczos / realcugan / waifu2x / realesrgan
--upscaler-fallback         none / lanczos
--tone-usage                auto / always / never
--invert                    入力の白黒を反転して扱う
--sdf-distance-source       binary_mask / soft_mask_hr
--soft-sdf-threshold        soft_mask_hr用のsupport閾値
--line-soft-coverage-mode   darkness / line_probability / max_probability
--line-soft-coverage-gamma  line_soft coverageへ適用するgamma
--width-bias-source-px      元解像度基準の線幅補正。既定は0
--aa-radius-hr-px           高解像度ピクセル基準のAA半径
--enable-directional-smoothing
--disable-directional-smoothing
--directional-smoothing-strength
--directional-smoothing-radius-hr-px
--directional-smoothing-min-angle-from-axis-degrees
--directional-smoothing-full-strength-angle-from-axis-degrees
--overwrite                 既存出力を上書き
```

MVPでは `--scale 2`, `--scale 3`, `--scale 4`, `--scale 6`, `--scale 8` を扱う。線画MVPの既定は `--upscaler none` とする。`gray_tone` / `conservative` では外部upscalerが未設定の場合、設定に応じて `lanczos` fallbackを使える。`--tone-usage auto` では純線画判定時に `tone_hr` を最終合成へ使わない。

### 2.2 `batch`

ディレクトリ内の画像を一括処理する。

```bash
mlu batch input_dir output_dir --scale 4 --preset line_only --workers 1
```

対象拡張子は既定で `png,jpg,jpeg,tif,tiff`。相対ディレクトリを保って `stem_x{scale}.png` を出力する。1ファイル失敗しても残りを処理し、`summary.json` と `summary.csv` に結果を保存する。既定では `workers=1` とし、速度より精度と再現性を優先する。現時点では `--workers 1` のみ対応する。

主要オプション：

```text
input_dir                   入力ディレクトリ
output_dir                  出力ディレクトリ
--scale                     2, 3, 4, 6, 8
--preset                    line_only / gray_tone / conservative
--config                    YAML設定ファイル
--extensions                カンマ区切り拡張子
--workers                   1のみ対応
--debug-dir                 画像ごとのdebug出力ベースディレクトリ
--line-renderer             sdf / potrace
--summary-json              summary JSON出力先
--summary-csv               summary CSV出力先
--invert                    入力の白黒を反転して扱う
--line-soft-coverage-mode   darkness / line_probability / max_probability
--line-soft-coverage-gamma  line_soft coverageへ適用するgamma
--overwrite                 既存出力を上書き
```

### 2.3 `inspect`

マスク抽出だけを試し、デバッグレイヤーを出す。

```bash
mlu inspect input.png --preset line_only --debug-dir debug_inspect
```

### 2.4 `doctor`

依存関係と任意外部バイナリの設定状況を確認する。

```bash
mlu doctor --config config/example.mlus.yaml
```

確認項目：

- Pythonバージョン
- OpenCV/Pillow/numpy/scikit-image
- Real-CUGAN実行ファイル
- waifu2x実行ファイル
- Real-ESRGAN実行ファイル
- Potrace実行ファイル
- CairoSVGまたはInkscape
- 書き込み権限

### 2.5 `compare`

パラメータグリッドを試し、比較シートを出す。

```bash
mlu compare input.png -o compare_out --preset line_only --grid config/grids/line_width.yaml
```

主要オプション：

```text
input                       入力画像
-o, --output-dir            比較出力ディレクトリ
--grid                      YAMLグリッド
--scale                     2, 3, 4, 6, 8
--preset                    line_only / gray_tone / conservative
--config                    YAML設定ファイル
--debug-dir                 variantごとのdebug出力ベースディレクトリ
--line-renderer             sdf / potrace
--thumbnail-width           contact_sheetの各列幅
--crop-source-size          中央切り出しサイズ。元画像ピクセル基準
--invert                    入力の白黒を反転して扱う
--line-soft-coverage-mode   darkness / line_probability / max_probability
--line-soft-coverage-gamma  line_soft coverageへ適用するgamma
--overwrite                 既存出力を上書き
```

生成物：

```text
compare_out/
  variants/
    01_variant-name.png
    01_variant-name.mlus-run.json
  contact_sheet.png
  center_crop_1x.png
  center_crop_200pct.png
  compare-summary.json
```

グリッドYAMLは `base`、`parameters` の直積、または `variants` の明示列挙に対応する。

```yaml
version: 1

parameters:
  sdf.width_bias_source_px:
    - -0.25
    - -0.10
    - 0.0
```

## 3. 設定解決順

設定は以下の優先順位でマージする。

```text
1. 内蔵デフォルト
2. プリセットYAML
3. ユーザー指定config YAML
4. CLI引数
```

CLI引数が最優先だ。

## 4. YAMLスキーマ案

```yaml
version: 1

io:
  output_bit_depth: 8
  preserve_alpha: false
  overwrite: false

pipeline:
  scale: 4
  line_renderer: sdf
  tone_mode: white_canvas
  debug: true

mask:
  black_threshold: 0.72
  adaptive:
    enabled: false
    method: sauvola
    window_size: 31
    k: 0.18
  hysteresis:
    enabled: true
    strong: 0.50
    weak: 0.25
  cleanup:
    min_component_area: 6
    close_radius: 0
    fill_holes_area: 12
  soft_coverage:
    mode: darkness
    gamma: 1.0

sdf:
  interpolation: lanczos
  distance_source: soft_mask_hr
  soft_sdf_threshold: 0.22
  width_bias_source_px: 0.0
  aa_radius_hr_px: 0.75
  soft_alpha_mode: none
  soft_gain: 0.0

line_stabilizer:
  enabled: false
  strength: 0.55

directional_smoothing:
  enabled: false
  strength: 0.55
  radius_hr_px: 2
  min_angle_from_axis_degrees: 20.0
  full_strength_angle_from_axis_degrees: 34.0
  orientation_sigma_hr_px: 1.0
  tensor_sigma_hr_px: 2.0
  min_orientation_confidence: 0.12
  min_gradient_energy: 0.00001
  min_alpha: 0.04
  support_dilate_hr_px: 1
  max_delta: 0.35

centerline_simplification:
  enabled: false
  filter_sigma_source_px: 0.0
  filter_sample_step_source_px: 0.50
  max_filter_displacement_source_px: 0.75
  strength: 1.0
  alpha_threshold: 0.50
  min_path_length_source_px: 64.0
  endpoint_protection_source_px: 3.0
  max_radius_source_px: 2.25
  support_margin_source_px: 0.75
  binarize_output: true
  binary_threshold: 0.50
  max_new_component_area: 2
  corner_angle_degrees: 45.0
  corner_window_source_px: 3.0
  geometry_strength: 1.0
  max_thinning_iterations: 128
  long_stroke_gate:
    enabled: true
    min_chord_arc_ratio: 0.985
    max_line_fit_rms_source_px: 0.35
    max_line_fit_deviation_source_px: 1.0
    max_width_cv: 0.20
    max_width_ratio: 1.50
    skip_paths_with_corners: true
  component_rollback:
    enabled: true
    preserve_component_count: true
    min_ink_ratio: 0.80
    max_ink_ratio: 1.20

potrace:
  turdsize: 2
  alphamax: 1.0
  opttolerance: 0.2
  opticurve: true
  turnpolicy: minority
  rasterizer: cairosvg

tone_source:
  mode: white_canvas
  dilate_radius: 1.2
  lift_strength: 0.85
  background_blur_radius: 9
  protect_midtones: true

upscaler:
  engine: none
  scale: 4
  fallback: lanczos
  realcugan:
    noise: -1
    model: auto
    tile_size: 256
    tta: false
  waifu2x:
    model: models-cunet
    noise: -1
    tile_size: 256
  realesrgan:
    model: realesrgan-x4plus-anime
    tile_size: 256

composite:
  line_darkness: 1.0
  edge_alpha_gamma: 1.2
  tone_usage: auto
  clamp: true

debug:
  save_layers: true
  save_run_json: false
  contact_sheet: false

external_tools:
  realcugan: null
  waifu2x: null
  realesrgan: null
  potrace: null
  cairosvg: null
  inkscape: null
```

## 5. 出力ファイル命名

単一処理：

```text
output.png
output_debug/
  00_input_gray.png
  01_darkness.png
  02_line_prob.png
  03_line_mask.png
  04_sdf_hr_preview.png
  05_line_alpha_hr.png
  06_final.png
  NN_line_soft_hr.png
  NN_soft_mask_hr.png
  NN_sdf_alpha_before_soft_mode_hr.png
  NN_tone_source.png        # lift_lines / passthrough時
  NN_tone_hr.png            # tone_hrを最終合成に使う時
  NN_directional_smoothing_source_alpha_hr.png
  NN_directional_smoothing_weight_hr.png
  NN_directional_smoothing_delta_hr.png
  NN_centerline_source.png
  NN_long_stroke_eligible_source.png
  NN_component_rollback_source.png
  NN_filtered_centerline_source.png
  NN_centerline_filter_displacement_source.png
  NN_centerline_protected_source.png
  NN_centerline_simplification_delta_hr.png
  NN_line_geometry_hr.png   # line_stabilizer有効時
```

通常の `upscale` では `output.mlus-run.json` を生成しない。`--save-run-json`、`--debug-dir`、または設定の `debug.save_run_json: true` を明示したデバッグ実行時だけ生成する。`inspect` と `compare` はデバッグ・評価コマンドのため実行記録を生成する。

Potraceレンダラー時：

```text
output_debug/
  00_input_gray.png
  01_darkness.png
  02_line_prob.png
  03_line_mask.png
  04_potrace.svg
  05_line_alpha_hr.png
  06_final.png
  07_sdf_reference_line_alpha_hr.png
```

バッチ処理：

```text
output_dir/
  image001_x4.png
  summary.json
  summary.csv
  debug/image001/
```

各画像の `image001_x4.mlus-run.json` は `--save-run-json` または `--debug-dir` を指定した場合だけ生成する。バッチ全体の `summary.json` と `summary.csv` は通常時も生成する。

## 6. 終了コード

```text
0  成功
1  入力・出力エラー
2  設定エラー
3  外部ツールエラー
4  画像処理エラー
5  ユーザー中断
```

## 7. ログ

標準出力には簡潔な進捗を出す。詳細ログはdebug-dirに保存する。

例：

```text
入力: input.png 2000x1400
スケール: 4x → 8000x5600
線画マスク: 面積率 12.4%
線画ブランチ: sdf source=soft_mask_hr threshold=0.22 aa=0.75 width_bias=0.0 source px soft=none:0.0
Tone upscaler: lanczos via fallback
出力: output.png
```

## 8. Codex実装時の注意

- CLIを先に作り、内部処理は小さい関数に分ける。
- 画像配列のレンジを関数docstringに必ず書く。
- `0=黒, 1=白` の規約を崩さない。
- 外部コマンドはリスト形式でsubprocessに渡し、文字列結合しない。
- Windowsパスを前提にせず、`pathlib.Path` を使う。
- デバッグ画像は8bit PNGでよい。MVPの最終出力も8bit PNGを既定とし、16bit対応は後続で優先する。
