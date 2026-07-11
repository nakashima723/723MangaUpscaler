# 723 Manga Upscaler

漫画背景の線画やグレースケール画像を、ローカルPCで2x/3x/4x/6x/8xにアップスケールするツールです。白地の線画は線画マスクを抽出してSDFで高解像度の黒線を再生成し、グレーを含む画像は線画だけの出力、線画と階調のレイヤー分離、または階調との再合成を選べます。

MVPの正確なスコープは [docs/00_mvp_scope.md](docs/00_mvp_scope.md)、開発ロードマップは [docs/05_development_roadmap.md](docs/05_development_roadmap.md) を参照してください。

## Windows導入

Python 3.11以上を使います。PowerShellでリポジトリ直下に移動して、開発用依存関係込みでインストールします。

```powershell
cd .\723MangaUpscaler
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
mlu doctor
```

`mlu doctor` はMVPに必要なPython依存関係を表示します。Real-CUGAN、waifu2x、Real-ESRGAN、Potraceなどの外部バイナリはMVPでは不要です。
`mlu` が見つからない場合は仮想環境が有効か確認し、同じ操作を `python -m mlu doctor` のように実行してください。PowerShellで仮想環境を有効化できない場合は、必要に応じて `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` を設定します。外部ツールのパスは、まずは空白や日本語を含まないASCIIパスに置くと切り分けが容易です。

## GUI

Windows用GUI exeは以下です。

```text
dist\723MangaUpscaler.exe
```

配布形式はこの単体EXEだけです。CustomTkinterのテーマ、フォント、設定、DIPlib DLL、第三者ライセンス原文を内包し、起動時に一時ディレクトリへ展開します。

GUIのタイトルは「723モノクロ線画拡大ツール　1.00」です。入力画像、出力倍率、明るさ、グレー部分の扱い、出力フォルダを指定してPNGまたはPSDを書き出せます。倍率は4倍が既定で、2倍、3倍、6倍、8倍も選べます。明るさは0が既定で、-10から+10まで整数単位で調整できます。スライダー左右の「-」「+」ボタンでも1段階ずつ変更できます。グレー部分の扱いは「線画と黒ベタのみ」が既定で、「グレー部分を除去して線画のみ出力」「線画とグレー部分を分けて出力」「グレー部分を線画と合成して出力」を選択できます。分離出力では、既定で `Line Art`、`Grayscale Tone`、`Background` の3レイヤーを持つグレースケールPSDを1ファイル生成し、設定を外すと主線PNGと階調PNGを個別に生成します。

内部の `soft_sdf_threshold` は、最低値-10を0.060、中央0を0.291、最大値+10を0.621とする連続・単調な区分線形対応です。新しい0は従来の明るさ-3相当、新しい+10は従来の+7相当です。背景まで線として扱う0.00は使用しません。

倍率メニュー右側の「プレビューを表示する」は既定でONです。入力画像を選ぶと、実際の出力と同じ処理・設定で作った出力プレビューを右側に自動表示し、倍率または明るさを変えるたびに更新します。更新時は表示中の入力画像上の中心座標と表示倍率を維持するため、見ている場所がずれたり全体表示へ戻ったりしません。プレビュー生成では指定出力先へ書き出さず、処理専用の一時フォルダを完了時・失敗時とも削除します。出力後の縦横ピクセル数の積が36,000,000以上になる場合は、同じ入力で最初に生成する前に確認します。「いいえ」を選ぶとチェックが外れ、再びONにするまで出力プレビュー処理を行いません。拡大・縮小ボタンとドラッグ移動は左右のペインで連動します。

