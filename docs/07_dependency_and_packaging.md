# 07. 依存関係・外部バイナリ・配布設計

## 1. Python依存関係

必須：

```text
numpy
pillow
pyyaml
scipy
diplib 3.6.1
```

開発用：

```text
pytest
ruff
```

任意：

```text
rich
cairosvg
opencv-python-headless
opencv-contrib-python-headless
```

`diplib` はApache-2.0の厳密ユークリッド距離変換をSDFへ使用する。SciPy参照実装とのfloat32画素一致を確認した3.6.1へ固定する。`cairosvg` はPythonパッケージとして導入する選択肢もあるが、現状のPotraceレンダラーでは外部CLIとして呼び出す。`opencv-python-headless` / `opencv-contrib-python-headless` はthinningなどを使う場合のみ検討し、現状のSDF処理には導入しない。

## 2. 外部バイナリ

MVPの純線画処理では外部バイナリを必須にしない。グレー階調やトーンを扱う階調ブランチではadapterを用意し、バイナリ未設定時は設定に応じて内部Lanczos fallbackへ落とす。Potraceレンダラーだけは、明示指定時に未設定ならSDFへfallbackせずエラーにする。

### 2.1 Real-CUGAN ncnn Vulkan

階調ブランチ候補。Vulkanで動くため、CUDAやPyTorch環境を前提にしない。

想定コマンド：

```bash
realcugan-ncnn-vulkan.exe -i tone_source.png -o tone_hr.png -s 4 -n -1 -t 256 -f png
```

実際の引数名や対応モデルはユーザー環境のバイナリに合わせて `doctor` と実行ログで確認する。

設定例：

```yaml
external_tools:
  realcugan: "C:/tools/realcugan-ncnn-vulkan/realcugan-ncnn-vulkan.exe"
```

### 2.2 waifu2x ncnn Vulkan

保守的なフォールバック候補。

```bash
waifu2x-ncnn-vulkan.exe -i tone_source.png -o tone_hr.png -s 4 -n -1 -t 256 -f png
```

### 2.3 Real-ESRGAN ncnn Vulkan

写真寄り・圧縮劣化が強い素材の候補。

```bash
realesrgan-ncnn-vulkan.exe -i tone_source.png -o tone_hr.png -n realesrgan-x4plus-anime -s 4 -t 256 -f png
```

### 2.4 Potrace

任意。線画マスクをベクター化する。

```bash
potrace line_mask.pbm -s -o line.svg
```

PotraceはGPLライセンスなので、配布物への同梱は避ける。外部CLIとしてパス指定する。

設定例：

```yaml
external_tools:
  potrace: "C:/tools/potrace/potrace.exe"
  cairosvg: "C:/tools/cairosvg/cairosvg.exe"
```

### 2.5 CairoSVG

PotraceのSVGをPNGへラスタライズする候補。

```bash
cairosvg line.svg -o line_alpha_hr.png --output-width 8000 --output-height 5600
```

CairoSVGが環境依存で詰まる場合は、Inkscape CLIを代替候補にする。

```yaml
potrace:
  rasterizer: inkscape
external_tools:
  inkscape: "C:/Program Files/Inkscape/bin/inkscape.exe"
```

## 3. ライセンス方針

- 本ツール本体はApache-2.0を候補にする。
- CPython、Tcl/Tk、NumPy/OpenBLAS、SciPy、Pillow、PyYAML、CustomTkinter、darkdetect、DIPlib、packaging、PyInstaller bootloaderの正規ライセンス原文を単体EXEへ内包する。
- `tools/collect_distribution_licenses.py` がビルド環境の配布メタデータから原文を収集し、見つからない場合は配布ビルドを失敗させる。
- 外部バイナリは同梱しない。
- モデルファイルは同梱しない。
- 外部ツールのライセンス確認をREADMEに明記する。
- PotraceはGPLのため、外部依存として扱う。

## 4. パッケージング

### 4.1 開発用

```bash
pip install -e .
```

または `uv` を使う。

```bash
uv sync
uv run mlu --help
```

### 4.2 配布用