「フォルダを指定して一括変換」では、選択フォルダ直下の `png, jpg, jpeg, tif, tiff, bmp` をまとめて処理できます。拡張子メニューの既定は「すべての対応画像」で、1種類だけにも絞れます。「指定した文字列を含むファイルのみ変換」をONにすると、拡張子条件とファイル名（拡張子を除く）の部分一致をAND条件で適用します。文字列照合は大文字小文字を区別せず、空白・Windowsでファイル名に使えない文字だけの入力は文字列条件なしとして扱います。出力先を明示していない場合は、入力フォルダ内の `723UpScaler_output` を使用します。入力フォルダ自身を出力先に指定しても、GUIが以前生成したPNGは次回の変換対象から除外します。出力前に対象枚数を確認し、OKの場合だけ変換します。プレビューには条件に一致する先頭の1枚だけを表示します。サブフォルダ内の画像はGUI一括変換の対象外です。

exeを作り直す場合は、開発用依存関係を入れた環境で以下を実行します。

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_gui_exe.ps1
```

ビルドスクリプトは常にonefile形式の `dist\723MangaUpscaler.exe` を生成します。フォルダ版を生成するオプションはありません。ビルド時にはインストール済み依存関係の正規ライセンス原文を検証・収集し、対応外のAVIFデコーダとアプリが使わないSciPy機能を除外します。SciPyの凍結用最小構成は `tests/test_packaging.py` で使用APIを固定しているため、新しい `scipy.ndimage` APIを使う場合は先に同テストとPyInstallerフックを更新してください。

### Code signing policy

一般配布では自己署名証明書を使いません。自己署名は無料ですが、利用者のPCでは信頼されずSmartScreen上も未署名と同等のためです。無料で信頼済みAuthenticode署名を得る候補として、条件を満たすオープンソースプロジェクト向けのSignPath Foundationを使用します。申請条件と運用方針は [コード署名ポリシー](docs/12_code_signing_policy.md) を参照してください。

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/). Author、Reviewer、Approverは[プロジェクト管理者 nakashima723](https://github.com/nakashima723)です。署名要求はGitHub ActionsのCI userが提出し、管理者が手動承認します。詳細は[コード署名ポリシー](docs/12_code_signing_policy.md)、プライバシー条件は[PRIVACY.md](PRIVACY.md)を参照してください。グレースケール・PSD対応とライセンス再監査は完了しており、署名対象と同じone-file EXEの未署名pre-releaseを先に公開してからSignPath Foundationへ申請します。審査承認とGitHub App、Project、Artifact Configuration、Signing Policyの設定がすべて完了するまで、実署名workflowは無効のままです。

信頼済みCode Signing証明書がWindows証明書ストアにある環境では、次のコマンドがunsigned stageのビルド、SHA-256署名、DigiCert RFC 3161 timestamp、改ざん検知、最終成果物の置換までを行います。秘密鍵ファイルやパスワードはリポジトリへ置きません。

```powershell
$env:UPSCALER_SIGNING_CERT_THUMBPRINT = "信頼済み証明書のthumbprint"
powershell -ExecutionPolicy Bypass -File .\tools\build_signed_gui_exe.ps1
```

既存の署名済み成果物だけを検証する場合は以下を使います。

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\verify_gui_signature.ps1 `
  -Path .\dist\723MangaUpscaler.exe `
  -ExpectedThumbprint "期待するthumbprint" `
  -TestTamperDetection
```

通常の `build_gui_exe.ps1` は必ず未署名EXEを生成します。SignPath FoundationのReleased要件を満たすための初回pre-releaseに限り、未署名であることを明記し、GitHub-hosted buildのSHA-256とともに公開します。審査完了後の正式リリースでは検証済みの署名後EXEだけを配布し、SHA-256も署名とタイムスタンプの後に計算します。

## 最小実行

単一画像処理では、出力先を `-o` で明示します。公開用の
`examples/synthetic_lineart.png` は、このリポジトリ内の生成スクリプトから
作った再配布可能な合成線画です。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_lineart_x4.png --scale 4 --preset line_only --overwrite
```

生成物は以下です。

- `synthetic_lineart_x4.png`: 最終8bit PNG

通常実行では配布用途のPNGだけを生成し、パラメータを含む `.mlus-run.json` は生成しません。デバッグ用の実行記録が必要な場合は `--save-run-json` を付けます。`--debug-dir` を指定した場合も、デバッグレイヤーと一緒に実行記録を保存します。

出力先ディレクトリは自動作成されます。既に同名ファイルがある場合は、上書き事故を避けるため `--overwrite` なしでは停止します。SDFレンダリングは画像サイズによって数秒から数十秒かかることがあります。

2x/3x/6x/8xも同じコマンドで倍率だけ変えます。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_lineart_x2.png --scale 2 --preset line_only --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_lineart_x3.png --scale 3 --preset line_only --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_lineart_x6.png --scale 6 --preset line_only --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_lineart_x8.png --scale 8 --preset line_only --overwrite
```

黒地に白線の反転素材は `--invert` を付けます。黒ベタ背景の複雑な素材はMVP後の対象です。

```powershell
mlu upscale .\path\to\inverted.png -o .\tmp\mvp\inverted_x4.png --scale 4 --preset line_only --invert --overwrite
```

## プリセット

通常は `line_only` から使います。

| プリセット | 用途 | 既定の外部ツール |
|---|---|---|
| `line_only` | 白地に黒線の純線画。MVPの標準。 | なし |
| `gray_tone` | 階調保持確認用。純線画では `tone_hr` を自動で最終合成から外す。 | Real-CUGAN優先、未設定ならLanczos fallback |
| `conservative` | 破綻を避ける保守的な階調ブランチ確認用。 | waifu2x優先、未設定ならLanczos fallback |

純線画の通常用途では `line_only` を使い、線幅やジャギーを調整する時だけ `--width-bias-source-px`、`--soft-sdf-threshold`、`--aa-radius-hr-px` を変えます。

## バッチ処理

ディレクトリ内の `png, jpg, jpeg, tif, tiff` をまとめて処理できます。既定は逐次処理で、相対ディレクトリを保ったまま `stem_x{scale}.png` を出力します。

```powershell
mlu batch .\examples .\tmp\batch_x4 --scale 4 --preset line_only --overwrite
```

生成物は以下です。

- `*_x4.png`: 各入力画像の最終PNG
- `summary.json`: バッチ全体の成功/失敗サマリ
- `summary.csv`: 表計算で確認しやすいサマリ

1枚の読み込みや保存に失敗しても残りの画像は処理を続けます。各画像の実行記録が必要な場合は `--save-run-json`、デバッグレイヤーもまとめて出したい場合は `--debug-dir` を指定します。バッチ全体の `summary.json` と `summary.csv` は処理結果として通常時も生成します。

```powershell
mlu batch .\examples .\tmp\batch_x4 --scale 4 --preset line_only --debug-dir .\tmp\batch_debug --overwrite
```

## 比較出力

パラメータを変えた複数出力をまとめて生成し、見比べるための比較PNGを作れます。

```powershell
mlu compare .\examples\synthetic_lineart.png -o .\tmp\compare_line_width --scale 4 --preset line_only --grid .\config\grids\line_width.yaml --overwrite
```

生成物は以下です。

- `variants/*.png`: 各パラメータの最終出力
- `contact_sheet.png`: 全体サムネイルの横並び比較
- `center_crop_1x.png`: 中央切り出しの等倍比較
- `center_crop_200pct.png`: 中央切り出しの200%比較
- `compare-summary.json`: 各variantの設定、出力パス、警告を含む実行記録

グリッドYAMLは以下のように書きます。

```yaml
version: 1

parameters:
  sdf.width_bias_source_px:
    - -0.25
    - -0.10
    - 0.0
```

サンプル画像で生成した比較例です。

`contact_sheet.png` は全体の破綻確認、`center_crop_1x.png` と `center_crop_200pct.png` は線幅、ジャギー、細線欠けの確認に使います。上の例では `sdf.width_bias_source_px` を左から順に変えており、太りや欠けが少ない列を採用します。

## デバッグ出力

`--debug-dir` を指定すると、最終PNGに加えて処理途中のPNGも保存します。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_lineart_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\mvp\debug_synthetic
```

debugディレクトリには番号付きで以下が出ます。

- `00_input_gray.png`: 入力を白背景合成後にグレースケール化した画像
- `01_darkness.png`: 黒さを表す画像
- `02_line_prob.png`: 線らしさの連続値
- `03_line_mask.png`: 二値の線画マスク
- `04_sdf_hr_preview.png`: 高解像度SDFの確認用画像
- `05_line_alpha_hr.png`: 高解像度の線アルファ
- `06_final.png`: 白キャンバスに黒線合成した最終画像
- `NN_line_soft_hr.png`: `line_soft` を高解像度化した画像
- `NN_soft_mask_hr.png`: SDF距離場の元になるsoft support
- `NN_sdf_alpha_before_soft_mode_hr.png`: `soft_alpha_mode` 適用前のSDF alpha
- `NN_tone_source.png`: `tone_source.mode` が `lift_lines` / `passthrough` のときの階調素材
- `NN_tone_hr.png`: `tone_hr` を最終合成に使うときの高解像度階調素材

`--line-renderer potrace` を使う場合は、SDFプレビューの代わりに `04_potrace.svg` が保存され、Potraceで作った `05_line_alpha_hr.png` と、比較用の `07_sdf_reference_line_alpha_hr.png` が出ます。

`inspect` は出力PNGパスを別指定せず、debugディレクトリだけを作ります。`06_final.png` と `06_final.mlus-run.json` も同じdebugディレクトリに保存します。

```powershell
mlu inspect .\examples\synthetic_lineart.png --preset line_only --debug-dir .\tmp\mvp\inspect_synthetic
```

## 調整

既定では、元画像由来の `line_soft` を高解像度化し、そのsoft maskからSDFを作る `distance_source: soft_mask_hr` を使います。source解像度の二値マスクから距離場を作るより、浅い建築線の階段状ジャギーが出にくく、直線を推定して描き足す処理ではないため、元画像にない長い細線を生成しにくい方式です。

`line_soft` のcoverageは既定で `darkness` です。これは元画像の黒さをそのまま使い、線検出用の `line_prob` で濃度を持ち上げません。旧挙動は `max_probability` として残していますが、浅角度の屋根線や電線に大きな周期の波打ちが出やすいため、通常は既定値を使います。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_binary_sdf.png --scale 4 --preset line_only --sdf-distance-source binary_mask --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_soft_sdf.png --scale 4 --preset line_only --sdf-distance-source soft_mask_hr --soft-sdf-threshold 0.22 --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_legacy_soft.png --scale 4 --preset line_only --line-soft-coverage-mode max_probability --line-soft-coverage-gamma 1.0 --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_wide.png --scale 4 --preset line_only --width-bias-source-px 0.15 --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_sharp.png --scale 4 --preset line_only --aa-radius-hr-px 0.5 --overwrite
```

`--soft-sdf-threshold` はsoft coverageをSDF形状に変換する閾値です。下げると薄い線を拾いやすくなり、上げると線の芯寄りになります。`--line-soft-coverage-mode` は `darkness` / `line_probability` / `max_probability` を選べます。`line_probability` は診断用で、通常出力には向きません。`--width-bias-source-px` は線幅を元画像ピクセル基準で増減します。`--aa-radius-hr-px` は高解像度側のアンチエイリアス幅です。

`line_only` の既定では `directional_smoothing` を無効にしています。これは直線を検出して描き足す処理ではなく、SDFで作った既存の線alphaを局所推定角に沿って平滑化する実験機能ですが、浅角度線では元画像にない波打ちを増やす場合があるためです。斜め線だけを切り分けたい場合は明示的に有効化します。

通常出力では、SDFのsmoothstepが内外とも完全に飽和して最終alphaが二値soft maskと一致する条件を厳密に判定し、不要な距離変換を省略します。線幅やAA設定で距離が必要な側だけを計算し、デバッグ出力では完全な距離マップを保持します。距離変換にはApache-2.0のDIPlib 3.6.1を使い、SciPy参照実装とのfloat32距離および最終PNG画素の完全一致を回帰テストしています。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_no_directional_smoothing.png --scale 4 --preset line_only --disable-directional-smoothing --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_directional_smoothing.png --scale 4 --preset line_only --enable-directional-smoothing --directional-smoothing-strength 0.55 --overwrite
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_strong_directional_smoothing.png --scale 4 --preset line_only --enable-directional-smoothing --directional-smoothing-strength 0.75 --directional-smoothing-radius-hr-px 3 --overwrite
mlu compare .\examples\synthetic_lineart.png -o .\tmp\compare_directional_smoothing --scale 4 --preset line_only --grid .\config\grids\directional_smoothing.yaml --overwrite
mlu compare .\examples\synthetic_lineart.png -o .\tmp\compare_wave_soft_coverage --scale 4 --preset line_only --grid .\config\grids\wave_investigation.yaml --crop-source-size 220 --thumbnail-width 320 --overwrite
```

`--debug-dir` 指定時は、補正前alpha、適用重み、差分が `*_directional_smoothing_*.png` として保存されます。

以下は浅角度線の波打ち調査用比較例です。左端が旧 `max_probability` 系で、中央の `darkness_thr022_sdf_only` が現行既定に近い設定です。

「長いストロークを単純化」の実験比較です。左から補正なし、弱、中、強です。64 source px以上で、角を含まず、直線性と線幅安定性を満たす枝だけを対象にします。短線、曲線、装飾、複雑ディテールは補正しません。

中心線は0.5 source px間隔へ等弧長化し、Gaussian低域通過で短周期成分を減衰させます。接線方向の変位は捨て、法線方向の変位だけを使うため、中心線点を少数の直線区間へ置き換えません。端点と角は固定します。

弱・中・強は `sigma 0.75 / 1.00 / 1.25 source px`、幾何強度 `0.50 / 0.75 / 1.00`、最大変位 `0.50 / 0.75 / 1.00 source px` です。線幅系列にも同じGaussianフィルタを適用し、局所4倍supersamplingで再描画します。機能は既定OFFで、現時点ではconfig比較用です。

単純化候補は最終出力前に成分単位で自動検査します。8近傍の連結成分が消失、分割、誤接続した場合、元にない成分が生じた場合、または対象領域の黒画素量が元の0.80〜1.20倍を外れた場合は、そのsource成分に属する変更だけを自動的に元へ戻します。

内部coverageは最終段で二値化するため、この比較画像と個別出力PNGはアンチエイリアスのない0/255のモノクロ画像です。

安全判定を通った長い縦線と浅い横線の比較です。

従来の二値SDF単独の挙動を切り分けたい場合は、設定ファイルで以下のように指定します。

```yaml
sdf:
  distance_source: binary_mask
  soft_alpha_mode: none
  soft_gain: 0.0
```

建築背景向けの `line_stabilizer` は、現状では元画像にない極細線を出すことがあり、MVP既定から外しています。実験比較のためコードとCLIは残しますが、通常の `line_only` では無効です。debug出力で `*_line_geometry_hr.png` が出る場合、その白線部分が幾何補正の候補です。

```yaml
line_stabilizer:
  enabled: false
  strength: 0.55
```

CLIでは以下のように明示した場合だけ一時的に有効化できます。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\mvp\synthetic_experimental_lines.png --scale 4 --preset line_only --enable-line-stabilizer --line-stabilizer-strength 0.55 --overwrite
```

## Potraceレンダラー

SDFの代わりにPotraceで線をベクター化してからPNGへ戻す実験的なレンダラーです。既定は引き続きSDFです。Potraceは外部ツールなので同梱せず、利用者が別途導入して設定します。

```yaml
external_tools:
  potrace: "C:/tools/potrace/potrace.exe"
  cairosvg: "C:/tools/cairosvg/cairosvg.exe"
```

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\potrace\synthetic_potrace.png --scale 4 --preset line_only --line-renderer potrace --config .\config\example.mlus.yaml --debug-dir .\tmp\potrace\debug_synthetic --overwrite
```

Potrace未設定時はSDFへ自動フォールバックせず、明確なエラーで停止します。`line_stabilizer` はSDF向けの実験機能のため、Potraceレンダラーと同時には使えません。

## 階調ブランチ

### 相対的な線画・階調分離（実験機能）

`--grayscale-mode` は、広いグレー面とその上の線を単純な黒閾値ではなく、周囲から推定した局所階調に対する相対暗化率で分離します。カラー入力は従来どおり先にsRGB輝度へ変換し、RGBAは白背景へ合成してから処理します。

線coverageの既定 `quality_hybrid` は、局所階調が白に近い場所では従来処理の `line_soft` を使い、グレー上では相対暗化率を使います。局所階調 `B` に対する従来処理の重みは `B <= 0.90` で0、`B >= 0.98` で1となり、その間をsmoothstepで連続補間します。相対側だけは固定gain `2.425` を適用してから合成します。このgainは現在の `soft_sdf_threshold` から算出し直さないため、GUIの明るさ設定やCLIのSDF閾値は引き続き線の採否へ反映されます。比較用に `relative_contrast` と旧方式相当の `detection_probability` も設定ファイルから選べます。

```powershell
# 階調を捨て、相対検出した線画だけを出力
mlu upscale input.png -o line.png --scale 4 --grayscale-mode line_only

# 従来互換: line.pngと黒RGB・alpha=(1-階調輝度)のline_tone.pngを出力
mlu upscale input.png -o line.png --scale 4 --grayscale-mode separate

# グレースケールPSDへ線画・グレー・白背景をレイヤー分離して出力
mlu upscale input.png -o layers.psd --scale 4 --grayscale-mode separate --separate-output-format psd

# Lanczosまたは指定upscalerで拡大した階調へ線画を合成
mlu upscale input.png -o composite.png --scale 4 --grayscale-mode composite
```

GUIで `separate` を選ぶと「PSDで出力する」が表示され、既定でONになります。ONでは単一のグレースケールPSDへ、上から `Line Art`、`Grayscale Tone`、`Background` の3レイヤーを保存します。線画とグレーは黒画素＋透明度チャンネルで、PSDの統合表示は `composite` と一致します。深度は `io.output_bit_depth` に従って8-bitまたは16-bitです。OFFでは従来どおり、主線PNGと `_tone.png` のRGBA PNGを出力します。CLI・YAMLの後方互換既定はPNGで、PSDを使う場合は `--separate-output-format psd` を明示します。`separate` / `composite` で `upscaler.engine: none` の場合は、階調枝だけ内部Lanczosを使用します。グレー分離モード専用の追加線幅補正は行わず、白地の線形状と細線接続を従来処理へ近づけます。局所背景推定半径より太い黒ベタ、線と階調が完全に同化した箇所、画像端から推定半径内は原理的に曖昧であり、現段階では実験対象です。

`gray_tone` / `conservative` では、`tone_source` を高解像度化してからSDF線を合成できます。外部upscalerが未設定で `fallback: lanczos` の場合は、内部Lanczosで代替します。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\gray\synthetic_gray_tone.png --scale 4 --preset gray_tone --overwrite --debug-dir .\tmp\gray\debug_synthetic
```

既定の `composite.tone_usage: auto` では、入力が純線画に見える場合、薄いtone残渣が品質を下げないよう `tone_hr` を最終合成に使わず白キャンバスへ戻します。グレー階調の合成を強制比較したい場合だけ `--tone-usage always` を使います。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\gray\synthetic_tone_forced.png --scale 4 --preset gray_tone --tone-usage always --overwrite
```

外部ツールの設定状況は `doctor` で確認します。

```powershell
mlu doctor --config .\config\example.mlus.yaml
```

外部ツールの行が `realcugan: C:\...` のような実パスなら認識済みです。`not configured` はconfigにもPATHにも見つからない状態、`unavailable` はconfigに書いたパスが存在しない状態を表します。

## Real-CUGAN導入

Real-CUGANは階調ブランチ用の任意外部ツールです。純線画の `line_only` では不要です。

1. Windows用の `realcugan-ncnn-vulkan.exe` を別途入手して展開します。
2. 設定ファイルにパスを書きます。

```yaml
external_tools:
  realcugan: "C:/tools/realcugan-ncnn-vulkan/realcugan-ncnn-vulkan.exe"
```

3. `doctor` で認識されるか確認します。

```powershell
mlu doctor --config .\my_tools.yaml
```

4. 階調ブランチを試します。

```powershell
mlu upscale .\examples\synthetic_lineart.png -o .\tmp\gray\synthetic_realcugan.png --scale 4 --preset gray_tone --config .\my_tools.yaml --tone-usage always --overwrite
```

グレー階調がある入力、または `--tone-usage always` で階調ブランチを強制した場合、Real-CUGAN未設定時は設定どおりLanczos fallbackへ落ちます。実行ログには `requested_engine`、実際の `engine`、fallback有無、stderrが保存されます。

## よくある失敗

| 症状 | 原因 | 対処 |
|---|---|---|
| 出力が既に存在するエラー | 同名ファイルがある | `--overwrite` を付けるか出力名を変える |
| 黒地白線が消える | 入力の濃度方向が逆 | `--invert` を付ける |
| 線が太い | SDF線幅補正が強い | `--width-bias-source-px -0.10` や `-0.25` を試す |
| 細線が欠ける | 閾値やcleanupが強い | `--soft-sdf-threshold` を下げる、プリセットを見直す |
| グレーが重なって汚く見える | 純線画にtone branchを強制している | 既定の `--tone-usage auto` を使う |
| Potraceが動かない | 外部バイナリ未設定 | `external_tools.potrace` と `external_tools.cairosvg` を設定し、`mlu doctor --config ...` で確認する |
| Real-CUGANが動かない | 外部バイナリ未設定またはPATH外 | `external_tools.realcugan` を設定し、`mlu doctor --config ...` で確認する |
| Real-CUGANでVRAM不足になる | tile-sizeが大きい | configの `upscaler.tile_size` を小さくする |

## 現在の対象外

以下はMVP後のロードマップ項目です。

- Real-CUGAN、waifu2x、Real-ESRGANの実バイナリ導入環境での品質保証
- 16bit PNGの品質保証

## ライセンス

本体はApache-2.0です。グレースケール分離とPSD出力は標準ライブラリおよび既存のNumPy、SciPy、Pillowだけで実装しており、この更新による第三者依存関係の追加はありません。単体EXEにはCPython、Tcl/Tk、NumPy/OpenBLAS、SciPy、Pillow、PyYAML、CustomTkinter、darkdetect、DIPlib、packaging、PyInstaller bootloaderの第三者告知と正規ライセンス原文を `licenses` 配下へ内包します。外部のPotrace、Real-CUGAN、waifu2x、Real-ESRGAN、モデルファイルは同梱せず、利用者が別途インストールしたコマンドとして呼び出します。外部ツールやモデルを再配布する場合は、それぞれのライセンスと再配布条件を別途確認してください。