pip install可能なPythonパッケージと、CustomTkinterのデータおよびDIPlibのDLLを内包するWindows向けonefile配布を維持する。GUIの配布成果物は `dist/723MangaUpscaler.exe` だけとし、onedir形式は生成しない。

候補：

- `pipx install .`
- `uv tool install .`
- `tools/build_gui_exe.ps1` でPyInstaller onefile配布を生成

### 4.3 単体EXEの最小化

- GUI非対応のPillow AVIFデコーダは収集しない。
- アプリが使わないSciPyの統計、最適化、信号処理などのサブパッケージを除外する。
- `scipy.ndimage` がモジュール読込時だけ参照する未使用の `scipy.special` は凍結版runtime hookで置き換え、連鎖するSciPy側OpenBLAS、linalg、sparseを収集しない。
- 実際に使うndimage APIは `tests/test_packaging.py` の許可リストで固定し、追加利用を無検証で配布しない。
- UPXは導入しない。現行onefileアーカイブは既に圧縮され、UPXにはDLL破損やセキュリティ製品の誤検知、展開時間増加のリスクがある。
- 配布ビルドには処理スモーク用の非公開 `--check-upscale INPUT OUTPUT` を残し、ソース版とのPNG画素完全一致を検証する。

### 4.4 Windowsコード署名

- 公開配布はWindowsが信頼するAuthenticode証明書を使い、自己署名証明書は試験専用とする。
- file digestとtimestamp digestはSHA-256、timestampはRFC 3161を使う。
- `tools/build_signed_gui_exe.ps1` は別名unsigned stageをビルドし、署名と検証に成功した場合だけ既存の配布EXEを置き換える。
- `tools/sign_gui_exe.ps1` はthumbprintで証明書を固定し、PFXやpasswordを受け付けない。秘密鍵はWindows証明書ストア、TPM/HSM、またはリモート署名サービスで管理する。
- `tools/verify_gui_signature.ps1` はAuthenticode policy、全署名、timestamp、Code Signing EKU、signer thumbprint、改ざん検知を確認する。
- 署名・timestamp後のファイルを最終成果物とし、その後にSHA-256を計算する。
- 無料の信頼済み署名は、公開OSSとして条件を満たした後にSignPath Foundationへ申請する。自己署名版を一般配布して利用者へルート証明書installを求めない。

## 5. Windows注意点

- パスに空白が含まれる前提で実装する。
- subprocessは文字列ではなく配列で渡す。
- 一時ファイルは `tempfile.TemporaryDirectory` を使う。
- 外部コマンド、return code、stdout、stderr、fallback有無はrun JSONに保存する。
- 外部バイナリが日本語パスで動かない場合を考え、一時ディレクトリをASCII寄りにするオプションを検討する。
- 長いパス対策をREADMEに書く。
- DIPlibのWindows wheelはMicrosoft Visual C++ 2015-2022 Redistributableを必要とする場合がある。PyInstallerビルド後は`DIP.dll`の同梱と別プロセスでのexe起動を確認する。

## 6. 16bit対応

MVPの既定出力は8bit PNGとする。16bit PNGは後続の優先対応として、内部表現と保存APIの設計に余地を残す。

内部はfloat32で処理する。保存時に以下へ変換する。

```text
8bit:  round(clamp(x) * 255)
16bit: round(clamp(x) * 65535)
```

Pillowだけで16bitグレースケールPNGの扱いが難しい場合は、OpenCV保存を併用する。

## 7. メモリ設計

8000x8000のfloat32画像は約256MBだ。複数レイヤーを持ってもRAM 128GBなら現実的だ。ただし無制限にコピーを作らない。

推奨：

- 中間配列を必要以上に保持しない
- debug保存後に不要配列を解放する
- `float64` を避ける
- boolean maskを使う
- 巨大画像ではcontact sheet生成を無効化する

## 8. 外部アップスケーラーのtile-size

VRAM 8GBでは、4倍出力時にtile-sizeが大きすぎると失敗する可能性がある。以下の順に試す。

```text
512 → 256 → 128 → 64
```

自動再試行は将来実装でよい。MVPでは設定値をログに出し、エラー時にtile-sizeを下げる案内を出す。
