# 開発ログ

## 2026-07-09 ロードマップ確認と仕様質問抽出

### 作業内容

- `docs/05_development_roadmap.md`、`task_backlog.csv`、要件・設計・CLI仕様・品質計画・プリセットを確認した。
- 現状は実装前の計画リポジトリで、フェーズ0から未着手と判断した。
- 実装前に決めるべき仕様質問を、入力画像、出力用途、品質トレードオフ、MVP範囲、Phase0/1の前提に分けて整理した。
- サブエージェント2本を使い、高推論側で仕様質問、中推論側でロードマップとバックログの整合性を並行確認した。

### 確認した主な未確定点

- 入力画像の標準前提は白地に黒線でよいか。
- ハッチング、カケアミ、点描、トーンを線画ブランチと階調ブランチのどちらで扱うか。
- 出力は最終PNG 1枚をMVP主対象にするか、レイヤー分離出力を初期設計から考慮するか。
- 16bit PNG、EXIF orientation、アルファ保持をMVP必須にするか。
- MVPにバッチ処理を含めるか。
- 型ヒント方針、ライセンス方針、設定ディレクトリ名をPhase0前に固定する必要がある。

### 今後同じミスをしないための有益な失敗

- この環境では `git` がPATH上に存在せず、`git status --short` が失敗した。以後、作業前差分確認ではGitが使えるか先に確認し、使えない場合はファイル一覧と編集対象の事前確認を明記する。
- ドキュメント内に `config` と `configs` の表記揺れがある。実装前にディレクトリ名を決めないと、CLI設定探索やREADME手順で混乱する。
- `CODEX_START_HERE.md`、ロードマップ、受け入れチェックリストのMVP範囲に差がある。実装開始前にどれを正とするか決める。

## 2026-07-09 MVPスコープ確定の反映

### 作業内容

- ユーザー回答を受け、MVPを「白地黒線の純線画を2x/3x/4xで高解像度PNG化する最小版」として確定した。
- `docs/00_mvp_scope.md` を追加し、MVPスコープ、入力、出力、品質方針、外部アップスケーラー、バッチ、ライセンス、型ヒント方針を集約した。
- `README.md`、`CODEX_START_HERE.md`、`config/example.mlus.yaml`、`config/presets/line_only.yaml` を線画MVP向けに更新した。

### 決定事項

- 標準入力は白地黒線の漫画背景線画とする。
- 反転素材は `--invert` で扱い、黒ベタ背景の複雑な素材は後回しにする。
- MVPではグレー階調、トーン、点描、網点トーンを品質保証対象にしない。
- 薄いグレーは白へ飛ばし、十分暗い画素だけを線として扱う。
- 細線保持を最優先し、線幅補正の既定値は0にする。
- 出力はまず最終8bit PNG 1枚を必須とし、16bit、レイヤー分離、TIFFは後続対応とする。
- Real-CUGANなどの外部アップスケーラーとバッチ処理はMVP後に回す。
- 本体ライセンス方針はApache-2.0とする。
- 設定ディレクトリ名は `config/` に統一する。

### 今後同じミスをしないための有益な失敗

- 当初ドキュメントはグレー階調ブランチと外部アップスケーラーをMVPに含めており、純線画MVPの品質目標とずれていた。今後は `docs/00_mvp_scope.md` を最優先の仕様として確認してから実装する。

## 2026-07-09 フェーズ0 リポジトリ初期化

### 作業内容

- `images/input` のサンプル画像6枚を確認した。
  - すべてPNG/RGB、1448x1086。
  - 白地黒線のMVP前提に概ね適合。
  - アンチエイリアス由来のグレー線が多いため、黒ピクセルだけに依存しない線抽出が必要。
- `pyproject.toml` を追加し、Python 3.11以上、pytest、ruff、`mlu` console scriptを設定した。
- `LICENSE` を追加し、本体ライセンスをApache-2.0方針に合わせた。
- `src/mlu` パッケージを作成し、`cli.py`、`__main__.py`、将来実装用の主要モジュールファイルを追加した。
- `tests/test_cli.py` を追加し、CLIヘルプとMVPコマンドの存在を確認するテストを入れた。

### 検証結果

- `python -m pip install -e ".[dev]"` 成功。
- `python -m mlu --help` 成功。
- `mlu --help` 成功。
- `python -m pytest` 成功。2件通過。
- `ruff check` 成功。

### 今後同じミスをしないための有益な失敗

- 作業開始時点では `ruff` が未導入だった。フェーズ0では `pyproject.toml` のdev依存を整備したうえで `python -m pip install -e ".[dev]"` を実行してからruffを確認する。
- 初回 `ruff check` で `src/mlu/__main__.py` のimport整形エラーが出た。`ruff check --fix` で修正済み。今後もファイル追加後はすぐruffを走らせる。

## 2026-07-09 フェーズ1 画像I/OとCLI骨格

### 作業内容

- `config.py` にデフォルト設定、プリセット読み込み、ユーザー設定、CLI overrideの深いマージを実装した。
- `grayscale.py` にRGB/RGBA/Grayのfloat32正規化を実装した。
  - 内部表現は `[0.0, 1.0]`、`0.0=黒`、`1.0=白`。
  - RGBAはMVP方針に従い白背景に合成する。
- `io.py` に画像読み込み、EXIF orientation適用、8bit/16bit PNG保存を実装した。
- `cli.py` の `upscale` をPhase1用に接続し、同サイズグレースケールPNGを書き出せるようにした。
- `inspect` は `00_input_gray.png` をdebug-dirへ保存する最小実装にした。
- `.gitignore` を追加し、`tmp/`、キャッシュ、ビルド成果物を除外対象にした。
- `tests/test_config.py`、`tests/test_io_grayscale.py`、`tests/test_cli_phase1.py` を追加した。

### 検証結果

- `python -m pip install -e ".[dev]"` 成功。
- `python -m pytest` 成功。10件通過。
- `ruff check` 成功。
- `mlu doctor` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase1\sample01_gray.png --scale 2 --preset line_only --overwrite` 成功。
- `mlu inspect .\images\input\sample01.png --preset line_only --debug-dir .\tmp\phase1\debug_sample01` 成功。
- 生成された `sample01_gray.png` と `00_input_gray.png` はどちらも `L` モード、1448x1086のPNGだった。

### 今後同じミスをしないための有益な失敗

- Pillow 11.3.0で `Image.fromarray(..., mode=...)` がPillow 13以降の削除予定として警告された。保存・テスト生成では型からmode推定させる形へ修正した。
- Phase1の `upscale` はまだ拡大処理を行わず、同サイズのグレースケールPNGを書き出す。今後のフェーズでSDF拡大を接続するとき、Phase1のログ文言やテスト名が誤解を生まないか確認する。

## 2026-07-09 フェーズ2 線画マスク抽出MVP

### 作業内容

- `mask_extract.py` に線画マスク抽出を実装した。
  - `darkness = 1 - gray`
  - 固定閾値マスク
  - weak/strongのヒステリシス接続
  - 小連結成分除去
  - 小穴埋め
  - `line_prob`, `line_mask`, `line_soft`, `darkness` を持つ `LineMaps`
  - マスク面積率と過少・過大抽出警告
- `inspect` コマンドで以下のdebug画像を保存するようにした。
  - `00_input_gray.png`
  - `01_darkness.png`
  - `02_line_prob.png`
  - `03_line_mask.png`
- `doctor` で `scipy` も確認するようにした。
- `pyproject.toml` に `scipy>=1.10` を追加した。
- `tests/test_mask_extract.py` を追加し、固定閾値、ヒステリシス、細線保持、小ノイズ除去、小穴埋めをテストした。

### 検証結果

- `python -m pip install -e ".[dev]"` 成功。
- `python -m pytest` 成功。17件通過。
- `ruff check` 成功。
- `mlu inspect .\images\input\sample01.png --preset line_only --debug-dir .\tmp\phase2\debug_sample01` 成功。
- `sample01` のdebug画像はすべて `L` モード、1448x1086のPNGだった。
- サンプル6枚のマスク面積率は以下。
  - `sample01.png`: 15.82%
  - `sample02.png`: 13.78%
  - `sample03.png`: 20.18%
  - `sample04.png`: 18.40%
  - `sample05.png`: 18.01%
  - `sample06.png`: 21.62%
- すべて過少・過大抽出警告なし。

### 今後同じミスをしないための有益な失敗

- 初回 `ruff check` で `mask_extract.py` のimport整形エラーが出た。新規モジュール追加後は実装直後にruffを走らせる。
- サンプル画像はアンチエイリアスのグレー線が多く、固定閾値を狭くすると細線が欠けやすい。今後SDFに渡すマスクを評価するときは、黒純色の画素数ではなく `line_prob` とヒステリシス後の `line_mask` を見る。
- `fill_holes_area` は看板文字や窓枠の小さな白抜きを潰す可能性がある。現時点では小穴だけを対象にしているが、実サンプルで白抜き文字が潰れる場合は既定値を下げる。

## 2026-07-09 フェーズ3 SDF線再レンダリング

### 作業内容

- `sdf_render.py` にSDF線再レンダリングを実装した。
  - `signed_distance_field`: 線内側を正、外側を負にする距離場生成。
  - 高解像度リサイズ後に `* scale` する距離補正。
  - `width_bias_source_px * scale` による線幅補正。
  - `smoothstep(-aa_radius_hr_px, aa_radius_hr_px, sdf)` による `line_alpha_hr` 生成。
  - `soft_alpha_mode=max` の任意対応。
  - 空マスクは全透明、全面マスクは全不透明として安定処理。
  - `sdf_preview` によるSDF確認用画像生成。
- `inspect` コマンドを拡張し、以下も保存するようにした。
  - `04_sdf_hr_preview.png`
  - `05_line_alpha_hr.png`
- `tests/test_sdf_render.py` を追加し、SDF符号、scale補正、線幅補正、AA半径、斜め線の半透明遷移、line_soft合成、空/全面マスクをテストした。

### 検証結果

- `python -m pip install -e ".[dev]"` 成功。
- `python -m pytest` 成功。28件通過。
- `ruff check` 成功。
- `mlu inspect .\images\input\sample01.png --preset line_only --debug-dir .\tmp\phase3\debug_sample01` 成功。
- `sample01` のSDF debug出力は以下。
  - `04_sdf_hr_preview.png`: `L` モード、5792x4344。
  - `05_line_alpha_hr.png`: `L` モード、5792x4344。
- サンプル6枚の `line_alpha_hr` はすべて5792x4344、値域は0.0〜1.0。

### 今後同じミスをしないための有益な失敗

- 最初の線幅補正テストでは、`nearest` リサイズでSDF値が大きな段差になり、`width_bias_source_px=0.25` では面積差が出なかった。SDFのパラメータ効果テストでは、補間方法・AA半径・補正量が観測可能な組み合わせになっているか確認する。
- AA半径テストでも、SDF値の段差がAA半径より大きいと半透明画素が出ない。`aa_radius_hr_px` のテストでは境界が半透明になる条件を明示する。
- `line_soft` は薄線救済になる一方で薄い汚れも復活させる可能性があるため、既定は `none` のまま維持する。

## 2026-07-09 フェーズ4 白キャンバス合成と最小pipeline接続

### 作業内容

- `composite.py` に白キャンバス合成を実装した。
  - `white_canvas`
  - `apply_edge_alpha_gamma`
  - `composite_black_lines`
  - `composite_on_white`
- `pipeline.py` にMVP単一画像pipelineを実装した。
  - 入力読み込み
  - 線画マスク抽出
  - SDF線alpha生成
  - 白キャンバスへの黒線合成
  - 最終PNG保存
  - debugレイヤー保存
- `cli.py` の `upscale` をPhase1の同サイズ保存から、実際の2x/3x/4x最終PNG出力へ切り替えた。
- CLIに `--width-bias-source-px` と `--aa-radius-hr-px` を追加した。
- `inspect` でも `06_final.png` を保存するようにした。
- `tests/test_composite.py` と `tests/test_pipeline.py` を追加し、CLIテストをPhase4仕様へ更新した。

### 検証結果

- `python -m pytest` 成功。40件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase4\sample01_x2.png --scale 2 --preset line_only --overwrite` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase4\sample01_x3.png --scale 3 --preset line_only --overwrite` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase4\sample01_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\phase4\debug_sample01_x4` 成功。
- 出力サイズは以下。
  - 2x: 2896x2172
  - 3x: 4344x3258
  - 4x: 5792x4344
- 4x debug-dirには `00_input_gray.png` から `06_final.png` まで保存された。

### 今後同じミスをしないための有益な失敗

- `edge_alpha_gamma` は最終画像ではなくalpha側へ適用する。最終画像側にかけると白背景や線濃度全体が壊れやすい。
- `upscale` はPhase4で挙動が変わり、同サイズ保存ではなく拡大PNGを出すようになった。今後のテストやログ名にPhase1の前提を残さないよう注意する。
- MVPでは白キャンバス合成のみを行うため、グレー階調は保持されない。サンプル評価時に元画像の薄いグレー線が消える場合は、マスク抽出やline_softの設定で調整する。

## 2026-07-09 フェーズ7 run JSON保存とMVP利用README整備

### 作業内容

- `debug_layers.py` にdebug PNG保存、run JSONパス生成、run metadata構築、JSON保存を集約した。
- `pipeline.py` で出力PNG保存後に `.mlus-run.json` をsidecarとして保存するようにした。
  - `upscale output.png` では `output.mlus-run.json` を保存する。
  - `inspect` では `debug-dir/06_final.png` と `debug-dir/06_final.mlus-run.json` を保存する。
- run JSONへ入力/出力サイズ、プリセット名、ツールバージョン、倍率、実効config、mask警告、debugレイヤーパスを記録するようにした。
- `debug.save_run_json` の既定値を `true` に変更し、通常のMVP実行で証跡が残るようにした。
- CLIの実行結果表示へ `Run JSON:` 行を追加した。
- READMEをMVP実用手順中心に書き換えた。
  - Windows導入
  - `mlu doctor`
  - 2x/3x/4x実行例
  - `--invert`
  - debugレイヤー説明
  - MVP後機能とGPL系外部ツール非同梱方針
- 受け入れチェックリストを実装済み項目と未確認の画質項目に分けて更新した。
- 白紙、黒寄り、透明PNG、JPEG入力の最小pipelineテストを追加した。
- 同一入力・同一設定で最終PNG画素が一致する再現性テストを追加した。

### 検証結果

- `python -m pytest` 成功。47件通過。
- `ruff check` 成功。
- `mlu doctor` 成功。
- `mlu --help` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase7\sample01_x2.png --scale 2 --preset line_only --overwrite` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase7\sample01_x3.png --scale 3 --preset line_only --overwrite` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase7\sample01_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\phase7\debug_sample01_x4` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\phase7\sample01_invert_x2.png --scale 2 --preset line_only --invert --overwrite` 成功。
- `mlu inspect .\images\input\sample01.png --preset line_only --debug-dir .\tmp\phase7\inspect_sample01` 成功。
- 実サンプル出力サイズは以下。
  - 2x: 2896x2172
  - 3x: 4344x3258
  - 4x: 5792x4344
- sidecar run JSONには `line_only`、scale、`0.1.0`、出力サイズが保存されていることを確認した。
- `debug_sample01_x4` と `inspect_sample01` のdebugレイヤーは `00_input_gray.png` から `06_final.png` まで欠けなし。

### 今後同じミスをしないための有益な失敗

- `upscale --debug-dir` のrun JSON保存先を、debug-dir内の `06_final.mlus-run.json` と誤解しやすかった。実際の仕様は、通常出力のsidecarである `output.mlus-run.json` にdebugレイヤーパスを記録する。`inspect` だけは通常出力が `debug-dir/06_final.png` なので、sidecarもdebug-dir内に出る。
- run JSONを出すかどうかが設定だけで既定falseのままだと、MVPの再現性チェックを通常コマンドで満たせない。MVPでは `debug.save_run_json: true` を既定にして、明示的に無効化された場合だけ保存しない。
- チェックリストを先に更新すると未検証項目をチェックしがちになる。今後は、チェックを入れる前にテストかスモークコマンドで根拠を作る。

## 2026-07-09 フェーズ4.5 soft coverageによるジャギー低減

### 作業内容

- ユーザーの目視確認で、フェーズ7出力が「二値化後にニアレスト拡大したような強いジャギー」に見える問題を確認した。
- `docs/05_development_roadmap.md` にフェーズ4.5「線画再レンダリング画質改善」を追加した。
- `docs/03_algorithm_design.md` と `README.md` を更新し、MVP既定を二値SDF単独ではなく `soft_alpha_mode: blend` にする方針を記録した。
- `mask_extract.py` の `line_soft` を、元画像の暗さと `line_prob` の強調値を併用するcoverage情報として扱うようにした。
- `sdf_render.py` に `soft_alpha_mode: blend` を追加した。
  - `alpha_from_sdf * (1 - soft_gain) + line_soft_hr * soft_gain`
  - 既定は `soft_gain: 0.85`
  - 従来相当のhard SDFは `soft_alpha_mode: none` で再現できる。
- `config.py`、`config/presets/line_only.yaml`、`config/example.mlus.yaml` の既定設定を `blend` に変更した。
- CLIログに `soft=blend:0.85` のようにsoft設定を表示するようにした。
- `tests/test_mask_extract.py`、`tests/test_sdf_render.py`、`tests/test_config.py` にテストを追加した。
  - `line_soft` が元濃度と `line_prob` を反映すること。
  - `blend` がsource coverageをalphaに混ぜること。
  - 長い浅角線fixtureでsoft coverageの情報が入ること。
  - 無効なsoft設定を拒否すること。

### 検証結果

- `python -m pytest` 成功。52件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\quality_soft\sample01_blend_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\quality_soft\debug_sample01_blend_x4` 成功。
- 事前に以下も生成済み。
  - `tmp/quality_soft/sample01_blend_x2.png`
  - `tmp/quality_soft/sample01_blend_x3.png`
  - `tmp/quality_soft/sample01_blend_x4.png`
- run JSONに `sdf.soft_alpha_mode=blend`、`sdf.soft_gain=0.85` が保存されることを確認した。
- debug出力は `00_input_gray.png` から `06_final.png` まで欠けなし。
- 目視確認用比較画像を `tmp/quality_soft/sample01_visual_compare.png` に生成した。
  - 左: 入力cropを4倍表示
  - 中央: 従来相当のhard binary SDF
  - 右: 改善後のsoft coverage blend

### 今後同じミスをしないための有益な失敗

- 二値 `line_mask` からSDFを作るだけでは、SDFのエッジが滑らかでも、元の1pxグリッド上の階段形状を高解像度化してしまう。浅い斜線や長い水平線では、元画像より強いジャギーとして見える。
- `line_soft` を元濃度そのままに寄せすぎると、ジャギーは減るが線が眠くなる。元画像の暗さだけでなく `line_prob` の強調値も併用して、中心線の黒さを戻す必要がある。
- 今回の `blend` は情報損失を減らす改修であり、中心線推定や直線フィットではない。建築線をさらに滑らかにするには、別rendererとして中心線/直線/円弧フィットを検討する。
- 画質改修では、テスト通過だけで完了扱いにせず、サンプルから目視確認用の比較画像を必ず生成する。

## 2026-07-09 フェーズ4.6 建築線スタビライザー初期実装

### 作業内容

- `line_stabilizer.py` を追加し、長い直線候補を検出して高解像度alphaへ控えめにblendする処理を実装した。
  - `line_mask` / `line_soft` のsupport点をHough風に角度/rhoへ投票。
  - 候補bandをprojection gapで分割。
  - PCAで線分端点、幅、RMS誤差を推定。
  - 長さ、密度、RMS誤差で絞り込み。
  - 高解像度側に直線coverageを作り、既存alphaへ `strength` 分だけ混ぜる。
- `pipeline.py` にline stabilizerを接続した。
- `SDFRenderResult` に `line_geometry_hr` と `line_segments` を追加した。
- debug出力に、補正が発生した場合だけ `07_line_geometry_hr.png` を追加した。
- run JSONに `line_stabilizer.segment_count` を保存するようにした。
- `line_only` の既定で `line_stabilizer.enabled: true`、`strength: 0.30` にした。
- CLIに以下を追加した。
  - `--disable-line-stabilizer`
  - `--line-stabilizer-strength`
- READMEとアルゴリズム設計、ロードマップへline stabilizerの説明を追加した。
- `tests/test_line_stabilizer.py` を追加した。
  - 長い浅角線が検出されること。
  - 高解像度alphaへ幾何coverageが混ざること。
  - 無効時にalphaが変化しないこと。
  - 短線は補正対象にならないこと。
- CLI override、config validation、run JSONのテストを追加した。

### 検証結果

- `python -m pytest` 成功。59件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\line_stabilizer\sample01_stabilized_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\line_stabilizer\debug_sample01_stabilized_x4` 成功。
- `sample01_stabilized_x4.png` は `L` モード、5792x4344。
- 既定強度0.30で、line stabilizerは96本の直線候補を検出した。
- `tmp/line_stabilizer/debug_sample01_stabilized_x4/07_line_geometry_hr.png` が生成された。
- run JSONで以下を確認した。
  - `line_stabilizer.enabled=true`
  - `line_stabilizer.strength=0.3`
  - `line_stabilizer.segment_count=96`
- 目視確認用比較画像を生成した。
  - `tmp/line_stabilizer/sample01_line_stabilizer_compare_road.png`
  - `tmp/line_stabilizer/sample01_line_stabilizer_compare_building.png`

### 今後同じミスをしないための有益な失敗

- 初回実装では角度0度付近の縦線候補だけで `max_segments` を使い切り、道路や屋根などの浅い建築線まで検出が届かなかった。角度順に即採用するのではなく、全角度から候補を集め、長さとRMS誤差で後から選ぶ必要がある。
- `strength=0.55` では補正効果が見えやすくなる一方、壁面の長い縦線補正が少し目立った。既定は安全側の0.30にし、強めたい場合だけCLIで上げる。
- 現在のline stabilizerは「控えめな直線補強」であり、線分を完全に再構成するベクター化ではない。建築線のジャギー/波打ちをさらに減らすには、候補ごとの局所mask、交差点保護、線幅推定、中心線rendererを別途詰める必要がある。

## 2026-07-09 line stabilizer既定off化と実験機能化

### 作業内容

- ユーザー目視確認で、比較画像の右2つ、つまりline stabilizer有効出力は補正が効きすぎ、不適切な線の乱れがあり、左から2番目のsoft-onlyがもっとも良いと判断された。
- `line_only` の既定をsoft-onlyへ戻した。
  - `config/presets/line_only.yaml`: `line_stabilizer.enabled: false`
  - `config/example.mlus.yaml`: `line_stabilizer.enabled: false`
- line stabilizerは削除せず、明示opt-inの実験オプションとして残した。
- CLIへ `--enable-line-stabilizer` を追加した。
- `--line-stabilizer-strength` 単独では有効化せず、`--enable-line-stabilizer` と併用したときだけ実験機能が動くようにした。
- line stabilizerに高解像度support gateを追加し、元の `line_mask` / `line_soft` 近傍だけ補正するようにした。
- line stabilizerが元alphaを薄くしないよう、補正後alphaは `max(original, strengthened)` にした。
- README、アルゴリズム設計、ロードマップを「既定有効」から「実験オプション」へ修正した。
- テストを追加・更新した。
  - `line_only` 既定は `soft_alpha_mode=blend` かつ `line_stabilizer.enabled=false`。
  - 通常debugでは `07_line_geometry_hr.png` が出ない。
  - `--enable-line-stabilizer` 明示時だけ有効化される。
  - `--line-stabilizer-strength` 単独では有効化されない。
  - line stabilizer有効時でもalphaを減らさない。

### 検証結果

- `python -m pytest` 成功。62件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\line_stabilizer_recheck\sample01_default_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\line_stabilizer_recheck\debug_default_x4` 成功。
- 通常実行のrun JSONで以下を確認した。
  - `line_stabilizer.enabled=false`
  - `line_stabilizer.segment_count=0`
  - `debug_default_x4` に `07_line_geometry_hr.png` は出ない。
- 明示enable実行では以下を確認した。
  - `line_stabilizer.enabled=true`
  - `line_stabilizer.segment_count=96`
  - `debug_stabilizer_x4` に `07_line_geometry_hr.png` が出る。
- 目視確認用比較画像を生成した。
  - `tmp/line_stabilizer_recheck/sample01_default_vs_experimental_road.png`
  - `tmp/line_stabilizer_recheck/sample01_default_vs_experimental_building.png`

### 今後同じミスをしないための有益な失敗

- 画質改善アルゴリズムは、合成テストで改善しても実サンプル目視で悪化することがある。ユーザー目視でsoft-onlyのほうが良いと判断された場合は、既定採用を即座に撤回し、実験オプションへ降格する。
- `--line-stabilizer-strength` のような調整値だけで実験機能が有効化されると、意図せず品質が変わる。実験機能は `--enable-line-stabilizer` のような明示opt-inを必須にする。
- 直線補正は「線を整える」つもりでも、幾何coverageが元alphaより低い場所では線を薄くして乱れに見える。実験版では少なくとも元alphaを減らさない安全制約が必要。
- 今後line stabilizerを再検討するなら、局所mask、交差点保護、曲線/カケアミ除外、差分debug画像を先に入れてから再度目視評価する。

## 2026-07-09 line stabilizer局所support化と強め既定

### 作業内容

- ユーザー目視確認で、ジャギー抑制だけを見ると右端の強めline stabilizer出力がもっとも良好と判断された。
- 一方で、建物側比較では右端に「元画像に存在しないきわめて細い線」がやや出ていたため、強度そのものではなく余分線の発生方向を抑える方針にした。
- line stabilizerの補正範囲を、全体の `line_mask` / `line_soft` gateではなく、検出線分ごとの実支持点近傍だけに限定した。
  - `LineSegment` に `support_x` / `support_y` を追加。
  - `_blend_segment()` で線分ごとのsupport gateを生成。
  - `support_dilate_hr_px` を既定3から2へ下げた。
- line stabilizer既定を強めに戻した。
  - `enabled: true`
  - `strength: 0.55`
- CLI調整仕様を維持した。
  - `--disable-line-stabilizer`
  - `--enable-line-stabilizer`
  - `--line-stabilizer-strength`
- README、アルゴリズム設計、ロードマップを、強め既定かつ局所support限定という仕様へ更新した。
- sparseな支持点間を勝手に直線で埋めない回帰テストを追加した。

### 検証結果

- `python -m pytest` 成功。63件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\line_stabilizer_v2\sample01_default_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\line_stabilizer_v2\debug_default_x4` 成功。
- `--disable-line-stabilizer` と `--line-stabilizer-strength 0.75` のサンプル出力も生成した。
- 目視確認用比較画像を生成した。
  - `tmp/line_stabilizer_v2/sample01_stabilizer_v2_compare_road.png`
  - `tmp/line_stabilizer_v2/sample01_stabilizer_v2_compare_building.png`
- 目視では、局所support gate後の既定0.55と強め0.75で、前回問題になった余分な極細線は目立ちにくくなった。

### 今後同じミスをしないための有益な失敗

- 「強い補正」自体が悪いのではなく、補正線が本来の支持点以外へ出ることが悪化要因だった。直線補正は強度だけで評価せず、補正が描かれるsupport範囲を必ず確認する。
- グローバルsupport gateは、一見安全でも、検出線分とは別の近傍supportに幾何線を出す可能性がある。線分ごとのsupport gateを使う。
- 強度は素材や好みに依存するため、既定は強めにしても、CLIと設定ファイルで必ず調整できるようにする。

## 2026-07-09 line stabilizer不採用と高解像soft SDF実装

### 作業内容

- ユーザー目視確認で、局所support制限後もline stabilizerに「元画像に存在しない極細線」が出る現象が残り、実用上は破棄すべき品質と判断された。
- line stabilizerはMVP既定から外し、明示opt-inの実験機能へ戻した。
  - `config.py`: `line_stabilizer.enabled=false`
  - `config/presets/line_only.yaml`: `line_stabilizer.enabled=false`
  - `config/example.mlus.yaml`: `line_stabilizer.enabled=false`
- `docs/05_development_roadmap.md` にフェーズ4.7「高解像soft SDFによるジャギー低減」を追加した。
- `sdf_render.py` に `sdf.distance_source` を追加した。
  - `binary_mask`: 従来通りsource解像度の `line_mask` からSDFを作り、HR化後に `* scale` する。
  - `soft_mask_hr`: `line_soft` を先に高解像度化し、`soft_sdf_threshold` でsupport化してからHR上でSDFを作る。
  - `soft_mask_hr` は最初からHRピクセル単位の距離場なので、距離値へ `scale` を掛けない。
- `line_only` 既定を `distance_source: soft_mask_hr`、`soft_sdf_threshold: 0.30` にした。
- CLIに以下を追加した。
  - `--sdf-distance-source binary_mask|soft_mask_hr`
  - `--soft-sdf-threshold`
- README、アルゴリズム設計、CLI仕様、最小実用アルゴリズム仕様を更新した。
- テストを追加・更新した。
  - `soft_mask_hr` は `line_soft` が必須。
  - `line_soft` のsupportがない場合、binary maskだけでは線を生成しない。
  - HR上でSDFが作られていること。
  - 無効な `distance_source` / `soft_sdf_threshold` を拒否すること。
  - `--line-stabilizer-strength` 単独では実験機能を有効化しないこと。

### 検証結果

- `python -m pytest` 成功。69件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\soft_sdf\sample01_soft_sdf_x4.png --scale 4 --preset line_only --overwrite --debug-dir .\tmp\soft_sdf\debug_sample01_soft_sdf_x4` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\soft_sdf\sample01_binary_sdf_x4.png --scale 4 --preset line_only --sdf-distance-source binary_mask --disable-line-stabilizer --overwrite --debug-dir .\tmp\soft_sdf\debug_sample01_binary_sdf_x4` 成功。
- run JSONで以下を確認した。
  - soft SDF出力: `sdf.distance_source=soft_mask_hr`
  - binary比較出力: `sdf.distance_source=binary_mask`
  - どちらも `line_stabilizer.enabled=false`
  - どちらも `line_stabilizer.segment_count=0`
- 目視確認用比較画像を生成した。
  - `tmp/soft_sdf/sample01_soft_sdf_compare_road.png`
  - `tmp/soft_sdf/sample01_soft_sdf_compare_building.png`

### 今後同じミスをしないための有益な失敗

- 幾何的に直線を描き足す補正は、ジャギー低減だけを見ると良く見えても、元画像にない極細線を少しでも生成すると実用上の致命的な破綻になる。MVP既定では採用しない。
- support gateを入れても、検出・描画のどちらかが外すと偽線が残る。偽線を避ける目的では、まず「新規の幾何coverageを作らない」方式を優先する。
- source解像度の二値maskからSDFを作ると、二値化グリッドの階段が残りやすい。`line_soft` をHR化してから距離場を作る方が、元画像のアンチエイリアス情報を活かしやすい。
- 今後さらに改善する場合は、`soft_supersample`、`support_clamp`、`support_gated_edge_smoothing` の順に、小さな比較画像と「偽細線が増えない」テストを先に用意してから進める。

## 2026-07-09 フェーズ5 tone_source生成

### 作業内容

- `tone_source.py` にsource解像度の階調素材生成を実装した。
  - `white_canvas`: 純線画MVP用に白一色を返す。
  - `passthrough`: 入力グレーをそのまま返す。
  - `lift_lines`: `line_mask` 近傍を白側へ持ち上げ、後続の階調upscalerに渡す線除去素材を作る。
- `lift_lines` では以下を実装した。
  - Euclidean距離による `line_mask` 膨張。
  - 線領域を白で埋めた画像からGaussian blurで背景推定。
  - `lift_strength` による白方向リフト。
  - `protect_midtones` による中間階調の過剰な白飛び抑制。
  - 背景midtone比率による簡易純線画判定。
- `config.py` に `tone_source` 設定validationを追加した。
  - `mode`
  - `dilate_radius`
  - `lift_strength`
  - `background_blur_radius`
  - `protect_midtones`
- `pipeline.py` で `generate_tone_source()` を呼び出し、run JSONに以下を保存するようにした。
  - `tone_source.mode`
  - `tone_source.is_likely_pure_lineart`
  - `tone_source.line_lift_ratio`
  - `tone_source.midtone_ratio`
- `debug_layers.py` で `tone_source.mode != white_canvas` のとき `07_tone_source.png` を保存するようにした。
- README、アルゴリズム設計、CLI仕様、ロードマップを更新した。
- `tests/test_tone_source.py` を追加し、pipeline/configテストも更新した。

### 検証結果

- `python -m pytest` 成功。79件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\tone_source\sample01_gray_tone_x4.png --scale 4 --preset gray_tone --overwrite --debug-dir .\tmp\tone_source\debug_sample01_gray_tone_x4` 成功。
- debug出力に `07_tone_source.png` が生成された。
- run JSONで以下を確認した。
  - `tone_source.mode=lift_lines`
  - `tone_source.is_likely_pure_lineart=true`
  - `tone_source.line_lift_ratio=0.5084064602851868`
  - `tone_source.midtone_ratio=0.001284220203484928`
- 目視確認用比較画像を生成した。
  - `tmp/tone_source/sample01_tone_source_compare_road.png`
  - `tmp/tone_source/sample01_tone_source_compare_building.png`

### 今後同じミスをしないための有益な失敗

- `tone_source` は最終線画ではなく、後続upscalerへ渡す階調素材である。ここで線を完全に消そうとして背景まで白飛びさせると、階調ブランチの情報が失われる。
- `dilate_radius` を整数のbinary dilationだけで扱うと、`1.2` のような設定値の差が見えにくい。距離変換で半径を扱う方が、設定の意味が明確になる。
- Real-CUGAN/waifu2x連携は未実装なので、フェーズ5では `tone_source` の生成とdebug確認までに境界を切る。`tone_source` を高解像度化して最終合成で二重線が減るかはフェーズ6で検証する。

## 2026-07-09 フェーズ6 外部アップスケーラー連携

### 作業内容

- `upscaler_external.py` に階調ブランチ用adapterを実装した。
  - `none`: 従来どおり白キャンバスを返す。
  - `lanczos`: 内部Lanczosで `tone_source` を高解像度化する。
  - `realcugan`: Real-CUGAN ncnn Vulkan想定コマンドを生成・実行する。
  - `waifu2x`: waifu2x ncnn Vulkan想定コマンドを生成・実行する。
  - `realesrgan`: Real-ESRGAN ncnn Vulkan想定コマンドを生成・実行する。
- 外部upscaler実行では以下を実装した。
  - 外部バイナリ存在確認。
  - `tempfile.TemporaryDirectory` への一時入力PNG保存。
  - `subprocess.run(..., capture_output=True, text=True)` による配列形式コマンド実行。
  - return code、stdout、stderr、commandの記録。
  - 出力画像サイズ検証。
  - 外部ツール未設定・失敗時の `fallback: lanczos`。
- Lanczos fallbackではPillow Lanczosのオーバーシュートを `[0,1]` へclampするようにした。
- `pipeline.py` を `tone_source -> tone_hr -> composite_black_lines` の流れに接続した。
  - `line_only` は `upscaler=none` のため白キャンバス合成のまま。
  - `gray_tone` / `conservative` は外部またはfallbackで `tone_hr` を作って合成する。
- `debug_layers.py` で `upscaler.engine != none` のとき `08_tone_hr.png` を保存するようにした。
- run JSONに `upscaler` 情報を保存するようにした。
  - `requested_engine`
  - `engine`
  - `used_fallback`
  - `command`
  - `returncode`
  - `stdout`
  - `stderr`
  - `error`
- CLIに以下を追加した。
  - `--upscaler`
  - `--upscaler-fallback`
- `doctor --config` でReal-CUGAN、waifu2x、Real-ESRGANの設定/PATH解決状況を表示するようにした。
- `config.py` にupscaler/external_tools validationを追加した。
- README、CLI仕様、アーキテクチャ、依存関係、ロードマップ、品質ドキュメントを更新した。
- `tests/test_upscaler_external.py` を追加し、pipeline/config/CLIテストも更新した。

### 検証結果

- `python -m pytest` 成功。95件通過。
- `ruff check` 成功。
- `mlu doctor --config .\config\example.mlus.yaml` 成功。
  - この環境ではReal-CUGAN、waifu2x、Real-ESRGANはいずれも未設定かつPATH上に存在しない。
- `mlu upscale .\images\input\sample01.png -o .\tmp\upscaler_external\sample01_gray_tone_lanczos_fallback_x4.png --scale 4 --preset gray_tone --overwrite --debug-dir .\tmp\upscaler_external\debug_sample01_gray_tone_lanczos_fallback_x4` 成功。
- 上記サンプルではReal-CUGAN未設定からLanczos fallbackへ落ちた。
- debug出力に `07_tone_source.png` と `08_tone_hr.png` が生成された。
- run JSONで以下を確認した。
  - `upscaler.requested_engine=realcugan`
  - `upscaler.engine=lanczos`
  - `upscaler.used_fallback=true`
  - `upscaler.error=realcugan executable is not configured and was not found on PATH.`
- 目視確認用比較画像を生成した。
  - `tmp/upscaler_external/sample01_upscaler_external_compare_road.png`
  - `tmp/upscaler_external/sample01_upscaler_external_compare_building.png`

### 今後同じミスをしないための有益な失敗

- Lanczosでfloat画像を拡大すると、補間オーバーシュートで0未満や1超過が発生する。tone_hrとして合成へ渡す前に必ずclampする。
- 外部CLI連携は実バイナリがない環境でも、コマンド構築、未設定時fallback、失敗時stderr記録をmockで検証できる。実バイナリの品質確認とは分けて扱う。
- `line_only` の白キャンバス合成を壊さないため、`upscaler=none` はtone_sourceを使わず白キャンバスを返す仕様にした。階調を使いたい場合は `lanczos` または外部upscalerを明示する。

## 2026-07-09 tone_hr自動合成制御

### 作業内容

- ユーザー目視確認で、`gray_tone` の `final` に薄い `tone_hr` が重なってもジャギー改善に寄与せず、グレー残渣として品質を下げることが確認された。
- `tone_hr` はジャギー改善用ではなく、グレー階調保持用の下地として扱う方針に整理した。
- `composite.tone_usage` を追加した。
  - `auto`: 純線画に見える場合は `tone_hr` を最終合成に使わず、白キャンバスへ戻す。
  - `always`: 比較や階調素材検証のため、常に `tone_hr` を下地に使う。
  - `never`: upscaler設定に関係なく白キャンバスへ戻す。
- `pipeline.py` に `decide_tone_usage()` を追加し、`tone_source_result.is_likely_pure_lineart` を使ってauto判定するようにした。
- 純線画判定でtone合成をスキップする場合、upscaler実行自体もスキップし、白キャンバスの `UpscalerResult` を作るようにした。
- run JSONに `tone_composite` を追加した。
  - `tone_usage`
  - `used_tone_hr`
  - `skip_reason`
- CLIに `--tone-usage auto|always|never` を追加した。
- README、CLI仕様、アルゴリズム設計、ロードマップを更新した。
- 回帰テストを追加した。
  - 純線画 + `tone_usage=auto` では `tone_hr` を使わず、白キャンバス合成結果と一致する。
  - 純線画 + `tone_usage=always` では `tone_hr` を使う。
  - 中間階調を含む入力では `tone_usage=auto` でもtone branchを使う。
  - CLIから `--tone-usage` を上書きできる。

### 検証結果

- `python -m pytest` 成功。99件通過。
- `ruff check` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\tone_usage_auto\sample01_gray_tone_auto_x4.png --scale 4 --preset gray_tone --overwrite --debug-dir .\tmp\tone_usage_auto\debug_sample01_gray_tone_auto_x4` 成功。
  - `tone_composite.used_tone_hr=false`
  - `tone_composite.skip_reason=input looks like pure line art`
  - `upscaler.engine=none`
  - `08_tone_hr.png` は出ない。
- `mlu upscale .\images\input\sample01.png -o .\tmp\tone_usage_auto\sample01_gray_tone_always_x4.png --scale 4 --preset gray_tone --tone-usage always --overwrite --debug-dir .\tmp\tone_usage_auto\debug_sample01_gray_tone_always_x4` 成功。
  - `tone_composite.used_tone_hr=true`
  - Real-CUGAN未設定からLanczos fallback。
  - `08_tone_hr.png` が出る。
- 目視確認用比較画像を生成した。
  - `tmp/tone_usage_auto/sample01_tone_usage_compare_road.png`
  - `tmp/tone_usage_auto/sample01_tone_usage_compare_building.png`

### 今後同じミスをしないための有益な失敗

- `tone_hr` を「線のジャギーを薄いグレーで補う」目的に使うと、SDF線の下に残渣が入り、漫画線画としての品質を下げる。ジャギー改善は線alpha側で行い、tone branchは階調保持目的に限定する。
- 純線画サンプルで `gray_tone` を試す場合、最終合成だけを見るとtone branchが悪化要因に見える。debugの `tone_source` は確認用として残しても、最終合成ではauto skipする。
- 比較用に悪化ケースを再現できる `tone_usage=always` を残しておくと、今後の改善差分を確認しやすい。

## 2026-07-09 線幅太り半減プレビュー

### 作業内容

- ユーザー目視確認で、アップスケール後の線の太り方がやや過剰と判断された。
- 採用前の比較として、既定設定は変更せず、`gray_tone` の `sdf.width_bias_source_px` だけを調整したプレビューを生成した。
- 「太り具合を半減」は、入力の `line_soft` に対する出力線alphaの増加分を約半分にする意味で扱った。
- `sample01` では、現在の `gray_tone` 設定 `width_bias_source_px=-0.05` に対し、`width_bias_source_px=-0.25` が増加分の半減に最も近かった。

### 検証結果

- `mlu upscale .\images\input\sample01.png -o .\tmp\line_width_half\sample01_current_x4.png --scale 4 --preset gray_tone --overwrite --debug-dir .\tmp\line_width_half\debug_sample01_current_x4` 成功。
- `mlu upscale .\images\input\sample01.png -o .\tmp\line_width_half\sample01_half_growth_x4.png --scale 4 --preset gray_tone --width-bias-source-px -0.25 --overwrite --debug-dir .\tmp\line_width_half\debug_sample01_half_growth_x4` 成功。
- 目視確認用比較画像を生成した。
  - `tmp/line_width_half/sample01_width_half_compare_road_right.png`
  - `tmp/line_width_half/sample01_width_half_compare_building_center.png`
  - `tmp/line_width_half/sample01_width_half_compare_thin_wires.png`

### 今後同じミスをしないための有益な失敗

- 全サンプルに対して複数の `width_bias_source_px` 候補を一括測定すると、HR SDFの距離変換が重くタイムアウトしやすい。まず代表サンプルまたは切り出しで候補を絞ってからフルサイズ生成する。
- 線幅調整は採用前に既定プリセットへ入れない。目視確認用の出力として生成し、細線欠けや建築線の破綻がないことを確認してから採用する。

## 2026-07-09 線幅太り半減設定の採用

### 作業内容

- ユーザー目視確認で、`width_bias_source_px=-0.25` の低減版の方が現在版より良いと判断された。
- `config/presets/gray_tone.yaml` の既定 `sdf.width_bias_source_px` を `-0.05` から `-0.25` へ変更した。
- `tests/test_config.py` に `gray_tone` プリセットの採用値を確認するテストを追加した。
- README、アルゴリズム設計、開発ログ上で線幅調整の扱いを更新した。

### 検証結果

- `python -m pytest tests\test_batch.py tests\test_config.py` 成功。24件通過。

### 今後同じミスをしないための有益な失敗

- 目視で採用した画質パラメータは、プリセット値だけでなくテストにも固定しておく。後続の設定整理で意図せず以前の太い値へ戻ることを防げる。

## 2026-07-09 フェーズ8：バッチ処理

### 作業内容

- `src/mlu/batch.py` を追加した。
  - 入力ディレクトリを再帰探索する。
  - 既定対象拡張子は `png,jpg,jpeg,tif,tiff`。
  - 相対ディレクトリを保ち、`stem_x{scale}.png` を出力する。
  - 1ファイル失敗しても残りを継続する。
  - `summary.json` と `summary.csv` を保存する。
- `mlu batch input_dir output_dir` をCLIに追加した。
  - `--scale`
  - `--preset`
  - `--config`
  - `--extensions`
  - `--workers`
  - `--debug-dir`
  - `--summary-json`
  - `--summary-csv`
  - 単一画像処理と同じ主要な画質・upscaler上書きオプション
- 現時点の `--workers` は `1` のみ対応とし、逐次処理を既定にした。
- summaryには、成功/失敗、入出力パス、run JSON、debug dir、入出力サイズ、警告、mask面積率、tone合成有無、upscaler概要を記録する。
- README、CLI仕様、アーキテクチャ、ロードマップ、受け入れチェックリストを更新した。
- `tests/test_batch.py` を追加した。
  - 拡張子parse
  - 再帰探索
  - 出力/debugパス生成
  - 成功時summary JSON/CSV
  - 失敗ファイルを含む場合の継続処理

### 検証結果

- `python -m pytest` 成功。105件通過。
- `ruff check` 成功。
- `mlu batch .\images\input .\tmp\batch_phase8 --scale 2 --preset line_only --overwrite --summary-json .\tmp\batch_phase8\summary.json --summary-csv .\tmp\batch_phase8\summary.csv` 成功。
  - 6件中6件成功、0件失敗。
  - `tmp/batch_phase8/summary.json` と `tmp/batch_phase8/summary.csv` を生成。
  - `sample01_x2.png` から `sample06_x2.png` まで生成。

### 今後同じミスをしないための有益な失敗

- バッチ処理で例外を握って継続する場合も、summary自体の保存は最後に必ず行う。失敗ファイルがある時こそ、どこまで処理できたかの証跡が必要になる。
- 並列処理は便利だが、最初から入れると外部upscalerやdebug出力の競合要因が増える。フェーズ8では `workers=1` の逐次処理に限定し、品質と再現性を先に固定する。

## 2026-07-09 フェーズ9：品質比較支援

### 作業内容

- `src/mlu/compare.py` を追加した。
  - YAMLグリッドを読み込む。
  - `parameters` の直積をvariantへ展開する。
  - `variants` の明示列挙にも対応する。
  - 任意の `base` mappingを各variantへ共通適用できる。
  - variant適用後に `validate_config()` で設定を再検証する。
  - variantごとに `upscale_image()` を実行する。
  - `contact_sheet.png`、`center_crop_1x.png`、`center_crop_200pct.png` を生成する。
  - `compare-summary.json` を保存する。
- CLIに `mlu compare` を追加した。
  - `-o, --output-dir`
  - `--grid`
  - `--thumbnail-width`
  - `--crop-source-size`
  - 単一画像処理と同じ主要な画質・upscaler上書きオプション
- サンプルグリッド `config/grids/line_width.yaml` を追加した。
- `tests/test_compare.py` を追加した。
  - ドットパスからネストしたoverrideを作る。
  - `parameters` グリッドを展開する。
  - `compare` コマンドがvariant出力、比較シート、summaryを生成する。
- README、CLI仕様、アーキテクチャ、ロードマップ、受け入れチェックリストを更新した。

### 検証結果

- `python -m pytest tests\test_compare.py` 成功。3件通過。
- `ruff check src\mlu\compare.py src\mlu\cli.py tests\test_compare.py` 成功。
- `mlu compare .\images\input\sample01.png -o .\tmp\compare_phase9 --scale 2 --preset line_only --grid .\config\grids\line_width.yaml --crop-source-size 160 --thumbnail-width 360 --overwrite` 成功。
  - 3 variantsを生成。
  - `tmp/compare_phase9/contact_sheet.png` を生成。
  - `tmp/compare_phase9/center_crop_1x.png` を生成。
  - `tmp/compare_phase9/center_crop_200pct.png` を生成。
  - `tmp/compare_phase9/compare-summary.json` を生成。

### 今後同じミスをしないための有益な失敗

- フル解像度出力を横に並べた等倍シートは、漫画背景のサイズでは巨大になりすぎる。品質確認用の等倍/200%は中央cropを標準にし、全体像はサムネイルcontact sheetで確認する。
- サンプルグリッドに `pipeline.scale` を入れると、CLIの `--scale` と衝突しやすい。標準グリッドは比較したいパラメータだけに絞り、共通設定を入れたい場合だけ `base` を使う。

## 2026-07-09 フェーズ10：Potraceオプション

### 作業内容

- `src/mlu/potrace_render.py` を追加した。
  - `line_mask` をPBMとして書き出す。
  - Potrace CLIでSVGを生成する。
  - CairoSVGまたはInkscape CLIで目標サイズPNGへラスタライズする。
  - ラスタライズPNGを `line_alpha_hr = 1.0 - grayscale` として読み込む。
  - Potrace/CairoSVG/Inkscapeの未設定時はSDF fallbackせず明確なエラーを出す。
  - Potraceコマンドとrasterizerコマンドをrun JSONへ記録する。
- `pipeline.line_renderer: sdf|potrace` を正式にvalidationするようにした。
- CLIに `--line-renderer sdf|potrace` を追加した。
  - `upscale`
  - `inspect`
  - `batch`
  - `compare`
- `potrace` 設定を追加した。
  - `turdsize`
  - `alphamax`
  - `opttolerance`
  - `opticurve`
  - `turnpolicy`
  - `rasterizer`
- `external_tools.inkscape` を追加し、`doctor` でPotrace/CairoSVG/Inkscapeも確認するようにした。
- Potraceレンダラー時のdebug出力を追加した。
  - `04_potrace.svg`
  - `05_line_alpha_hr.png`
  - `07_sdf_reference_line_alpha_hr.png`
- `line_stabilizer` はSDF向けのため、Potraceレンダラーと同時に有効化された場合は設定エラーにした。
- `tests/test_potrace_render.py` を追加した。
  - PBM書き出し
  - Potraceコマンド構築
  - 偽Potrace/CairoSVG CLIによる成功系
  - pipeline/CLI経由のdebug SVGとrun JSON確認
  - Potrace未設定時の明確なエラー
- README、CLI仕様、アーキテクチャ、アルゴリズム設計、ロードマップ、受け入れチェックリストを更新した。

### 検証結果

- `python -m pytest` 成功。116件通過。
- `ruff check` 成功。
- `mlu doctor --config .\config\example.mlus.yaml` 成功。
  - この環境ではPotrace/CairoSVG/Inkscapeはいずれも未設定かつPATH上に存在しない。
- `mlu upscale .\images\input\sample01.png -o .\tmp\potrace_missing\sample01.png --scale 2 --preset line_only --line-renderer potrace --overwrite` は想定どおり失敗。
  - `potrace executable is not configured and was not found on PATH (potrace, potrace.exe).`

### 今後同じミスをしないための有益な失敗

- Potraceは外部GPLツールであり、未設定時にSDFへ自動fallbackすると「Potraceで確認したつもり」の誤判定が起きる。任意機能ではあるが、指定された場合は未設定を明確なエラーにする。
- Potrace時にもSDF比較用レイヤーを出しておくと、ベクター化で線が丸まりすぎたか、SDF由来のジャギーが残っているかを切り分けやすい。
- `line_stabilizer` はSDF alphaを前提にした実験機能なので、Potrace alphaへ重ねると評価対象が混ざる。Potrace選択時は同時利用を拒否する。

## 2026-07-09 フェーズ11：ドキュメント整備

### 作業内容

- READMEを非エンジニアでもMVPを試せる導線へ更新した。
  - Windows上の仮想環境作成
  - `mlu` が見つからない場合の `python -m mlu` fallback
  - PowerShell実行ポリシーの注意
  - 出力先自動作成と `--overwrite` の挙動
  - 比較画像の読み方
  - `doctor` の外部ツール表示の見方
  - Real-CUGAN導入手順
  - よくある失敗例
  - 外部ツール、モデルファイルのライセンス注意
- サンプル比較画像を `docs/assets/` に保存し、READMEから参照した。
  - `sample_compare_line_width_contact_sheet.png`
  - `sample_compare_line_width_center_200pct.png`
- `docs/07_dependency_and_packaging.md` を現在の依存関係、外部ツール、任意依存に合わせて更新した。
- `docs/02_architecture.md`、`docs/03_algorithm_design.md`、`docs/04_cli_and_config_spec.md` の古いMVP後表現を、実装済み機能の現状に合わせて更新した。
- `docs/05_development_roadmap.md` のフェーズ11タスクを完了扱いにし、READMEとチェックリストの現状を記録した。
- `checklists/acceptance_checklist.md` を更新し、実装済みの外部コマンド記録と、ユーザー環境依存のReal-CUGAN実バイナリ品質確認を分離した。

### 検証結果

- `python -m pytest` 成功。116件通過。
- `ruff check` 成功。
- `mlu doctor --config .\config\example.mlus.yaml` 成功。
  - この環境ではReal-CUGAN、waifu2x、Real-ESRGAN、Potrace、CairoSVG、Inkscapeはいずれも未設定かつPATH上に存在しない。
- フェーズ11の未完了チェック項目は0件。
- README参照用サンプル比較画像2件が存在することを確認した。

### 今後同じミスをしないための有益な失敗

- READMEを大きく更新した後は、古い文脈を前提にしたパッチが失敗しやすい。追記前に狭い行範囲で現状を確認してから差分を当てる。
- 「外部アップスケーラー連携が実装済み」と「Real-CUGAN実バイナリ環境で品質確認済み」は別の状態として扱う。チェックリストで分離しないと、実装検証とユーザー環境依存の品質検証が混ざる。
- READMEの導入手順は、成功系コマンドだけでは不十分。`mlu` が見つからない、PowerShellでvenvを有効化できない、外部ツールがPATHにない、といった最初に詰まりやすい点も同じ場所に書く。

## 2026-07-09 フェーズ12：斜め線ジャギー低減

### 作業内容

- `directional_smoothing` を追加した。
  - SDF後の `line_alpha_hr` に対して、水平・垂直から離れた局所方向だけを線の進行方向へ平滑化する。
  - 旧 `line_stabilizer` のように直線coverageを新規描画しない。
  - 既存alpha近傍のsupport gate、局所方向のconfidence gate、`max_delta` による変更量制限を入れた。
  - Potraceレンダラーでは適用しない。
- `line_only` 既定で `directional_smoothing.enabled=true`、`strength=0.55`、`radius_hr_px=2` にした。
- CLIオプションを追加した。
  - `--enable-directional-smoothing`
  - `--disable-directional-smoothing`
  - `--directional-smoothing-strength`
  - `--directional-smoothing-radius-hr-px`
  - `--directional-smoothing-min-angle-from-axis-degrees`
- run JSONに `directional_smoothing` の適用状況、変更率、平均差分、最大差分を保存するようにした。
- debug出力を追加した。
  - `*_directional_smoothing_source_alpha_hr.png`
  - `*_directional_smoothing_weight_hr.png`
  - `*_directional_smoothing_delta_hr.png`
- 比較グリッドを追加した。
  - `config/grids/directional_smoothing.yaml`
  - off/default/strong/wideを比較する。
- README、アルゴリズム設計、CLI/config仕様、ロードマップ、受け入れチェックリストを更新した。
- 目視確認用画像を生成し、READMEから参照できるようにした。
  - `tmp/directional_smoothing_phase12/sample01/contact_sheet.png`
  - `tmp/directional_smoothing_phase12/sample01/center_crop_200pct.png`
  - `docs/assets/sample_compare_directional_smoothing_contact_sheet.png`
  - `docs/assets/sample_compare_directional_smoothing_center_200pct.png`

### 検証結果

- `python -m pytest` 成功。124件通過。
- `ruff check` 成功。
- `mlu doctor --config .\config\example.mlus.yaml` 成功。
  - この環境ではReal-CUGAN、waifu2x、Real-ESRGAN、Potrace、CairoSVG、Inkscapeはいずれも未設定かつPATH上に存在しない。
- `mlu compare .\images\input\sample01.png -o .\tmp\directional_smoothing_phase12\sample01 --scale 4 --preset line_only --grid .\config\grids\directional_smoothing.yaml --crop-source-size 192 --thumbnail-width 360 --overwrite` で比較画像を生成した。
  - 初回のツール呼び出しは120秒でタイムアウトしたが、残っていた処理は完了し、4variantと比較画像は生成された。
- フェーズ12の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- フルサイズの4x SDFを4variant比較すると、代表サンプル1枚でも120秒を超えることがある。目視比較を頻繁に回す場合は、入力を切り出した小画像、variant数の削減、またはtimeout延長を先に決める。
- ジャギー低減を目的にしても、新しい直線coverageを足す方式は元画像にない極細線を出す危険が高い。今回のように既存alphaだけを変形する処理でも、debugで補正前alpha、重み、差分を必ず出して副作用を確認する。
- 水平・垂直線を対象外にするだけでは、端点や交差部では局所方向が斜めに推定されることがある。水平・垂直線への副作用は平均差分だけでなく、端点・交差部の目視確認も必要。

## 2026-07-09 フェーズ13：浅角度線の波打ち抑制

### 作業内容

- ユーザー目視確認で、`directional_smoothing` により浅角度の屋根線へ元画像にない大きな周期の波打ちが出る問題を確認した。
- `directional_smoothing` の候補角量子化を廃止した。
  - 旧方式は15度刻みの候補角から近い方向を選んでいた。
  - 新方式は構造テンソルで推定した局所接線角そのものに沿って `map_coordinates` でサンプリングする。
- 浅角度線へのgateを連続重み化した。
  - `min_angle_from_axis_degrees` 未満では無効。
  - `full_strength_angle_from_axis_degrees` まで線形に強度を上げる。
- 既定値を浅角度線保護側へ変更した。
  - `min_angle_from_axis_degrees: 20.0`
  - `full_strength_angle_from_axis_degrees: 34.0`
- CLIオプションを追加した。
  - `--directional-smoothing-full-strength-angle-from-axis-degrees`
- `directional_smoothing` のrun JSON統計に `sampling_mode: local_angle` と `active_weight_ratio` を追加した。
- `config/grids/directional_smoothing.yaml` を更新した。
  - `smoothing_off`
  - `smoothing_default`
  - `smoothing_strong`
  - `smoothing_diagonal_only`
- 屋根線付近の比較用に `sample01` から切り出しを作り、比較画像を生成した。
  - `tmp/directional_smoothing_phase13/sample01_roof_crop.png`
  - `tmp/directional_smoothing_phase13/roof_compare/contact_sheet.png`
  - `tmp/directional_smoothing_phase13/roof_compare/center_crop_200pct.png`
- README用assetsを更新した。
  - `docs/assets/sample_compare_directional_smoothing_contact_sheet.png`
  - `docs/assets/sample_compare_directional_smoothing_center_200pct.png`
- README、アルゴリズム設計、CLI/config仕様、ロードマップ、受け入れチェックリストを更新した。

### 検証結果

- 対象テスト実行：
  - `python -m pytest tests/test_directional_smoothing.py tests/test_config.py tests/test_cli_phase1.py tests/test_pipeline.py` 成功。50件通過。
  - `ruff check src\mlu\directional_smoothing.py src\mlu\config.py src\mlu\cli.py tests\test_directional_smoothing.py tests\test_config.py tests\test_cli_phase1.py` 成功。
- `mlu compare .\tmp\directional_smoothing_phase13\sample01_roof_crop.png -o .\tmp\directional_smoothing_phase13\roof_compare --scale 4 --preset line_only --grid .\config\grids\directional_smoothing.yaml --crop-source-size 220 --thumbnail-width 360 --overwrite` 成功。
- フェーズ13の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- 角度候補へ量子化すると、浅い線が実際より大きい角度へ引っ張られ、屋根線や電線に大きな周期の波打ちが出ることがある。方向性処理は候補角に丸めず、局所推定角を直接使う方が安全。
- 水平・垂直からの角度gateを二値判定にすると、線上の推定角の揺れが処理ムラになる。浅角度線は連続重みで弱める。
- ジャギー改善の目視比較では、急な斜線だけでなく、水平に近い長い建築線と電線を必ず別枠で確認する。

## 2026-07-09 Pro拡張レビュー用ZIP作成

### 作業内容

- ユーザー目視確認で、フェーズ13後も浅角度線の大きな波打ちが十分に改善していないと判断された。
- 別AIレビュー向けに、必要材料を `tmp/pro_review_package_20260709_wave_review/` へ集約した。
- `REVIEW_BRIEF.md` を作成し、問題概要、再現コマンド、現行アルゴリズム、既知の失敗、レビュー観点を整理した。
- ユーザー提示画像を同梱した。
  - `evidence/user_report/user_simple_upscale_reference.png`
  - `evidence/user_report/user_mlu_output_wave_artifact.png`
- フェーズ13の屋根線比較画像とvariant出力を同梱した。
  - `evidence/phase13_roof_compare/`
- レビューに必要なコード、設定、テスト、主要docsを同梱した。
  - `code/src/`
  - `code/tests/`
  - `code/config/`
  - `docs_snapshot/`
- `__pycache__` と `*.egg-info` はレビューの邪魔になるため除外してZIPを作り直した。

### 成果物

- `tmp/pro_review_package_20260709_wave_review.zip`
  - サイズは約4.0MB。
  - `REVIEW_BRIEF.md`、ユーザー提示画像、比較画像、関連コード、設定、テスト、docs、`MANIFEST.txt` を含む。

### 今後同じミスをしないための有益な失敗

- 外部レビュー用パッケージでは、実行キャッシュやビルド生成物を含めるとノイズになる。ZIP化前に `__pycache__`、`*.egg-info`、巨大なtmp全体を除外する。
- 画像品質レビューでは、コードだけでなく、ユーザーが実際に問題と判断したbefore/after画像を同梱する必要がある。

## 2026-07-09 フェーズ14：line_soft起点の波打ち抑制

### 作業内容

- Pro拡張レビュー結果をリポジトリ内に保管した。
  - 原本: `reviews/wave_artifact_review_for_codex/original/wave_artifact_review_for_codex.zip`
  - 展開物: `reviews/wave_artifact_review_for_codex/extracted/wave_artifact_review_for_codex/`
- レビューの主指摘どおり、波打ちの主因を `directional_smoothing` だけでなく `line_soft` 生成とsoft SDF support化にあるものとして扱った。
- `mask.soft_coverage.mode` / `gamma` を追加した。
  - 既定は `darkness`。
  - 旧挙動は `max_probability`。
  - 診断用に `line_probability` も選べる。
- `line_only` 既定を浅角度線保護側へ変更した。
  - `soft_sdf_threshold: 0.22`
  - `soft_alpha_mode: none`
  - `soft_gain: 0.0`
  - `directional_smoothing.enabled: false`
- CLIで `--line-soft-coverage-mode` と `--line-soft-coverage-gamma` を指定できるようにした。
- SDF debugとrun JSONに診断情報を追加した。
  - `NN_line_soft_hr.png`
  - `NN_soft_mask_hr.png`
  - `NN_sdf_alpha_before_soft_mode_hr.png`
  - `sdf_diagnostics`
- 浅角度線の波打ち調査用グリッドを追加した。
  - `config/grids/wave_investigation.yaml`
- 屋根線付近の目視比較画像を生成し、README用assetsへ保存した。
  - `tmp/wave_soft_coverage_phase14/roof_compare/contact_sheet.png`
  - `tmp/wave_soft_coverage_phase14/roof_compare/center_crop_200pct.png`
  - `docs/assets/sample_compare_wave_soft_coverage_contact_sheet.png`
  - `docs/assets/sample_compare_wave_soft_coverage_center_200pct.png`
- README、アルゴリズム設計、CLI/config仕様、最小実用アルゴリズム仕様、ロードマップ、受け入れチェックリストを更新した。
- 展開したレビュー草案は外部資料として編集しない方針にし、`pyproject.toml` で `reviews/` をruff対象から除外した。

### 検証結果

- 対象テスト実行:
  - `python -m pytest tests/test_mask_extract.py tests/test_config.py tests/test_cli_phase1.py tests/test_pipeline.py tests/test_wave_artifact_guard.py` 成功。59件通過。
  - `ruff check src\mlu\mask_extract.py src\mlu\config.py src\mlu\cli.py src\mlu\sdf_render.py src\mlu\debug_layers.py src\mlu\pipeline.py tests\test_mask_extract.py tests\test_config.py tests\test_cli_phase1.py tests\test_pipeline.py tests\test_wave_artifact_guard.py` 成功。
- 全体検証:
  - `python -m pytest` 成功。130件通過。
  - `ruff check` 成功。
  - `mlu doctor --config .\config\example.mlus.yaml` 成功。
    - この環境ではReal-CUGAN、waifu2x、Real-ESRGAN、Potrace、CairoSVG、Inkscapeはいずれも未設定かつPATH上に存在しない。
- `mlu compare .\tmp\directional_smoothing_phase13\sample01_roof_crop.png -o .\tmp\wave_soft_coverage_phase14\roof_compare --scale 4 --preset line_only --grid .\config\grids\wave_investigation.yaml --crop-source-size 220 --thumbnail-width 320 --overwrite` 成功。
- フェーズ14の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- `line_prob` は線検出には有効だが、`line_soft` のcoverageとして既定利用すると、元画像の微妙な濃度揺れを高解像度supportへ増幅し、浅角度線に大きな周期の波打ちを固定することがある。
- 「ジャギーを減らす」目的でも、soft alphaを薄く重ねるだけでは品質改善に寄与せず、不要なグレー層として画質を下げることがある。重ねるならdebugで `sdf_alpha_before_soft_mode_hr` と最終alphaの差を見る。
- レビューZIPの展開物には草案コードが含まれるため、リント対象に入れると保管物の書式でCIが落ちる。外部レビュー資料は `reviews/` 配下に隔離し、原本性を優先してプロジェクトlintから除外する。

## 2026-07-09 フェーズ15：support拡張による線太り切り分け

### 作業内容

- ユーザー目視確認で、`04_darkness_thr026_sdf_only.png` がジャギーと波打ちの両方で最も良好、`03_darkness_thr022_sdf_only.png` は線がやや太いと判断された。
- 今回のジャギー低減軸である `soft_sdf_threshold` は `0.26` に固定し、それ以外で線を太らせ得る処理を切り分けることにした。
- 現在の `line_only` では直接的な線幅補正 `width_bias_source_px` は `0.0`、soft alpha重ねは `none:0.0`、`directional_smoothing` と `line_stabilizer` は無効であるため、残る候補として `mask.hysteresis.weak` による弱線support拡張と `cleanup.fill_holes_area` を段階化した。
- `config/grids/support_fattening_isolation.yaml` を追加した。
  - `support_fattening_0`: weak support拡張なし相当、`fill_holes_area: 0`
  - `support_fattening_1of3`: 現状の約1/3
  - `support_fattening_2of3`: 現状の約2/3
  - `support_fattening_current`: 現状相当
- 比較画像を生成した。
  - `tmp/support_fattening_phase15/roof_compare/contact_sheet.png`
  - `tmp/support_fattening_phase15/roof_compare/center_crop_200pct.png`
  - `docs/assets/sample_compare_support_fattening_contact_sheet.png`
  - `docs/assets/sample_compare_support_fattening_center_200pct.png`

### 検証結果

- `mlu compare .\tmp\directional_smoothing_phase13\sample01_roof_crop.png -o .\tmp\support_fattening_phase15\roof_compare --scale 4 --preset line_only --grid .\config\grids\support_fattening_isolation.yaml --crop-source-size 220 --thumbnail-width 360 --overwrite` 成功。
- フェーズ15の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- `width_bias_source_px` が0でも、ヒステリシスの弱線supportや小穴埋めは線幅・細部の拾い方に影響し得る。ただし今回の比較では段階差が小さく、太さの主因はsupport拡張より `soft_sdf_threshold` 側に残っている可能性が高い。
- 線幅調整の切り分けでは、ジャギー低減軸と線太り軸を同時に動かすと判断できない。今回は `soft_sdf_threshold: 0.26`、`coverage: darkness`、`soft_alpha_mode: none` を固定してからsupport拡張だけを動かした。

## 2026-07-09 フェーズ16：weak support無効時のsoft SDF閾値比較

### 作業内容

- ユーザー指定に従い、ヒステリシスのweak support拡張と `fill_holes_area` を無効化した状態で、`soft_sdf_threshold` だけを比較した。
- `config/grids/no_hysteresis_threshold_sweep.yaml` を追加した。
  - base条件:
    - `mask.hysteresis.enabled: false`
    - `mask.cleanup.fill_holes_area: 0`
    - `mask.soft_coverage.mode: darkness`
    - `sdf.width_bias_source_px: 0.0`
    - `sdf.soft_alpha_mode: none`
    - `directional_smoothing.enabled: false`
    - `line_stabilizer.enabled: false`
  - 比較閾値:
    - `soft_sdf_threshold: 0.26`
    - `soft_sdf_threshold: 0.30`
    - `soft_sdf_threshold: 0.34`
- 既存の屋根クロップ範囲で比較画像を生成した。
  - `tmp/no_hysteresis_threshold_phase16/roof_compare/contact_sheet.png`
  - `tmp/no_hysteresis_threshold_phase16/roof_compare/center_crop_200pct.png`
- `sample01` 全体でも3variantの個別PNGを生成した。
  - `tmp/no_hysteresis_threshold_phase16/sample01_full/sample01_no_hysteresis_thr026.png`
  - `tmp/no_hysteresis_threshold_phase16/sample01_full/sample01_no_hysteresis_thr030.png`
  - `tmp/no_hysteresis_threshold_phase16/sample01_full/sample01_no_hysteresis_thr034.png`
- README等から参照しやすいように、比較シートを `docs/assets/` に保存した。
  - `docs/assets/sample_compare_no_hysteresis_threshold_roof_contact_sheet.png`
  - `docs/assets/sample_compare_no_hysteresis_threshold_roof_center_200pct.png`
  - `docs/assets/sample_compare_no_hysteresis_threshold_sample01_contact_sheet.png`
  - `docs/assets/sample_compare_no_hysteresis_threshold_sample01_center_200pct.png`

### 検証結果

- `mlu compare .\tmp\directional_smoothing_phase13\sample01_roof_crop.png -o .\tmp\no_hysteresis_threshold_phase16\roof_compare --scale 4 --preset line_only --grid .\config\grids\no_hysteresis_threshold_sweep.yaml --crop-source-size 220 --thumbnail-width 360 --overwrite` 成功。
- `mlu compare .\images\input\sample01.png -o .\tmp\no_hysteresis_threshold_phase16\sample01_full --scale 4 --preset line_only --grid .\config\grids\no_hysteresis_threshold_sweep.yaml --crop-source-size 256 --thumbnail-width 360 --overwrite` 成功。
- フェーズ16の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- 「weak supportを0にする」は、`weak` 値を `strong` へ近づけるより、`hysteresis.enabled: false` として明示的に無効化した方が条件の意味が明確になる。
- クロップ比較だけだと局所的な線幅や波打ちは確認しやすいが、細い電線・窓枠・葉などの欠けは見落としやすい。閾値候補を絞る段階でも、代表サンプル全体の個別PNGを同時に出す。

## 2026-07-09 フェーズ17：Windows GUI exe

### 作業内容

- `src/mlu/gui.py` を追加し、Tkinterベースの単一画像GUIを実装した。
  - 入力ファイル選択ボタン。
  - 出力倍率プルダウン。
    - 既定は4倍。
    - 2倍、3倍、4倍、6倍、8倍に対応。
  - `soft_sdf_threshold` スライダー。
    - 既定は0.34。
    - 0.04刻みで前後へ調整。
    - 0未満になる位置は有効値0.0へclampする。
  - 出力フォルダ選択ボタン。
  - 出力ボタン。
  - 出力結果プレビュー。
  - 拡大・縮小・全体表示ボタン。
  - ドラッグ移動による手のひらツール相当のプレビュー移動。
- 処理本体の倍率制限を `2, 3, 4` から `2, 3, 4, 6, 8` へ拡張した。
  - `src/mlu/scales.py` に対応倍率を集約した。
  - `config.py`、`cli.py`、`sdf_render.py`、`potrace_render.py`、`line_stabilizer.py`、`upscaler_external.py` を更新した。
- `pyproject.toml` に `mlu-gui = mlu.gui:main` と `pyinstaller>=6` を追加した。
- `tools/build_gui_exe.ps1` を追加した。
  - `config/` をexeへ同梱する。
  - 未使用のpytest、matplotlib、Qt系を除外する。
- `dist/723UpScalerGUI.exe` を生成した。
  - サイズは約65.7MB。
- README、CLI/config仕様、最小実用アルゴリズム仕様、ロードマップを更新した。

### 検証結果

- `python -m mlu.gui --version` 成功。
- `python -m pytest tests\test_gui.py tests\test_config.py tests\test_pipeline.py tests\test_sdf_render.py` 成功。54件通過。
- `ruff check src\mlu\gui.py src\mlu\scales.py src\mlu\config.py src\mlu\sdf_render.py src\mlu\cli.py src\mlu\line_stabilizer.py src\mlu\potrace_render.py src\mlu\upscaler_external.py tests\test_gui.py tests\test_config.py tests\test_pipeline.py` 成功。
- `powershell -ExecutionPolicy Bypass -File .\tools\build_gui_exe.ps1` 成功。
- `Start-Process .\dist\723UpScalerGUI.exe --version -Wait` 相当の起動終了確認に成功。Exit Code 0。
- フェーズ17の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- PyInstallerは環境に入っている未使用パッケージをhook経由で拾うことがある。初回ビルドではmatplotlib/Qt系まで同梱され、exeが約118MBになった。GUIで使わない大きな依存はビルドスクリプトで明示除外する。
- exe内でプリセットYAMLを読むには `config/` を `--add-data` で同梱する必要がある。コードだけをone-file化すると、`line_only` プリセットが見つからない。
- GUIのバックグラウンドスレッドからTkinterウィジェットを直接触らない。処理完了やエラー表示は `after()` でUIスレッドへ戻す。

## 2026-07-10 フェーズ18：GUI exeのプリセット読込修正と入力プレビュー

### 作業内容

- ユーザー報告で、GUI exeから出力すると `Preset does not exist: line_only` が出ることを確認した。
- 原因はアプリ側のリソース探索だった。
  - PyInstaller one-file exeでは、同梱した `config/` は一時展開先に置かれる。
  - 既存の `repo_root()` は通常のソースツリーだけを前提にしていたため、exe内の `config/presets/line_only.yaml` を見つけられなかった。
- `config.repo_root()` を修正し、PyInstaller実行時は `sys._MEIPASS` を優先するようにした。
- GUIに `--check-config` 診断引数を追加し、exe内から `line_only` プリセットを読めるか検証できるようにした。
- 入力ファイル選択直後にプレビュー領域へ画像を表示するようにした。
  - `ImageOps.exif_transpose()` でEXIF回転を反映する。
  - 出力後は同じプレビュー領域を出力結果へ差し替える。
- 既存 `dist/723UpScalerGUI.exe` は実行中プロセスが2つありロックされていたため、上書きビルドは失敗した。
  - 実行中プロセスは強制終了しなかった。
  - 修正版は `dist/723UpScalerGUI_fixed.exe` としてビルドした。

### 検証結果

- `python -m pytest tests\test_gui.py tests\test_config.py` 成功。29件通過。
- `ruff check src\mlu\config.py src\mlu\gui.py tests\test_config.py tests\test_gui.py` 成功。
- `python -m mlu.gui --check-config` 成功。
- `powershell -ExecutionPolicy Bypass -File .\tools\build_gui_exe.ps1 -Name 723UpScalerGUI_fixed` 成功。
- `Start-Process .\dist\723UpScalerGUI_fixed.exe --check-config -Wait` 相当の確認に成功。Exit Code 0。
- フェーズ18の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- `--add-data "config;config"` でデータを同梱しても、アプリ側が `sys._MEIPASS` を見ていなければone-file exeでは読めない。exe化するリソースは、ビルド設定と実行時探索の両方をセットで確認する。
- windowed exeは標準出力を見にくい。GUI専用でも、`--check-config` のような非表示診断引数を用意しておくと、同梱データ読込をExit Codeで検証できる。
- 既存exeを起動したまま再ビルドすると上書きに失敗する。ユーザーが開いている可能性があるexeは強制終了せず、別名ビルドで検証を進める。

## 2026-07-10 フェーズ19：GUI左右比較プレビュー

### 作業内容

- ユーザー要望に従い、GUIのプレビューを出力前後比較ビューへ変更した。
- 入力選択直後は従来どおり入力画像を単独プレビューする。
- 出力後は、左ペインに出力前画像、右ペインに出力後画像を表示する。
- 比較時の座標系は出力画像のピクセル座標を基準にした。
  - 左の入力画像は、出力画像と同じ範囲を比較できるように表示上は出力倍率相当へ拡大する。
  - 右の出力画像は実出力PNGをそのまま基準座標に置く。
- 拡大・縮小ボタンは左右ペインで同じ `preview_scale` を使う。
- クリック＆ドラッグの視点移動は左右ペインで同じoffsetを使う。
- 各ペインに表示する画像は、ペイン内の可視範囲だけを切り出して描画する方式にした。
  - ズーム時に左画像が右ペインへはみ出さない。
  - 巨大画像の全体を毎回Canvasへ直接置くより、描画範囲を制御しやすい。
- `comparison_scale_for_images()` を追加し、入力画像と出力画像の表示倍率対応をテストした。
- 通常名の `dist/723UpScalerGUI.exe` を再ビルドした。

### 検証結果

- `python -m pytest tests\test_gui.py tests\test_config.py` 成功。31件通過。
- `ruff check src\mlu\gui.py tests\test_gui.py` 成功。
- `powershell -ExecutionPolicy Bypass -File .\tools\build_gui_exe.ps1` 成功。
- `Start-Process .\dist\723UpScalerGUI.exe --check-config -Wait` 相当の確認に成功。Exit Code 0。
- 全体検証:
  - `python -m pytest` 成功。137件通過。
  - `ruff check` 成功。
- フェーズ19の未完了チェック項目は0件。

### 今後同じミスをしないための有益な失敗

- Canvasに左右ペインを作るだけでは、拡大した画像が隣のペインへはみ出す。Tkinter Canvas自体には簡単なペイン単位クリップがないため、ペインごとに可視範囲を切り出してから描画する方が安全。
- 出力前後比較では、入力画像と出力画像のピクセル寸法が異なる。単に同じズーム率で描くと比較範囲が揃わないため、出力画像座標を基準にして入力画像を表示上の出力倍率へ合わせる。

## 2026-07-10 CSP風ベクター線単純化の導入可否判断

### 作業内容

- ユーザー提示のCLIP STUDIO PAINT「ベクター線単純化」に近い補正を、現行アプリへ導入できるか確認した。
- 現行の本線は `line_alpha_hr` というラスタalphaをSDFで生成する方式であり、CSPのような制御点付きベクター線は保持していないことを確認した。
- 既存の候補機能を整理した。
  - `directional_smoothing` は局所方向に沿ったラスタalpha平滑化であり、中心線や制御点の単純化ではない。
  - `line_stabilizer` は直線coverageを描き足す方式で、過去に元画像にない極細線を生成するリスクが確認済み。
  - `potrace` は輪郭ベースの外部ベクター化で、ストローク中心線の制御点削減とは性質が異なる。
- `docs/05_development_roadmap.md` にフェーズ20「中心線ベース線単純化（実験候補）」を追加した。
- 既定GUIへ即時導入するのではなく、中心線抽出、単純化、線幅再付与、交差部保護、debug出力を持つ実験ブランチとして扱う方針にした。

### 判断

同じ思想の補正は可能だが、現行SDFパイプラインへ小さな後処理として安全に入れる処理ではない。導入する場合は、ラスタalphaから中心線を抽出し、Douglas-Peucker系などで単純化し、元の線幅を再付与して再ラスタライズする新しい実験ブランチとして進める。

GUIに載せる場合も、既定値は0で完全無効にし、品質確認後にだけ「線単純化」スライダーとして追加する。既存の `directional_smoothing` を「ベクター線単純化」として露出することは、過去の浅角度線波打ち副作用と処理内容の違いから避ける。

### 今後同じミスをしないための有益な失敗

- ラスタalphaの方向性平滑化と、ベクター制御点の単純化は別物である。UI上で同じ名前にすると、ユーザーが期待する「制御点を減らして形を整理する処理」と実装内容がずれる。
- 偽線生成を避けるためには、直線を新規描画する方式より、中心線単純化後も既存support外へインクを出さない制約が必要になる。
- 中心線ベース処理は、交差部や端点を壊すと建築背景で破綻が目立つ。単純化アルゴリズム本体より先に、保護領域とdebug可視化を設計する。

## 2026-07-10 フェーズ20：中心線ベース線単純化の開発実験

### 作業内容

- `src/mlu/centerline_simplification.py` を追加した。
  - SDF後alphaをsource解像度へ集約する。
  - Zhang-Suen thinningで中心線を抽出する。
  - 冗長な斜め辺を除いた8近傍グラフとして枝を追跡する。
  - 長い開放枝をRamer-Douglas-Peucker法で単純化する。
  - 端点、分岐、短い枝、閉曲線、太い形状を保護または対象外にする。
  - 元の高解像度alphaを中心線法線方向へサンプリングし、隣接する別線を含めない連続区間から線幅を再推定する。
  - 2倍supersamplingで再描画し、元supportの対象枝と局所近傍だけへstrength付きで混合する。
- `centerline_simplification` 設定を追加した。既定は `enabled: false`、`tolerance_source_px: 0.0` で、0では処理を完全に迂回する。
- run JSONへ適用有無、パス数、制御点削減率、変更画素率、support guardを記録する。
- debugへ中心線、単純化後中心線、保護領域、alpha差分を追加した。
- `config/grids/centerline_simplification.yaml` に4段階を追加した。
  - なし: tolerance `0.0`、strength `0.0`
  - 弱: tolerance `0.75`、strength `0.35`
  - 中: tolerance `1.25`、strength `0.65`
  - 強: tolerance `2.0`、strength `1.0`
- `sample01` 全体の4出力を保存した。
  - `tmp/centerline_simplification_phase20/sample01_full/variants/`
- 現在の `sample01` から屋根範囲を切り出した比較画像を保存した。
  - `tmp/centerline_simplification_phase20/sample01_full/roof_crop_comparison_4x.png`
  - `docs/assets/sample_compare_centerline_simplification_roof_4x.png`
- 全体サムネイル比較も `docs/assets/sample_compare_centerline_simplification_contact_sheet.png` に保存した。

### 目視上の初期所見

- 弱・中では建物、電線、植栽の大部分を保ったまま変化量を段階化できた。
- 強では長い曲線の制御点が大きく減る一方、曲線が少数の直線へ分解され、多角形状の折れが見える場合がある。
- このため、今回の実験結果だけではGUIへ採用せず、ユーザー目視判断後に許容上限とUI値の割り当てを決める。

### 検証結果

- `python -m pytest tests/test_centerline_simplification.py tests/test_pipeline.py tests/test_config.py` 成功。43件通過。
- `ruff check src tests` 成功。
- `python -m pytest` 成功。143件通過。
- `mlu compare` による屋根クロップ4variantと `sample01` 全体4variantの生成に成功した。
- 既定OFFまたは許容誤差0では入力alphaと同一オブジェクトを返すテストが通過した。
- 再描画alphaが元線の局所近傍外へ出ない回帰テストが通過した。

### 今後同じミスをしないための有益な失敗

- 元support内だけで単純化結果を「削る」初期方式は、波打ちの山を落とせても線を細くし、長い建築線に断線を作った。中心線を移動して滑らかにする処理には、元supportのごく近い外側へ再描画できる局所マージンが必要。
- EDT半径をそのまま線幅へ変換すると、1px線や偶数幅線で太さを誤りやすい。高解像度alphaを法線方向へ直接サンプリングした方が元の見た目に近い。
- 法線上のalphaを全区間積分すると、平行な屋根線など隣接線まで線幅へ加算し、再描画が太る。中心付近の連続したalpha区間だけを積分する。
- RDP許容誤差がsource pixelの階段振幅より小さいと、制御点数は減っても見た目の階段がほとんど変わらない。今回の4段階では0.75px以上から差を確認した。
- フェーズ20の未完了項目は、GUI調整仕様とGUIスライダー追加の2件。強設定の多角形化をユーザー目視で評価してから進める。

## 2026-07-10 フェーズ20：単純化出力のグレーにじみ除去

### 原因

- 補正なしの `sample01` 出力は画素値0/255の2値だけだった。
- 単純化variantは、2倍supersampling後のLanczos再描画によるfractional alphaを保持していた。
- 弱・中variantではさらに `strength: 0.35 / 0.65` で元alphaと再描画alphaを混合したため、旧線と新線の間にグレーが残った。
- 修正前のグレー画素数は、弱946,239件、中1,090,673件、強824,807件だった。

### 修正内容

- `centerline_simplification.binarize_output` を追加し、既定を `true` にした。
- `centerline_simplification.binary_threshold` を追加し、既定を `0.50` にした。
- supersamplingとLanczos coverageは、滑らかな線の占有率を決める内部処理として維持した。
- 元alphaとの合成後、最終 `line_alpha_hr` 全体を閾値処理して0/1へ戻すようにした。
- 4段階比較の単純化有効variantは `strength: 0.55 / 0.75 / 1.0`、`tolerance_source_px: 0.75 / 1.25 / 2.0` とした。二値化閾値0.5以下のstrengthは補正が消えるため使わない。
- run JSONへ二値化前後のfractional pixel ratioを記録するようにした。
- 二値化を無効化した診断出力もconfigから再現可能にした。
- 二値化時に元線と重ならない面積2px以下の新規孤立成分を除去し、Lanczos ringing由来の孤立黒点を残さないようにした。
- 比較元variantがすべて二値の場合、`contact_sheet.png` とcrop比較もNEAREST縮小と最終二値化を使うようにした。

### 出力確認

- `tmp/centerline_simplification_phase20/roof_compare/` を再生成した。
- `tmp/centerline_simplification_phase20/sample01_full/` を再生成した。
- `sample01` 全体の補正なし・弱・中・強は、すべて画素値0/255のみ、グレー画素0件だった。
- `contact_sheet.png`、中央crop比較、屋根crop比較も画素値0/255のみ、グレー画素0件だった。
- `docs/assets/sample_compare_centerline_simplification_*.png` を二値化後の比較へ更新した。
- 黒画素数は補正なし比で弱 `-0.624%`、中 `-1.461%`、強 `-3.296%` だった。
- 8近傍連結成分数は補正なし396、弱423、中417、強422だった。強は線面積減少が大きいため、引き続き比較用上限として扱う。
- 単純な1本線fixtureでは、弱・中・強の各段階が別結果になり、各出力の線連結が1成分のまま保たれる回帰テストを追加した。

### 今後同じミスをしないための有益な失敗

- 内部でアンチエイリアスcoverageを使うことと、最終PNGへグレーを残すことは別問題である。形状決定にはsupersamplingを使い、漫画原稿向け最終出力では最後に明示的な二値化を行う。
- 小数alphaの `strength` はグレースケール出力では連続的な強度になるが、最終二値化と組み合わせると閾値を跨ぐかどうかで不連続になる。二値閾値を超える `strength > 0.5` の範囲だけを使い、弱・中は0.55/0.75として旧線保持と新線coverage採用を保守側へ寄せる。

## 2026-07-10 フェーズ20：ディテール保護と中心線ガタつき低減案の調査

### 調査結果

- コード変更は行わず、現行実装、既存テスト、比較grid、生成済み診断画像を調査した。
- 二値化前のalphaへ `strength` を掛ける現方式は、最終閾値0.5との組み合わせで連続強度にならない。同じ `tolerance_source_px: 0.75` で `strength` を0.55から1.0へ変えた屋根cropでは、黒画素減少が `-0.855%` から `-2.866%`、8近傍連結成分が58から60へ増えたため、alpha混合の単独廃止は低リスクではない。
- 低リスク寄りの構成は、alpha混合を廃止する代わりに、各RDP区間で元中心線点から区間内の線形補間点へ座標を幾何補間し、その補間率を強度として扱う方式である。端点保護範囲は補間せず、最終二値化と局所support guardは維持する。
- source解像度の整数RDP制御点を単に直線描画する処理は現行にもある。追加価値があるのは、元パスとRDP後パスの対応点を浮動小数座標で連続補間することであり、Bezier/Catmull-Rom等の高次補間はovershootと角丸めのため初回案から除外する。
- 曲率/corner anchorは、source階段を角と誤認しないよう、弧長2.5から3.0px程度の両側窓で方向差を測り、30度前後以上の局所最大だけをanchorとしてRDP区間を分割する案が妥当。交差部と端点の既存保護は維持し、corner近傍の線幅法線は片側接線または小半径の別保護を要する。
- corner anchor導入後の比較初期値は `low: 1.0`、`medium: 1.25`、`high: 1.5` source pxを推奨する。現行0.75はsource階段を残しやすく、2.0は長い曲線の多角形化と黒画素減少が大きい。anchor導入前は上限1.25に留める。

### 必要な検証

- 強度0/1と中間値で、端点固定、変位の単調性、許容誤差内、最終alphaの完全二値を確認する単体テスト。
- L/V字角、浅角度直線、滑らかな開曲線、閉曲線、T/X交差、短線を使い、角anchor、交差部・端点の画素一致、連結性を確認する統合テスト。
- 1/2/3 source px幅の水平・斜線で、法線方向幅、黒画素面積、断線、新規成分を比較するテスト。
- 実サンプルでは中心線の直線当てはめRMS、角位置ずれ、黒画素増減、8近傍連結成分、追加/削除画素、局所support外画素をなし・弱・中・強で記録する。

### 検証結果

- `python -m pytest -q tests/test_centerline_simplification.py` 成功。5件通過。
- `python -m pytest -q tests/test_config.py tests/test_pipeline.py` 成功。40件通過。
- フェーズ20の未完了項目は、UI調整仕様とGUIスライダー追加の2件。

## 2026-07-10 フェーズ20：low品質崩れの修正と幾何強度化

### 原因

- 旧lowの `tolerance_source_px: 0.75` は、source解像度の1px階段をRDP制御点として残していた。
- 旧lowは `strength: 0.55` で二値alphaを混合してから閾値0.5で二値化していた。
  - 元黒画素では再描画coverageが約0.091以上なら黒が残る。
  - 元白画素ではcoverageが約0.909以上にならないと新しい黒にならない。
- この非対称判定により、旧輪郭の微小な黒片と単純化線の芯が混在し、medium/highよりlowだけ局所的な太さ変動とガタつきが目立った。
- 屋根上の代表的な313点の長線では、旧lowは28制御点と10度超の方向変化23回を残したが、medium/highは11点・4回まで減っていた。

### 修正内容

- 二値出力時のalpha混合を廃止し、再描画coverageは常に100%置換してから二値化するようにした。
- `geometry_strength` を追加した。
  - 元パス各点と対応するRDP chord上の点を弧長比で対応付ける。
  - `q = (1 - g) * original + g * simplified` で浮動小数座標を補間する。
  - 端点保護範囲とRDPアンカーは移動しない。
- low/medium/highを次の設定へ変更した。
  - low: tolerance `1.00`、geometry strength `0.50`
  - medium: tolerance `1.25`、geometry strength `0.75`
  - high: tolerance `1.50`、geometry strength `1.00`
- 弧長3pxの両側方向差が45度以上の点を実角アンカーとして検出し、RDP区間を分割するようにした。
- 線幅は簡略制御点だけでなく元の密な中心線点で再推定し、幾何補間後のパスへ付与するようにした。
- `config/grids/centerline_low_diagnosis.yaml` を、旧0.75形状と新しいlow/medium/highを比較する診断gridへ更新した。

### 出力確認

- `tmp/centerline_simplification_phase20/roof_compare_v2/` に新方式の屋根比較を保存した。
- `tmp/centerline_simplification_phase20/sample01_full/` の4出力と比較画像を新方式で再生成した。
- `docs/assets/sample_compare_centerline_simplification_*.png` を更新した。
- `sample01` 全体の黒画素変化は補正なし比で次の範囲に収まった。
  - low: `-0.035%`。旧方式は `-0.624%`。
  - medium: `-0.381%`。旧方式は `-1.461%`。
  - high: `-0.551%`。旧方式は `-3.296%`。
- 8近傍連結成分数は補正なし396、low412、medium412、high414だった。
- 4variantと全比較画像は画素値0/255のみで、グレー画素0件だった。
- 実角アンカーは `sample01` 全体で85点検出された。

### 検証結果

- `python -m pytest` 成功。150件通過。
- `ruff check src tests` 成功。
- 幾何強度0/0.5/1.0のアンカー固定と変位単調性をテストした。
- 45度実角を保持し、浅いデジタル階段を角アンカーにしないテストを追加した。
- T字交差を最終再描画・二値化後も1成分のまま保ち、交差保護領域が画素一致するテストを追加した。
- 単純な1本線fixtureでlow/medium/highが別結果になり、各線が1成分のまま保たれることを確認した。

### 今後同じミスをしないための有益な失敗

- 二値画像におけるalpha混合率は、最終閾値の前後で連続的な強度として働かない。二値線画の補正強度はalpha濃度ではなく、中心線座標や形状パラメータで表現する。
- RDP許容誤差がsource階段の振幅以下だと、「弱い補正」ではなく階段を忠実に再描画する結果になる。lowでも階段振幅を超える最小値を使い、ディテールは角アンカーと幾何補間率で保護する。
- 許容誤差だけを強くすると曲線の多角形化が増える。実角アンカーを固定し、highの上限も2.0から1.5へ下げる。
- RDP区間の隣接anchorを走査する2列の `zip` は要素数が1つ違うため、`strict=True` を使えない。新規区間分割処理では境界配列の長さ関係を単体テストで確認する。
- フェーズ20の未完了項目は、UI調整仕様とGUIスライダー追加の2件。

## 2026-07-10 フェーズ20：旧low出力の定量原因分析

### 分析対象

- 15:33生成の `tmp/centerline_simplification_phase20/` を対象に、旧4段階の `low: tolerance 0.75 / strength 0.55 / binary threshold 0.5` をなし・中・強および同一RDPの `strength 1.0` と比較した。
- 解析中に中心線実装と比較gridが更新されたため、保存PNG/run JSONと現行コードの世代差を分離した。保存PNGは旧alpha blend方式、現行コードはgeometry blend方式である。

### 定量結果

- 旧lowの二値判定は、元黒画素では再描画coverage `>= 0.0909`、元白画素では `>= 0.9091` となる。mediumは `0.3333 / 0.6667`、highは両方 `0.5` であり、lowだけ旧ラスタへ強く拘束される。
- 屋根cropで同一RDPの `epsilon 0.75 / strength 1.0` と比較すると差は12,636画素で、11,072画素（87.6%）はlowだけに残る黒だった。差分3,641成分中3,421成分（94.0%）が4画素以下で、旧輪郭の局所残留として現れている。
- 目立つ長線1枝は元313点からlowで28点、medium/highで11点になった。lowのRDP中間点には隣接1pxの階段対が残り、制御点間の方向変化10度超はlow 23回、medium 4回だった。
- `sample01` 全体の黒画素はなし3,767,837、low 3,744,312（-0.6244%）、medium 3,712,782（-1.4612%）、high 3,643,633（-3.2964%）。8近傍連結成分は396 / 423 / 417 / 422だった。

### 結論

- lowだけの崩れは、`epsilon 0.75`がsourceラスタ階段をRDP制御点として残すことと、`strength 0.55`後の閾値0.5が旧黒・旧白で非対称な実効閾値を作ることの複合原因である。単独の線幅推定や連結成分除去が主因ではない。

## 2026-07-10 フェーズ20：「長いストロークを単純化」への対象限定

### 改修内容

- ユーザー向け名称を「中心線ベース線単純化」から「長いストロークを単純化」へ変更した。設定互換性のため内部キー `centerline_simplification` は維持した。
- 今回は処理対象の限定だけを改修し、中心線抽出、RDP単純化、線幅再推定、再ラスタライズのアルゴリズムは変更していない。
- 既定対象を次の条件をすべて満たす枝に限定した。
  - 長さ64 source px以上、最大半径2.25 source px以下。
  - 45度以上の角アンカーを含まない。
  - 弦長/弧長比0.985以上。
  - PCA直線近似のRMS 0.35 source px以下、最大偏差1.0 source px以下。
  - 線幅変動係数0.20以下、線幅P90/P10比1.50以下。
- 条件外の枝は全体を保護領域へ入れ、単純化結果で置換しない。
- run JSONへ `eligible_path_count` と条件別 `rejected_path_counts` を追加し、debugへ `long_stroke_eligible_source` を追加した。

### sample01確認

- `tmp/long_stroke_simplification_phase20/sample01_full/` に補正なし、弱、中、強の全体出力と比較画像を保存した。
- 全30,891枝のうち対象は79枝だった。旧条件の1,242枝から約93.6%減少した。
- 主な除外数は短線30,685、弦長/弧長比不足55、線幅変動31、角を含む枝28、太線8だった。
- 補正なし比の黒画素変化はlow `-0.1045%`、medium `-0.2708%`、high `-0.2795%` だった。
- 8近傍連結成分数は補正なし396、low/medium/highはいずれも400だった。
- 4variant、比較画像、屋根クロップはすべて画素値0/255のみで、グレー画素はない。
- 資料用画像を `docs/assets/sample_compare_long_stroke_simplification_*.png` に保存した。

### 今後同じミスをしないための有益な失敗

- 枝長だけでは、植栽や装飾内の長い輪郭まで対象になる。長さ、角、直線性、線幅安定性を同時に満たす局所branch gateが必要である。
- support連結成分の枝数6以下、主枝長比50%以上という成分単位gateも試算したが、候補79枝が2枝まで減った。建築線は細部と同じ巨大連結成分に属しやすいため、成分の複雑さを理由に全体を除外すると必要な長線もほぼ消える。
- 厳格gateのテストで階段状疑似直線を受理ケースに使うと、弦長/弧長比条件が正しく拒否する。受理fixtureは真の直線とし、階段線は拒否fixtureとして分ける。

### 検証

- `python -m pytest -q` 成功。151件通過。
- `ruff check src tests` 成功。
- 直線の受理、角、デジタル階段、線幅変動の拒否、拒否数と対象数の総和が全path数に一致することをテストした。
- フェーズ20の未完了項目は、UI調整仕様とGUIスライダー追加の2件。

## 2026-07-10 フェーズ20：成分単位の自動ロールバック

### 改修内容

- 厳格なbranch gateと中心線単純化の後段へ、source成分単位の自動ロールバックを追加した。
- 処理順は、再ラスタライズ、二値化、2px以下の新規孤立成分除去、成分ロールバック、最終差分集計とした。
- 元画像と候補画像を出力解像度の8近傍でラベル付けし、変更画素を最寄りの処理対象source成分へ帰属させる。
- 元成分と候補成分の全画像上の重なり対応から、成分消失、分割、誤接続、新規成分を検出する。いずれか1件でも検出した成分は変更画素を元へ戻す。
- トポロジーを保っていても、帰属する置換領域内の黒画素比が0.80未満または1.20超なら、過剰な欠落または太りとして戻す。
- 二値出力時は元の二値画素を復元し、元alphaの小数値を戻さないため、ロールバック後もグレーは混入しない。
- run JSONへ評価、採用、復元成分数、候補前後と最終の全体成分数、復元画素数、理由別件数、成分別診断を追加した。
- debugへ `component_rollback_source.png` を追加し、戻された処理対象範囲を確認できるようにした。

### sample01確認

- なし・弱・中・強の全体画像を `tmp/component_rollback_phase20/sample01_full/` に保存した。
- 各補正段階で30,891枝中79枝がbranch gateを通過し、変更のあった5 source成分をロールバック判定した。
- 候補画像は元396成分から400成分へ増えていた。3 source成分で分割を検出して変更125,491〜130,069画素を戻し、安全な2成分だけを採用した。
- 最終出力の連結成分数はlow/medium/highのすべてで396へ戻り、元画像と一致した。
- 補正なし比の黒画素変化はlow `-0.0308%`、medium/high `-0.0899%` だった。
- 全variantと比較画像は画素値0/255のみで、グレー画素はない。
- ロールバック前後の屋根比較を `docs/assets/sample_compare_component_rollback_before_after_4x.png`、採用成分の比較を `docs/assets/sample_compare_component_rollback_accepted_4x.png` に保存した。

### 今後同じミスをしないための有益な失敗

- 初期実装では変更画素bboxにpaddingを加えた局所ROIの成分数を直接比較した。この方式では、ROI外で接続している1成分を複数成分と誤認する可能性があるため破棄した。
- 全体の成分数だけを比較すると、分割と誤接続が同時に起きて増減が相殺された場合を見逃す。元成分と候補成分の重なり対応を双方向に検査する必要がある。
- 黒画素総量の変化が小さくても断線は発生する。`sample01`の候補は黒画素変化が小さい一方で396成分から400成分へ増えていたため、面積比だけでは安全判定にならない。
- 微小新規成分除去より前にロールバック判定すると、後段で消える2px以下のノイズまで成分異常として扱う。最終候補に近い順序で判定する。
- 二値化後の復元に元の小数alphaを使うと、ロールバック処理自身がグレーを再混入させる。二値出力では元の二値判定値を戻す。

### 検証

- 成分分割、完全消失、新規孤立成分、2成分の誤接続、過剰な太りを元へ戻すテストを追加した。
- 連結性と黒画素量を保った局所移動は採用されることをテストした。
- 対象テスト57件、全テスト156件、`ruff check src tests` は成功した。
- フェーズ20の未完了項目は、UI調整仕様とGUIスライダー追加の2件。

## 2026-07-10 フェーズ20：RDPを高周波ノイズ除去へ置換

### 改修内容

- Ramer-Douglas-Peuckerの制御点削減、区間chordへの幾何補間、制御点削減統計を実行経路から削除した。
- gate通過中心線を0.5 source px間隔へ等弧長化し、Y/Xへ1次元Gaussian低域通過を適用する方式へ変更した。
- フィルタ後中心線から接線を求め、変位の接線成分を除き、法線成分だけを採用する。元の密な中心線点数は維持する。
- 端点とcorner近傍は変位0とし、3 sigma範囲をsmoothstepで接続する。最終変位は設定値でベクトル長clampする。
- low/medium/highを次の設定にした。
  - low: sigma `0.75`、geometry strength `0.50`、最大変位 `0.50` source px。
  - medium: sigma `1.00`、geometry strength `0.75`、最大変位 `0.75` source px。
  - high: sigma `1.25`、geometry strength `1.00`、最大変位 `1.00` source px。
- strict branch gate、局所support制限、最終二値化、成分単位ロールバックは維持した。
- 線幅系列にも同じGaussianフィルタを適用し、短周期の線幅推定ノイズを減衰させた。
- 再描画は全画面2倍supersamplingから、対象ストロークの局所bboxを原則4倍supersamplingする方式へ変更した。丸キャップは密な全サンプル点ではなく両端だけに限定した。
- `tolerance_source_px` を廃止し、`filter_sigma_source_px`、`filter_sample_step_source_px`、`max_filter_displacement_source_px` へ移行した。
- debugの `simplified_centerline_source` を `filtered_centerline_source` へ変更し、`centerline_filter_displacement_source` を追加した。
- run JSONへ平均、P95、最大変位、再サンプル数、clamp数、高周波energy減衰率を追加した。

### sample01確認

- `tmp/high_frequency_filter_phase20/sample01_full/` に補正なし、弱、中、強の全体出力と比較画像を保存した。
- 全30,891枝中79枝がstrict gateを通過し、二値化前に実変位があった枝はlow 19、medium/high 32だった。
- 最大変位はlow `0.1168`、medium `0.2119`、high `0.3202` source pxだった。設定上限へclampされた点は0件だった。
- 候補は元396成分から397成分へ増えたが、分割を起こした1 source成分をロールバックし、安全な2成分だけを採用した。最終成分数は全variantで396だった。
- 補正なし比の黒画素変化はlow `+0.0055%`、medium `+0.0130%`、high `+0.0127%` だった。
- low/medium/highはそれぞれ別の二値出力となり、全variantと比較画像の画素値は0/255のみだった。
- 目視比較を `docs/assets/sample_compare_high_frequency_filter_*.png` に保存した。

### 今後同じミスをしないための有益な失敗

- 最初にSavitzky-Golay低域通過を試作したが、負の係数によるringingがあり、窓幅に対する周波数応答も単調ではなかった。余分な線を避ける用途では、正係数でsigmaに対して単調なGaussianを優先する。
- RDP設定名 `tolerance_source_px` を別の意味へ流用すると、既存configが意図しない強度で動く。アルゴリズムを置換する場合は新しい物理量名へ移行する。
- 密な中心線の全サンプル点へ丸キャップを重ねると、浅い線で周期的な太りが生じる。連続線分を描き、丸キャップはストローク両端だけに置く。
- 線幅フィルタを中心線sigmaの4倍まで強める試行は、短周期の膨らみを長い段差へ変えただけだったため撤回した。中心線と線幅は同じsigmaに保つ。
- 全画面supersampling倍率を上げるとメモリが画像面積に比例する。対象ストロークの局所bboxだけを高倍率で描画する。
- 二値ラスタではサブピクセル中心線を平滑化しても浅い線の段差は完全には消えない。RDP多角形化は解消したが、採用判断では目視比較と成分ロールバックを継続する。

### 検証

- sigma 0とgeometry strength 0での完全迂回、完全直線不変、端点固定、低周波保持、4px周期ノイズの単調減衰、最大変位、線幅ノイズ減衰をテストした。
- 既存の交差保護、局所support、完全二値、成分ロールバックの回帰テストを維持した。
- 対象テスト59件、全テスト158件、`ruff check src tests` は成功した。
- フェーズ20の未完了項目は、UI調整仕様とGUIスライダー追加の2件。

## 2026-07-10 フェーズ20：本採用見送りと凍結

### 目視評価の結論

- 「長いストロークを単純化」は、処理対象や補正を広くすると、元画像に必要な細部や線形状を崩す作用が強くなった。
- ディテール破壊を避けるため、strict gate、最大変位、成分単位ロールバックで適用範囲を狭くすると、最終出力に残る変化が少なく、有意義な品質改善を確認できなかった。
- RDP制御点削減をGaussian高周波ノイズ除去へ置き換えても、「広く適用すると破壊的、狭く適用すると効果不足」という根本的なトレードオフは解消しなかった。
- 現方式の延長でパラメータ調整を続けても、漫画背景用の細い電線、柵、窓枠、建築線を保護しながら十分なガタつき低減を得られる見込みは低いと判断した。

### 決定

- フェーズ20は実験完了とし、本採用を見送って凍結する。
- `centerline_simplification` の実験コード、config grid、比較画像、run JSON、debugレイヤーは調査記録として保持する。
- 機能は既定OFFのままとし、製品GUIへスライダーを追加しない。
- 未着手だったUI調整仕様とGUIスライダー追加は、未達成作業ではなく凍結による中止項目としてロードマップへ記録する。
- 新しい原理の手法、またはディテール保持と有意な改善を同時に示す比較結果が得られない限り、この実験ブランチの追加調整は再開しない。

### 今後同じ判断を行うための基準

- 安全装置によって変化の大部分が元へ戻る場合、統計上安全でも製品機能としての追加価値は不足している。
- 適用範囲を広げないと効果が見えず、広げると必要なディテールを壊す手法には、実用的な設定域がない。
- アルゴリズムの局所的な改善だけでなく、最終二値出力を人間が目視して既存拡大手法より明確に優れることを本採用条件とする。

### ロードマップ状態

- フェーズ20についての未達成ロードマップは0件。UI関連2件は凍結により中止した。
- 本判断をもって、ロードマップ内の既定作業はすべて完了または明示的に中止された。

## 2026-07-10 フェーズ21：配布GUI向け表示・出力整理

### 改修内容

- GUIの内部パラメータ表示 `soft_sdf_threshold: 0.xx` を、ユーザー向けの整数表示「明るさ」へ置き換えた。
- 明るさ0を内部閾値0.36とし、1段階につき0.04を加減する。表示範囲は-9から+9で、内部閾値は0.00から0.72になる。
- 通常のGUI、`mlu upscale`、`mlu batch` では画像別の `.mlus-run.json` を生成しないよう、`debug.save_run_json` の既定値をfalseへ変更した。
- JSON生成機構自体は維持し、`--save-run-json`、`--debug-dir`、`inspect`、`compare` では実効configを含む実行記録を生成する。
- バッチの `summary.json` と `summary.csv` はパラメータのサイドカーではなく処理成否のサマリなので、通常時も生成する。

### 今後同じミスをしないための有益な失敗

- 内部アルゴリズム名と小数値をそのままGUIへ出すと、利用者が画質上の意味を判断しにくい。配布UIではユーザーの操作概念と内部パラメータを分離し、変換を単一のテスト可能な関数へ集約する。
- JSON出力の既定値だけを変更すると、比較・検査ワークフローまで記録を失う。通常処理は既定OFF、明示的なデバッグ経路はONという境界をコマンド単位で固定する。
- `--debug-dir` を指定した処理は通常出力ではないため、デバッグレイヤーとrun JSONを一緒に残す。通常バッチでサイドカーが出ないことは別の回帰テストで保証する。

### 検証

- GUIの明るさ変換について、0、±1、±9、範囲外入力のclampをテストした。
- 通常の単一画像・バッチ処理でrun JSONが生成されず、明示的なデバッグ処理では生成されることをテストした。
- `debug.save_run_json` に文字列などの非boolean値を指定した場合は設定エラーとして拒否するテストを追加した。
- 全テスト161件と `ruff check src tests` が成功した。
- `dist/723UpScalerGUI_updated.exe` を最新ソースからクリーンビルドし、`--check-config` と `--version` がともに終了コード0であることを確認した。
- 通常名の `dist/723UpScalerGUI.exe` は2プロセスで起動中だった。ユーザーの作業を中断しないため強制終了せず、更新版を別名で配置した。

### ロードマップ状態

- フェーズ21についての未達成ロードマップは0件。
- 本改修を含め、ロードマップ内の作業はすべて完了または明示的に中止されている。

## 2026-07-10 CustomTkinter移行影響調査

### 調査内容

- `src/mlu/gui.py` のイベント配線、UI状態、Tkinter固有API、プレビュー描画、バックグラウンド処理を確認した。
- CustomTkinter化後も、ファイルダイアログ、メッセージボックス、Tk変数、画像プレビュー用Canvas、`ImageTk.PhotoImage`、CanvasのマウスイベントをTkinter側に残す必要がある。
- `winfo_children()` と型判定による一括状態変更はCustomTkinterの複合ウィジェットに適さない。操作可能ウィジェットを明示的に保持し、ボタンとスライダーはnormal/disabled、コンボボックスはreadonly/disabledを直接設定する方式を推奨する。
- ワーカースレッドからUIを直接更新せず、成功・失敗とも `after(0, ...)` でUIスレッドへ戻す契約を維持する。
- `CTkSlider` は `resolution=1` の代わりに `number_of_steps=18` を使い、-9から+9の整数19値を維持する。
- CustomTkinter公式のPyInstaller手順はデータファイルの明示同梱と`--onedir`を前提とする。現行の`--onefile`ビルドスクリプト、配布パス、README、生成specは見直しが必要になる。

### 検証

- `python -m pytest` は161件成功した。
- `ruff check src/mlu/gui.py tests/test_gui.py` は成功した。
- `python -m mlu.gui --check-config`、`--version`、現行Tkinter GUIの生成・破棄スモーク確認は成功した。
- 現環境にはCustomTkinterが未導入のため、移行後ビルドは実行していない。
- コードは変更していない。

### ロードマップ状態

- 未達成チェック項目は0件で、ロードマップ内の作業はすべて完了または明示的に中止されている。

## 2026-07-10 フェーズ22：CustomTkinterによるGUI外観改善

### 改修内容

- `UpscalerGui` を `customtkinter.CTk` ベースへ移行し、ライトテーマとSegoe UIを採用した。
- 入力画像、出力先、倍率、明るさ、出力操作を、16px外側余白と8px角丸の上部設定パネルへ整理した。
- パス選択ボタンは92x36px、倍率メニューは100x36px、主操作の出力ボタンは140x42pxへ統一した。
- 拡大・縮小を中央揃えの記号ボタン、全体表示をテキストボタンとしてプレビューツールバー右側へ配置した。
- 明るさスライダーは `number_of_steps: 18` とし、-9から+9までの整数19値を維持した。
- プレビュー描画、入力と出力の左右比較、同期ズーム、同期パンは既存のTk Canvas実装を維持した。
- 処理中に無効化する操作を明示リストで管理し、CustomTkinter内部ウィジェットを再帰的に変更しない方式へ改めた。
- `customtkinter>=5.2,<6` を通常依存へ追加した。
- PyInstallerビルドを `--onedir` とCustomTkinterデータ同梱へ変更した。配布先は `dist/723UpScalerGUI/723UpScalerGUI.exe` になる。

### 今後同じミスをしないための有益な失敗

- CustomTkinterの複合ウィジェットは内部にCanvas等を持つため、`winfo_children()` を再帰して状態変更してはいけない。利用者が直接操作するウィジェットだけを保持して状態を切り替える。
- `CTkEntry` は `disabled_text_color` を受け付けない。見た目を保った読み取り専用パス欄には通常状態のEntryを使い、キー入力イベントを抑止する。
- 全角の拡大記号は小さいボタンで横線に近く見える環境がある。一般的なASCIIの `+` を使用し、縮小記号と区別できることを実画面で確認する。
- CustomTkinterはテーマJSONとフォント等のデータを含む。従来の単一ファイル化をそのまま流用せず、公式手順に沿ってデータ同梱したフォルダ配布にする。

### 目視確認

- 1240x820の実ウィンドウを起動し、設定欄の整列、パス欄、倍率メニュー、明るさスライダー、主ボタン、プレビューツールバー、空プレビューを確認した。
- 拡大・縮小ボタンは同寸法で中央揃えになり、出力ボタンだけが青い主操作として識別できる。

### 検証

- 全テスト162件と `ruff check src tests` が成功した。
- GUIの生成・破棄、`--check-config`、`--version` をソース実行で確認した。
- `dist/723UpScalerGUI/723UpScalerGUI.exe` をCustomTkinterデータ同梱の `--onedir` 形式でビルドした。
- 配布exeの `--check-config` と `--version` はともに終了コード0だった。

### ロードマップ状態

- フェーズ22についての未達成ロードマップは0件。
- 本改修を含め、ロードマップ内の作業はすべて完了または明示的に中止されている。

## 2026-07-10 フェーズ23：CustomTkinter GUIの単体EXE配布

### 判断

- CustomTkinter公式資料はテーマJSONやフォントを理由に `--onedir` を推奨しているため、フォルダ版は安定した配布経路として維持する。
- 現行PyInstallerのonefileは追加データを起動時の一時ディレクトリへ展開できる。実際の配布EXE上でUI生成まで検証することを条件に、単体版も提供する。

### 改修内容

- `tools/build_gui_exe.ps1` に `-OneFile` スイッチを追加した。指定なしは従来どおり `--onedir`、指定時は `--onefile` になる。
- どちらの形式でもCustomTkinterパッケージディレクトリと `config/` を明示的に同梱する。
- GUIへ非公開オプション `--check-ui` を追加した。CustomTkinterルート、全ウィジェット、テーマを生成してアイドル処理後に破棄するため、frozen exeのリソース不足を検出できる。
- READMEへ単体版 `dist/723UpScalerGUI.exe` と公式推奨フォルダ版 `dist/723UpScalerGUI/723UpScalerGUI.exe` の両方を記載した。

### 検証

- `powershell -ExecutionPolicy Bypass -File .\tools\build_gui_exe.ps1 -OneFile` が成功した。
- 生成物は `dist/723UpScalerGUI.exe`、73,489,142 byte。
- 単体EXEの `--check-config`、`--version`、`--check-ui` はすべて終了コード0だった。
- `--version` と `--check-ui` は一時展開を含めて約4.0秒、最初の `--check-config` は約7.6秒だった。
- 全テスト177件と `ruff check src tests` が成功した。

### 今後同じミスをしないための有益な失敗

- onefileが生成できただけではCustomTkinterのデータ同梱成功を確認できない。設定確認だけでなく、実際にCTkウィンドウを生成するfrozen exe内スモークテストを必須にする。
- onefileは起動ごとに依存ファイルを一時展開するため、フォルダ版より起動が遅い。起動速度が重要な配布ではフォルダ版を残す。

### ロードマップ状態

- フェーズ23についての未達成ロードマップは0件。
- ロードマップ内の作業はすべて完了または明示的に中止されている。

## 2026-07-10 フェーズ24：出力完全一致を維持する高速化

### 解析と改修内容

- `sample01.png` 4倍の段階計測で、全体8.234秒のうち `render_line_branch` が6.845秒、高解像度signed distance fieldが4.458秒を占めることを確認した。
- soft maskから作るexact SDFは、内側の最短距離が+1、外側の最大距離が-1である。`a=float32(aa_radius_hr_px)`、`b=float32(width_bias_source_px * scale)` とすると、内側EDTが必要なのは `1+b<a`、外側EDTが必要なのは `-1+b>-a` の場合だけである。
- 両条件が偽ならsmoothstep結果はsoft maskの0/1と完全一致するため、通常の `line_only` では高解像度EDTを省略する。片側だけ遷移域へ入る設定では必要な側だけを計算し、両側が必要な場合だけ2回計算する。
- デバッグレイヤー指定時は従来どおり完全なsource/HR SDFを保持する。run JSONだけを保存する場合は距離配列を保持せず、line softのmin/max/meanとmask面積率だけを同じfloat32集計値で記録する。
- 距離変換をDIPlib 3.6.1系列の `EuclideanDistanceTransform(..., "object", "separable")` へ置き換えた。ライセンスはApache-2.0で本体と整合する。SciPy参照実装とのfloat32距離一致を、ランダム・境界mask、長距離1次元形状、実サンプルで確認した。
- SDF alphaが完全二値、tone未使用、白キャンバス、line darkness 1、全後処理OFFの場合は、gamma合成を数学的に同値な `final = 1 - alpha` へ短絡した。
- 既定OFFのline stabilizerとdirectional smoothingをpipelineで短絡し、不要な高解像度zero配列2枚を生成・保持しないようにした。
- 純線画判定で固定半径2のEDTを13画素Euclidean diskのbinary dilationへ置き換えた。小穴埋めは`binary_fill_holes`後の再labelを廃止し、背景label 1回と境界接触label除外で同じ結果を得る方式へ変更した。
- 完全一致を検証した `diplib==3.6.1` を必須依存へ固定し、doctor表示、README、依存・配布設計、第三者告知を更新した。

### 性能と完全一致確認

- `sample01.png` 1448x1086、`line_only`、4倍、通常出力のwarm中央値は変更前8.234秒から0.884秒へ短縮し、約9.3倍となった。
- fresh processのpeak working setは1384.4MiBから664.4MiBへ約52%減少した。
- 完全SDF診断とrun JSONを保持する経路も中央値0.933秒だった。
- 変更前後のfinal float32、復号PNG画素、PNGファイルSHA-256は完全一致した。PNG SHA-256は `ce292aacd6d3c77f3955b70440d69786a26142ee30bbc98efe218424e03708eb`。
- scale 2/3/4/6/8、AAと線幅biasの境界内外、none/max/blend、empty/full/random maskを含む1620組で、最終用経路と完全SDF経路のalphaが全件 `np.array_equal` だった。

### 配布

- `tools/build_gui_exe.ps1` でDIPlibの `DIP.dll` を明示収集し、不要なviewer/javaioバイナリを除外した。
- 本体Apache-2.0 LICENSEと `THIRD_PARTY_NOTICES.md` を配布フォルダの `licenses` へ同梱した。
- `dist/723UpScalerGUI_fast/723UpScalerGUI_fast.exe` の `--check-config` と `--version` は終了コード0だった。

### 今後同じミスをしないための有益な失敗

- 二値maskからSDFを作っても、AA遷移幅が1px未満なら距離値は最終alphaへ寄与しない場合がある。重い処理は入力条件だけでなく、後段の飽和条件まで式で確認する。
- 内外EDTを単純に2スレッド化するとx4では速くなる一方、同時scratchによりpeak working setが約1.8GiBまで増えた。8倍画像で危険なため採用せず、不要側の省略とfloat32 exact EDTを優先した。
- PyInstallerの `--collect-binaries diplib` は不要なDIPjavaioまで収集し、未使用の`jvm.dll`警告を出した。必要な`DIP.dll`だけを明示追加し、javaio/viewer拡張を除外する。
- 通常名の既存distフォルダはDropboxまたは別プロセスのロックによりCOLLECT時に削除できなかった。利用中の成果物を強制終了・削除せず、別名の配布フォルダへ安全にビルドする。
- bool maskの`mean()`はfloat64集計になり、従来のfloat32 debug mask平均と最下位桁が変わる。run JSONまで互換にする場合は `np.mean(mask, dtype=np.float32)` を明示する。

### 検証

- `python -m pytest` 成功。179件通過。
- `ruff check src tests` 成功。
- `python -m pip check` 成功。
- フェーズ24についての未達成ロードマップは0件。
- 本改修を含め、ロードマップ内の作業はすべて完了または明示的に中止されている。

## 2026-07-10 フェーズ25：GUIのフォルダ一括変換

### 改修内容

- 入力ファイル選択の横へ「フォルダを指定して一括変換」ボタンを追加した。
- フォルダモード時だけ「指定した文字列を含むファイルのみ変換」チェック、1行入力欄、「拡張子を指定」メニューを表示する。文字列チェックは既定OFFで、ONの場合だけ入力欄を表示する。
- GUIで既に単一変換可能だった `png, jpg, jpeg, tif, tiff, bmp` を固定の対応形式として一元化し、全形式または1形式を選べるようにした。
- Windows禁止文字と制御文字を除いた検索語が空の場合は文字列条件を適用せず、有効な場合は拡張子を除くファイル名へ大文字小文字を区別しない部分一致を適用する。拡張子との併用はAND条件にした。
- GUI一括変換は選択フォルダ直下だけを対象とし、ファイル名順を固定して先頭1枚だけを入力プレビューへ表示する。変換後も先頭入力に対応する出力だけを左右比較へ表示する。
- 出力時に対象一覧を再計算して「N枚の画像を一括変換します。よろしいですか？」と確認し、キャンセル時はworkerを開始しない。OK時は同じ一覧を固定して順次変換する。
- 単一GUIと同じ倍率・明るさ設定、`stem_x{scale}_thr{threshold}` 命名を使い、既存出力と同stemの別拡張子を予約済みパス集合で連番回避する。
- 1枚の変換失敗後も残りを処理し、最後に成功・失敗数と先頭5件のエラーを通知する。
- 自動出力先を入力フォルダ内の `723UpScaler_output` にした。入力フォルダ自身を出力先に明示した場合も、GUI生成名に一致するPNGを次回入力から除外して自己増殖を防ぐ。
- フォルダ走査の権限エラーや切断をプレビュー更新で捕捉し、Tkコールバック例外ではなくステータス表示へ戻す。
- README、開発ロードマップ、受け入れチェックリストを更新した。

### 今後同じミスをしないための有益な失敗

- 入力フォルダを出力先の既定にすると、生成PNGが次回の入力へ混ざり、実行ごとに対象が増える。フォルダ一括処理では専用出力先を既定にし、同一フォルダを許す場合も自生成物を除外する。
- フォルダの存在・種別だけを検証しても、`iterdir()` 自体は権限、ネットワーク切断、同期状態で `OSError` を返し得る。出力開始時だけでなく、フィルタ変更に伴うプレビュー更新も走査例外を処理する。
- WindowsのTk環境によっては、同一pytestプロセス内でGUIルートを何度も生成・破棄するとTclリソースの再初期化に失敗する。実GUIスモークは1回に保ち、追加の状態遷移は純粋関数と軽量状態スタブで検証する。
- 対象枚数を確認したあとに再探索すると、確認件数と実処理件数がずれる。確認に使ったPath一覧をtupleとして固定し、そのままworkerへ渡す。

### 検証

- 拡張子・文字列AND条件、無効検索語、大小文字、直下限定、出力自己混入除外、同stem出力予約、確認キャンセル/OK、先頭プレビュー、途中失敗継続、走査権限エラーを追加テストした。
- `python -m pytest` は189件成功した。
- `python -m ruff check src tests` と `python -m pip check` は成功した。
- ソース版の `--check-config`、`--version`、`--check-ui` は終了コード0だった。
- 単体版 `dist/723UpScalerGUI.exe` を最新ソースから再ビルドした。サイズは73,063,584 byteで、`--check-config`、`--version`、`--check-ui` はすべて終了コード0だった。
- 配布EXEの初期画面を目視し、入力行に単一ファイル選択と一括変換ボタンが横並びで収まり、既存の倍率・明るさ・出力・プレビュー領域が崩れていないことを確認した。

### ロードマップ状態

- フェーズ25についての未達成ロードマップは0件。
- ロードマップ内の作業はすべて終わりました。

## 2026-07-11 フェーズ26：実出力一致のリアルタイムプレビュー

### 改修内容

- 出力倍率メニューの右側へ「プレビューを表示する」チェックボックスを追加し、既定ONにした。
- 単一ファイル入力時とフォルダ入力の先頭画像確定時に、現在の倍率・明るさで出力プレビューを自動生成する。
- 倍率と明るさの変更は200ms debounceし、変更中の不要な中間設定を処理しないようにした。
- プレビューには実出力と同じ `line_only` configと `upscale_image` を使い、専用一時フォルダへPNGを生成して復号後のL画像をコピーする。指定出力先には書き込まず、一時フォルダは成功・失敗のどちらでも終了時に削除する。
- 出力サイズの縦横積が36,000,000以上になる場合、同じ入力で最初の出力プレビューを作る前に縦横サイズを示して確認する。「いいえ」ではチェックを外し、再びONにするまで生成しない。
- 仕様文の「超える」と6000px×6000pxの例が境界で異なるため、例を優先して36,000,000ちょうども確認対象にした。
- プレビューworkerは同時に1件だけ実行し、処理中の設定変更は最新1件だけを待機させる。revisionと入力パスを照合し、古い結果は表示せず画像を閉じる。
- 実出力、一括変換、プレビュー生成に共通lockを使い、高解像度処理の並列実行によるピークメモリ増加と競合を防いだ。
- プレビューOFF時は入力だけを表示し、実出力完了後も出力画像を自動表示しない。再チェック時は現在設定であらためて生成する。

### 今後同じミスをしないための有益な失敗

- スライダー変更ごとにworkerを新規起動すると、古い処理が残ったまま高解像度配列が並列に増える。debounceだけでは処理開始後を止められないため、単一workerと最新1件キューの両方が必要になる。
- 一時PNGを `Image.open()` したまま一時フォルダを閉じると、遅延読込の参照先が消える。コンテキスト内でグレースケール変換と `copy()` まで完了し、ファイルから切り離した画像だけをUIへ渡す。
- worker完了順だけで表示すると、倍率や入力を変えた後に古い画像が上書きする。要求revision、入力パス、ON/OFF、実出力中かをUIスレッドで再確認する。
- 実出力後の画像読込で入力fallbackを呼ぶ場合、通常の入力読込と同じ自動スケジュールを使うとプレビューが二重生成される。fallbackでは自動生成を明示的に抑止する。

### 検証

- 出力サイズ計算と36,000,000画素の境界、確認文面、はい・いいえ、再チェック、入力変更時の承認リセットをテストした。
- プレビューPNGの復号画素が同設定の実出力PNGと `np.array_equal` で完全一致することを確認した。
- pipelineが途中失敗した場合を含め、一時フォルダが残らないことを確認した。
- debounce、連続設定変更、実行中キュー、古い結果破棄、プレビューOFF、実出力後表示を回帰テストした。
- `python -m pytest` は200件成功し、`ruff check src tests` と `python -m pip check` も成功した。
- ソース版の `--check-config`、`--version`、`--check-ui` は終了コード0だった。
- 実画面でチェックが倍率メニュー右側に既定ONで配置されること、入力直後の左右プレビュー、明るさ変更後の更新を確認した。
- sample01の8倍で「縦8688px・横11584px」の確認を表示し、「いいえ」でチェック解除・入力のみ表示となること、再チェックで確認が再表示されることを確認した。
- フォルダ版 `dist/723UpScalerGUI/723UpScalerGUI.exe`（10,714,293 byte）と単体版 `dist/723UpScalerGUI.exe`（73,069,196 byte）を再ビルドした。両方の `--check-config`、`--version`、`--check-ui` はすべて終了コード0だった。

### ロードマップ状態

- フェーズ26についての未達成ロードマップは0件。
- ロードマップ内の作業はすべて終わりました。

## 2026-07-11 フェーズ27：GUI配布を単体EXEへ統一

### 方針変更

- 今後のGUI配布成果物は `dist/723UpScalerGUI.exe` の単体版だけとする。
- フェーズ23で維持するとしたフォルダ版は廃止し、onedirを再生成できるビルド分岐も削除する。
- 過去ログのonedir生成記録は当時の事実として保持し、本項目以降の方針を現行仕様とする。

### 改修内容

- `tools/build_gui_exe.ps1` から `-OneFile` スイッチと `--onedir` 分岐を削除し、引数なしで常に `--onefile` を渡すようにした。
- READMEからフォルダ版の配布案内と `-OneFile` 付きコマンドを削除し、通常コマンドが単体EXEだけを生成することを明記した。
- 依存・配布設計をonedir維持からonefile専用へ更新した。
- 旧onedir用 `723UpScalerGUI_updated.spec` を削除した。現行 `723UpScalerGUI.spec` はonefile構成である。
- 既存の `dist/723UpScalerGUI/`、`dist/723UpScalerGUI_fast/`、`dist/723UpScalerGUI_updated/` を削除した。

### 今後同じミスをしないための有益な失敗

- 配布方針だけをREADMEで変更しても、ビルドスクリプトの既定値がonedirならフォルダ版は再び生成される。不要な選択肢は説明で禁止するのではなく、スクリプトの分岐自体を削除する。
- 旧名のspecに `COLLECT` が残っていると、ビルドスクリプトを直してもspec直接実行でonedirを再生成できる。廃止した配布形式の生成定義も同時に削除する。
- Dropbox同期中のフォルダはプロセスが終了していても一時的にロックされ、最初の削除が一部だけ失敗することがある。対象の絶対パスとプロセス不在を確認し、ロック解放後に同じ限定パスだけを再試行する。

### 検証

- 引数なしの `tools/build_gui_exe.ps1` が成功し、73,070,465 byteの `dist/723UpScalerGUI.exe` を生成した。
- 単体EXEの `--check-config`、`--version`、`--check-ui` はすべて終了コード0だった。
- `dist/` からGUIフォルダ版3系統が消えていることを確認した。
- `python -m pytest` は200件成功し、`ruff check src tests` と `python -m pip check` も成功した。
- ビルドスクリプトに `OneFile`、`--onedir`、`BundleMode` の旧分岐が残っていないことを検索確認した。

### ロードマップ状態

- フェーズ27についての未達成ロードマップは0件。
- ロードマップ内の作業はすべて終わりました。

## 2026-07-11 フェーズ28：プレビュー視点保持・明るさ再マップ・製品名表示

### 改修内容

- 出力プレビューを差し替える直前に、表示倍率、ペイン中央が指す入力画像座標、パン位置を `PreviewViewState` として保存するようにした。
- 新しい出力倍率では、入力1pxあたりの画面表示倍率から出力px側の内部倍率を逆算する。倍率4→8では内部倍率を1/2にし、同じ入力位置・同じ見た目の拡大率を維持する。
- 明るさ変更のように出力寸法が同じ場合は、表示倍率とオフセットをそのまま復元する。初回プレビューと新しい入力だけは従来どおり全体表示する。
- ズームの上下限を出力画像px基準から入力画像px基準へ変更し、8倍から2倍などへ変更した場合も上限clampで表示倍率が変わらないようにした。
- 明るさスライダーを-10～+10の整数21段階へ変更した。SDF閾値は0.06～0.72を1段0.033で線形に割り当て、中央0は0.39とした。
- GUIタイトルとバージョン出力を「723モノクロ線画拡大ツール　0.10」へ変更し、`src/mlu/__init__.py` と `pyproject.toml` のバージョンを0.10へ同期した。

### 黒化原因と判断

- 従来の明るさ-9は `soft_sdf_threshold=0.00` だった。SDF support生成の `line_soft_hr >= threshold` は背景値0も含めて全画素trueとなるため、sample02が全面黒になっていた。
- sample02では閾値0.00のsupport面積率が1.000、0.06では約0.172だった。既存の正常出力実績もある0.06を新しい最低値とし、旧最大0.72までを連続線形に割り当てた。
- 2桁丸めでは各段が0.03と0.04で交互になり厳密な線形性を失うため、内部閾値は3桁で保持する。

### 今後同じミスをしないための有益な失敗

- 画像内容だけを更新する機能でも、共通の画像設定関数が毎回 `_fit_preview()` を呼ぶと利用者のズームとパンを破棄する。新規入力と同一入力の内容更新を分け、後者では視点を保存・復元する。
- 出力px座標の `preview_scale` をそのまま維持すると、出力倍率を変えたとき入力画像上の見た目の倍率が変わる。視点状態は倍率から独立した入力画像座標で持つ。
- SDF閾値0は数値範囲として有効でも、`coverage >= 0` という比較では背景を含む特殊値になる。スライダー端点は設定validatorだけでなく、実画像で最終出力を確認する。
- 表示範囲を広げる際に旧stepをそのまま使うと再び0へ到達する。安全な内部端点を先に決め、表示値全体を連続式でリマップする。

### 検証

- 明るさ-10～+10の21点が0.06～0.72へ0.033間隔で単調・線形に対応することを確認した。
- 入力座標の視点保存・復元、倍率4→8、深いズームでの8→2、同倍率での画像差し替え、古い画像のcloseをテストした。
- sample02を明るさ-10、2倍で実際のpreview pipelineへ通し、白画素が残り、黒画素率が50%未満であることを確認した。
- 全204テスト、`ruff check src tests`、`python -m pip check` が成功した。
- ソース版と単体EXEの `--check-config`、`--version`、`--check-ui` が成功した。
- 実画面でタイトル「723モノクロ線画拡大ツール　0.10」と、sample02の明るさ-10プレビューが全面黒にならないことを確認した。
- 単体版 `dist/723UpScalerGUI.exe` を再ビルドした。サイズは73,070,798 byte。

### ロードマップ状態

- フェーズ28についての未達成ロードマップは0件。
- ロードマップ内の作業はすべて終わりました。

## 2026-07-11 フェーズ29：既定明るさの暗め調整と段階操作ボタン

### 改修内容

- 新しい明るさ0をSDF閾値0.291とし、従来の明るさ-3と同じ出力設定にした。
- 新しい最大値+10を0.621とし、従来の明るさ+7と同じ設定まで最大値を切り下げた。
- 最低値-10は全面黒化を防いだ安全値0.060を維持した。
- -10～0は0.060～0.291を1段約0.0231、0～+10は0.291～0.621を1段0.033で結ぶ、0で連続する単調な区分線形にした。
- スライダー左右に残っていた固定表示「-9」「+9」を削除し、同じ位置へ30px角の「-」「+」ボタンを配置した。
- ボタンは1クリックで明るさを1だけ変更する。-10／+10では値をクランプし、変化がない場合はラベル更新やプレビュー生成を行わない。
- 両ボタンを倍率、スライダー、出力ボタンと同じ処理中無効化リストへ追加した。

### 今後同じミスをしないための有益な失敗

- スライダー定数を-10～+10へ変更しても、端の表示を固定文字で実装していると旧「-9」「+9」が残る。端値を表示する必要がない場合は操作ボタンにし、状態の唯一の表示を「明るさ: 値」へ集約する。
- 新しい-10を旧-10、新しい0を旧-3、新しい+10を旧+7へ合わせる3条件は、単一の直線では同時に満たせない。最低値を負のSDFへ落としたり平坦clampを作ったりせず、0で連続する2区間の線形補間を使う。
- 端値のボタン押下でも毎回プレビューを予約すると、画像が変化しないのに重い処理が走る。clamp後の値が現在値と同じならイベント処理を終了する。
- CTkButtonを処理中無効化リストへ入れ忘れると、出力中に設定だけ変更でき、表示値と処理設定が食い違う。新しい設定操作は必ず既存の制御リストへ登録する。

### 検証

- 新しい-10=0.060、0=0.291、+10=0.621であることと、範囲外入力のclampを確認した。
- 21値がすべて狭義単調増加し、正側10段が0.033刻みで従来-3～+7と一致することを確認した。
- 「-」「+」ボタンの1段操作、上下限での無更新、配置列、スライダーとの共通親、処理中無効化登録をテストした。
- 全205テスト、`ruff check src tests`、`python -m pip check` が成功した。
- ソース版と単体EXEの `--check-config`、`--version`、`--check-ui` が成功した。
- 実画面で旧「-9」「+9」が消え、スライダー左右へ「-」「+」ボタンが表示され、0→-1→0と1段ずつ操作できることを確認した。
- 単体版 `dist/723UpScalerGUI.exe` を再ビルドした。サイズは73,070,063 byte。

### ロードマップ状態

- フェーズ29についての未達成ロードマップは0件。
- ロードマップ内の作業はすべて終わりました。

## 2026-07-11 フェーズ30：単体EXEの配布最小化

### 調査結果

- 変更前 `dist/723UpScalerGUI.exe` は73,070,063 byteで、PE本体ではなくPyInstaller onefileアーカイブがほぼ全容量を占めていた。
- 主な圧縮後内訳は、未使用分を含むSciPy、NumPyとSciPyそれぞれのOpenBLAS、対応外AVIFデコーダ、DIPlib、Python/Tcl/Tkだった。
- `upx=True` はspecにあったが、ビルド環境にUPXがないため実際には一度も圧縮していなかった。onefileアーカイブ自体は既にzlib圧縮されており、速度・DLL破損・誤検知リスクを増やすUPXは導入しないと判断した。

### 改修内容

- GUIが受け付けないPillow AVIFデコーダと、SciPyのstats、optimize、spatial、integrate、interpolate、signalなど未使用サブパッケージをPyInstaller収集対象から外した。
- `scipy.ndimage._interpolation` がモジュール読込時に参照するだけで本アプリの使用APIでは呼ばない `scipy.special` を、凍結版runtime hookの空moduleで満たした。
- stockのSciPy hookが無条件収集するSciPy側OpenBLASを独自最小hookで止め、連鎖するspecial、linalg、sparseも除外した。実処理に必要なNumPy側OpenBLASは維持した。
- `tests/test_packaging.py` を追加し、ソースが使用できるndimage APIを現在の11種類へ固定した。将来 `rotate` などを追加した場合、凍結フックの再検討なしではテストを通さない。
- CustomTkinterの明示data収集をパッケージ全体からassetsだけへ狭め、pure Pythonコードの二重収録を解消した。
- ビルドへ `--noupx` を明示し、別の開発環境でPATH上にUPXがあっても無検証で適用されないようにした。
- GUIと同じexport configをmodule-level関数へ集約し、凍結EXE自身で代表画像を処理できる非公開 `--check-upscale INPUT OUTPUT` を追加した。
- `tools/collect_distribution_licenses.py` を追加し、CPython、Tcl/Tk、NumPy/OpenBLAS、SciPy、Pillow、PyYAML、CustomTkinter、darkdetect、DIPlib、packaging、PyInstallerの正規ライセンス原文をビルド時に検証・収集するようにした。原文が見つからない場合は配布ビルドを失敗させる。
- `THIRD_PARTY_NOTICES.md`、README、依存・配布設計、ロードマップを現行の単体EXE構成へ更新した。

### 今後同じミスをしないための有益な失敗

- specに `upx=True` と書くだけではUPXは適用されない。ビルドログとアーカイブ実測を確認せず、設定値だけで圧縮済みと判断しない。
- `from scipy import ndimage` を `import scipy.ndimage` へ変えるだけでは、今回のPyInstaller ModuleGraph収集量は変わらなかった。実測せずimport表記だけを最適化として残さない。
- `numpy.testing` を丸ごと除外すると、PyInstallerのNumPy hookが必要な `numpy.core._multiarray_tests` まで収集しなくなり、凍結EXEが起動時に `ModuleNotFoundError` で停止した。optionalに見える親packageを除外する前に、hookがhidden import判定へ利用していないか確認する。
- SciPy側OpenBLAS DLLだけを後処理で削除すると、special/linalgのネイティブ依存が残る。先に未使用import連鎖をruntime hookで切り、アーカイブに依存PYDがないことを確認してからstock hookの無条件DLL収集を置き換える。
- DIPlibだけの第三者告知では、実際のonefileに含まれるPython、NumPy、Pillow、Tkなどのbinary再配布条件を満たせない可能性がある。アーカイブ内訳の最小化とライセンス原文の棚卸しは同時に行う。

### 検証

- 単体EXEは33,977,278 byte（32.40 MiB）となり、変更前から39,092,785 byte、53.5%縮小した。
- `sample01` を明るさ0・4倍でソース版と単体EXEそれぞれ3回処理し、全6出力が371,543 byte、SHA-256 `213A910A583572101AD9F3022B0D0586A8BAD114B1E39F40A38CA52AE41F06E1` で一致した。復号配列も `np.array_equal` がtrue、最大画素差0だった。
- ソース版fresh processの3回は1.406、1.444、1.401秒で、変更前測定中央値1.490秒から悪化しなかった。
- 単体EXEの処理込み3回は5.985、4.025、3.027秒だった。onefileのcold extractionを含むため初回が長いが、変更前の起動だけの中央値約4.019秒に対し、縮小後の `--version` 中央値は3.310秒、`--check-config` は3.022秒、`--check-ui` は3.306秒となった。
- EXEだけを新しいOS一時フォルダへコピーし、作業ディレクトリにも他ファイルがない状態で `--version`、`--check-config`、`--check-ui` が各3回すべて終了コード0だった。
- 凍結EXEでpng、jpg、jpeg、tif、tiff、bmpを入力し、すべて128x96のL PNGへ正常変換した。
- アーカイブからSciPy側OpenBLAS、scipy.special/linalg/sparse、Pillow AVIFが消え、NumPy側OpenBLAS、DIPlib、line_only preset、第三者ライセンス14ファイルが残ることを確認した。
- 全208テスト、`ruff check src tests tools/collect_distribution_licenses.py`、`python -m pip check` が成功した。
- 最終EXEのSHA-256は `B2ED2D9954B75B900846E468A03C58412AACB5F581CC3A39805044F8FC75578E`。Authenticodeは未署名である。

### ロードマップ状態

- フェーズ30についての未達成ロードマップは0件。
- ロードマップ内の作業はすべて終わりました。

## 2026-07-11 フェーズ31：無料範囲のWindowsコード署名導入

### 調査と判断

- Microsoft公式では、自己署名証明書はテスト用途であり、他PCでは信頼されずSmartScreen上も未署名と同じstrong blockになる。利用者へ自己署名rootのinstallを求める運用は安全性を下げるため、本番EXEへの自己署名は採用しない。
- Sigstore/cosignは無料のprovenance証明として有用だが、通常はEXEと別のbundleを配り、Windows ExplorerやSmartScreenが認識する埋込Authenticodeではないため、単体EXE配布の署名代替にはしない。
- 公開OSSの条件を満たす場合、SignPath Foundationは無料で信頼済みAuthenticode証明書、HSM秘密鍵管理、timestamp、GitHub Actions連携を提供する。現時点のリポジトリにはremote設定がなく公開状態を確認できないため、外部申請を勝手に行わず、申請可能な署名工程とpolicyまでを実装した。

### 改修内容

- `config/windows_version_info.txt` を追加し、ProductName、FileDescription、CompanyName、version、original filenameをWindows version resourceへ埋め込んだ。
- `tools/AuthenticodeTools.psm1` を追加し、Windows SDKのx64 SignToolを解決し、各呼出しを60秒でtimeoutさせるようにした。
- `tools/sign_gui_exe.ps1` を追加した。Windows certificate storeのthumbprintで証明書を一意指定し、Code Signing EKU、private key、有効期間を検査してから、SHA-256 file digestとDigiCert RFC 3161 SHA-256 timestampで一時コピーを署名する。
- `tools/verify_gui_signature.ps1` を追加した。PowerShellとSignTool `/pa /all /tw` の両方でchain、全署名、timestamp、signer thumbprintを確認し、一時コピーの4096 byte位置を反転して `HashMismatch` になることも検証する。
- `tools/build_signed_gui_exe.ps1` を追加した。別名unsigned stageをビルド・署名・検証し、成功した場合だけ既存の配布EXEと同一volume上で置き換える。失敗時は既存成果物を維持する。
- signing scriptはPFXやpasswordを受け付けず、`.gitignore` に `*.pfx`、`*.p12`、`*.pem`、`*.key` を追加した。
- `docs/12_code_signing_policy.md` に署名対象、暗号要件、秘密鍵管理、承認分離、検証、privacy、SignPath Foundation申請手順をまとめた。
- `tests/test_packaging.py` にSHA-256、RFC 3161、thumbprint固定、tamper検知、SignTool timeout、staging、秘密鍵除外の回帰検査を追加した。

### 今後同じミスをしないための有益な失敗

- 自己署名をEXEへ付けるだけでは「署名済みの信頼された発行元」にはならない。署名の存在、hash整合性、signer identity、利用者PCでのchain trustを別々に検証する。
- 一時自己署名証明書をCurrentUser Rootへ `Import-Certificate` するとWindowsの確認UIで停止し、自動試験がtimeoutした。一般配布でroot installを要求しない方針とも一致するため、テストはtrust storeを変更せず、明示的な `AllowUntrustedRootForTest` でhash、signer、timestamp、tamperだけを検証する。
- PowerShell certificate providerの `EnhancedKeyUsageList.ObjectId` はこの環境ではOid objectではなく文字列だった。`.ObjectId.Value` と決め打ちすると正しいCode Signing証明書を拒否する。
- 子PowerShell script内で実行したSignToolの非0終了コードが呼出元の `$LASTEXITCODE` に残る。子scriptがテスト用untrusted chainを期待どおり拒否した後でも失敗扱いになったため、PowerShell script間はterminating errorで伝播し、古いnative exit codeを再判定しない。
- `[IO.File]::Replace` のbackup pathへ `$null` を渡すと、この環境では「path is empty」で失敗した。置換前ファイルの一時backup pathを同一directoryに作り、成功後に限定削除する。
- SignToolを `&` で直接呼ぶとtimestamp endpointや証明書UIで無期限に待つ可能性がある。Process APIで引数を個別に渡し、timeout時はprocess treeを停止する。
- 署名前にWindows version resourceを追加しなければ、署名後のresource編集で署名が無効になる。metadata、圧縮、ライセンス収集、検査を終えた最終バイト列だけを署名する。

### 検証

- 全209テスト、`ruff check src tests tools/collect_distribution_licenses.py`、`python -m pip check` が成功した。
- PowerShell parserで4本のps1と1本のpsm1にsyntax errorがないことを確認した。
- 一時的なRSA 3072bit、SHA-256、non-exportable Code Signing証明書でEXE一時コピーを署名した。DigiCert RFC 3161 timestamp chainを確認した。
- unsigned一時コピー33,979,482 byteに対し署名後は33,987,472 byteで、増分は7,990 byteだった。
- 署名後の一時コピーに対する1 byte改変は `HashMismatch` となり、SignToolも拒否した。
- 署名前後の `sample01` 4倍出力は同じ371,543 byte、SHA-256 `213A910A583572101AD9F3022B0D0586A8BAD114B1E39F40A38CA52AE41F06E1` で完全一致した。
- 署名後一時コピーの `--version`、`--check-config`、`--check-ui` はすべて終了コード0だった。
- テスト用証明書、private key、一時EXE、一時PNGが残っていないことを確認した。
- 再ビルドした本番EXEは33,979,482 byte、SHA-256 `AF9B9EBF54142268991F112DA4FD4F93A42787EE823385DC41E2B72484A2D557`。Windows version resourceは製品名0.10を表示し、署名状態は意図どおり `NotSigned` である。

### ロードマップ状態

- フェーズ31についての未達成ロードマップは残り1件。
- 次の作業予定は、公開リポジトリ化とSignPath Foundation審査・GitHub連携を完了し、最終EXEへ信頼済み署名を付けることです。

## 2026-07-11 フェーズ31：公開リポジトリ・SignPath連携準備

### 公開・ライセンス監査

- 空のDropbox reparse directoryだった`.git`を通常のGit repositoryとして`main` branchで初期化した。remote、commit、GitHub上のrepositoryはまだ作成していない。
- 公開候補からprivate key、token、API key、個人の絶対pathを検索し、実値は検出されなかった。生成`.spec`にはlocal pathが入るため、従来どおり`*.spec`をignoreし、force-addしない。
- `images/input/`、そこから作った`docs/assets/`、外部reviewとZIPを含む`reviews/`は、公開再配布のprovenanceを確認できないため`.gitignore`へ追加した。
- READMEとtestの実画像依存を、`examples/generate_synthetic_lineart.py`から作る再配布可能な`examples/synthetic_lineart.png`へ置換した。公開READMEの画像link切れも解消した。
- `PRIVACY.md`、`SECURITY.md`、`CONTRIBUTING.md`、`.gitattributes`、公開・SignPath手順、license監査文書を追加した。
- Apache-2.0本体と主要runtime依存は互換性がある。Potraceと外部upscalerは非同梱の別process CLIとして境界を明記した。

### 供給網と再現build

- Windows x64 / CPython 3.11のruntime・test・build wheelを`requirements-release.txt`へversionとSHA-256 hash付きで固定した。local wheelだけを使うoffline clean venvで全packageをinstallし、`pip check`と主要importに成功した。
- GitHub Actionsのcheckout、Python setup、artifact upload、SignPath submit、CodeQL、dependency reviewをtag参照ではなく確認済みcommit SHAへ固定した。
- 通常CI、CodeQL/dependency review、SignPath release workflowを追加した。release workflowはprotected `main`、既存tag、GitHub-hosted runner、GitHub environment、SignPath手動承認、unsigned artifact経由を必須にする。
- `.signpath/artifact-configuration.xml`でEXE名、ProductName、ProductVersion、FileVersion、CompanyName、copyright、OriginalFilenameを制約し、最終EXEだけへSHA-256 Authenticode署名する構成にした。
- `docs/12_code_signing_policy.md`のOIDC表現を修正した。公式ActionはSubmitter用API tokenを必要とし、GitHub App/connectorはsource・workflow・artifactの出所検証に使う。

### 配布物ライセンス修正

- PyInstaller解析で、`MSVCP140.dll`と`VCOMP140.DLL`をImageMagick install directoryから偶然取得していることを発見した。Visual Studio Installerの`vswhere.exe`で公式x64 Redistを解決し、Microsoft Authenticode署名、signer organization、CompanyNameを検証してから明示同梱するようbuildをfail-closed化した。
- `ImageMagick`由来のbinaryがPyInstaller解析へ現れた場合はbuildを失敗させる。Microsoft runtimeはSystem Libraryとして`THIRD_PARTY_NOTICES.md`へ記載した。
- NumPy test utility経由で不要な`win32pdh.pyd`と`pywintypes311.dll`が入っていたため、`win32pdh`をexcludeした。再build後のarchiveにpywin32 runtimeがないことを確認した。
- CustomTkinter同梱RobotoのGoogle copyright noticeとApache-2.0原文をEXE内license bundleへ追加した。
- wheel lock、Action SHA、公開asset除外、Roboto license収集、Microsoft runtime検証を`tests/test_packaging.py`で回帰検査するようにした。

### 今後同じミスをしないための有益な失敗

- Python packageのlicense一覧だけでは、PyInstallerがPATHから追加収集したDLLやoptional test moduleを見落とす。実archiveとAnalysis TOCも監査し、build host由来binaryの取得元を制約する。
- `PATH`上のDLLがMicrosoft署名済みでも、ImageMagick等の別製品directoryから偶然取得するbuildは再現可能な供給網ではない。署名だけでなく正規Redist rootとpublisherを同時に検証する。
- 短いtimeoutで親PowerShellを停止すると、子PyInstallerが一時的に残り`.pkg`をlockした。長時間buildは十分なtimeoutで起動し、失敗後はcommand lineを確認して自分のprocessだけを扱う。
- PyInstallerの`Analysis-00.toc`は長いpathを複数のPython stringへ折り返すため、完全pathの単純検索は正しいbuildを誤って拒否した。取得元の完全pathは生成specで検証し、TOCでは禁止directoryの混入を検査する。
- YAMLのplain scalar内に`--only-binary=:all:`を書くとcolonがmappingとして解釈されsyntax errorになった。commandはblock scalarへ入れ、workflow YAMLをparserで検証する。
- SignPath Foundationは公開OSSであるだけでなく、署名対象と同じ形式で既にrelease済みであること、担当role、MFA、手動承認、正確なpolicy文言を要求する。審査前にunsigned pre-releaseと実account linkを用意する。

### 検証

- 全212テスト、`ruff check src tests examples tools/collect_distribution_licenses.py`、`pip check`が成功した。
- GitHub workflow 3本をYAML parser、SignPath Artifact ConfigurationをXML parserで検証した。
- Microsoft公式Redist固定とpywin32除外後のonefile EXE buildが成功した。archiveにはRoboto notice/license、`msvcp140.dll`、`vcomp140.dll`が入り、pywin32とImageMagick由来binaryは入っていない。
- EXEの`--version`、`--check-config`、`--check-ui`、合成線画の`--check-upscale`が成功し、source版と画素完全一致した。
- 再build後のEXEは33,914,515 byte、SHA-256 `81F3AA1E90895CD8415872C746690240B3088479A19243FCF104C2720E04A09C`。ProductVersion `1.00`、FileVersion `1.00.0.0`、署名状態は意図どおり`NotSigned`である。
- 現在の公開候補はsecret scan済みで、権利未確定asset、build、dist、tmp、環境file、秘密鍵形式はignoreされている。

### ロードマップ状態

- フェーズ31についての未達成ロードマップは残り4件。
- 次の作業予定は、GitHub owner、repository名、Authors、Reviewers、Approversを確定し、public repositoryへ初回pushすることです。

## 2026-07-11 フェーズ32：バージョン1.00・初期プレビュー文言更新

### 改修内容

- `src/mlu/__init__.py` のアプリバージョンを1.00へ変更し、GUIタイトルとGUI `--version` 出力を同期した。
- `pyproject.toml` のproject versionを1.00へ変更した。
- Windows version resourceの数値versionを1.0.0.0、表示用ProductVersionを1.00、FileVersionを1.00.0.0へ更新した。
- 画像読込前のプレビュー文言を「入力画像または出力結果のプレビューがここに表示されます。」から「入力画像および出力結果のプレビューがここに表示されます。」へ変更した。
- 実GUIのCanvas itemから初期文言を取得して検証する回帰テストを追加した。
- READMEと受け入れチェックの現行バージョン表記を1.00へ更新した。過去の開発ログと過去フェーズの0.10記録は当時の履歴として維持した。

### 今後同じミスをしないための有益な失敗

- GUIタイトルの文字列だけを変更すると、package metadataとWindows Explorerに表示されるProductVersionが旧値のまま残る。アプリversion、pyproject、Windows version resourceを同時に更新する。
- ソース文字列の検索だけではCanvasに実際に描画された文言を保証できない。初期状態のCanvas item textをテストで取得し、利用者が見る文字列を直接検証する。
- version resourceはPyInstallerのビルド時に埋め込まれるため、設定ファイル更新だけでは既存EXEへ反映されない。必ず配布EXEを再ビルドする。
- Authenticode署名後にversion resourceを変更すると署名が無効になる。今回のようなversion更新は信頼済み署名工程より前に完了させる。

### 検証

- 全209テストが成功した。
- `ruff check src tests tools/collect_distribution_licenses.py` と `python -m pip check` が成功した。
- 単体EXEの `--version`、`--check-config`、`--check-ui` はすべて終了コード0だった。
- Windows version resourceはProductName「723モノクロ線画拡大ツール」、ProductVersion `1.00`、FileVersion `1.00.0.0` になった。
- `sample01` 4倍出力は371,543 byte、SHA-256 `213A910A583572101AD9F3022B0D0586A8BAD114B1E39F40A38CA52AE41F06E1` で従来と一致した。
- 再ビルド後の単体EXEは33,980,477 byte、SHA-256 `2BCF05AF2078D9814059D2DD9FCDF0AAABB5C52904243C1A883D4246ADCF8A8B`。信頼済み署名の外部審査前なので署名状態は `NotSigned` のままである。

### ロードマップ状態

- フェーズ32についての未達成ロードマップは残り0件。
- 公開準備後のコード署名フェーズ31についての未達成ロードマップは残り4件。
- 次の作業予定は、GitHub owner、repository名、Authors、Reviewers、Approversを確定し、public repositoryへ初回pushすることです。

## 2026-07-11 GitHub初回公開・SignPath提出前準備

### 改修内容

- 公開先を`https://github.com/nakashima723/723MangaUpscaler`、英語正式名を`723 Manga Upscaler`、配布EXE名を`723MangaUpscaler.exe`へ統一した。日本語GUIタイトルと処理アルゴリズムは変更していない。
- Python project metadata、Windows ProductName、FileDescription、InternalName、OriginalFilename、SignPath Artifact Configuration、署名script、README、privacy/notice文書を新名称へ同期した。
- single-maintainer projectとしてAuthors、Reviewers、Approversを`nakashima723`と明記した。署名提出主体はGitHub ActionsのCI user、手動承認主体は`nakashima723`のinteractive accountとし、別人を必須にしない方針へ修正した。
- SignPath release workflowは`SIGNPATH_SUBMISSION_ENABLED=true`が設定されない限りjob全体を実行しない。グレースケール対応など次回公開版の機能範囲を確定するまで、申請、GitHub App接続、署名要求を行わない。
- SignPath organization、project、signing policy、artifact configurationの実値はGitHub variablesから受け取るようにし、審査前の仮slugをhard-codeしない構成へ変更した。
- `CODEOWNERS`でworkflow、SignPath設定、dependency lock、build/signature scriptを重点管理し、DependabotはGitHub Actionsだけを月次確認するようにした。
- GitHub CLI 2.96.0の公式Windows x64 ZIPを取得し、公開SHA-256 `C2D6ACC935CD2F00E2144D7E036D5CD82E6B6BD5594E8C75AA75EF2A4ED6AAC3`と一致することを確認した。portable CLIから`nakashima723`へbrowser認証した。

### セキュリティ修正

- `workflow_dispatch`の`release_tag`、`product_version`、`file_version`をPowerShell本文へ直接展開すると、管理画面から任意PowerShellを注入できる問題を公開前監査で発見した。
- 手動入力はjob environmentへ渡して`$env:`経由で参照し、release tag、ProductVersion、FileVersionをstrict regexで検査するようにした。shell command本文へ`${{ inputs.* }}`を埋め込まない回帰testも追加した。

### 今後同じミスをしないための有益な失敗

- 署名workflowの手動入力はmaintainerだけが使う想定でも、shell sourceへ直接展開してはいけない。署名対象改変につながるため、environment経由とallowlist検証の両方を必須にする。
- この環境には`winget`がなく、GitHub CLIを通常installできなかった。公式immutable releaseのportable ZIPを使い、GitHub API記載digestを照合してから実行した。
- コマンドプロンプトの`start /wait`は今回のquoted pathを誤解釈し`Access is denied`となった。batch contextではGUI EXEを直接呼び出せば完了を待てるため、診断は`cmd /c dist\\723MangaUpscaler.exe ...`で実行する。
- Windows PowerShell 5.1は、このCodex環境の`PSModulePath`では`Microsoft.PowerShell.Security`をautoloadできなかった。build script自体の問題ではなく、Command PromptからPowerShell 7の`pwsh.exe -File`を呼ぶと正しく検証・buildできた。

### 検証

- 全212テスト、Ruff、`pip check`が成功した。
- 改名後の`723MangaUpscaler.exe`をone-file形式で再buildし、`--version`、`--check-config`、`--check-ui`、`--check-upscale`がすべて終了コード0となった。
- 合成線画に対するsource版とEXE版のPNGはbinary完全一致した。
- 改名後EXEのSHA-256は`48EAB4251C09104D106E52539C8FB71667BBAAAFF2E60FBD2837552DDC34FB31`、署名状態はSignPath審査前のため`NotSigned`である。

### ロードマップ状態

- コード署名フェーズ31についての未達成ロードマップは残り4件。
- 次の作業予定は、監査済み公開対象を`nakashima723/723MangaUpscaler`の`main`へ初回pushすることです。

## 2026-07-11 GitHub初回公開完了

### 公開結果

- 102ファイル、20,620行の初回commit `361ab9d`を作成し、公開repository `nakashima723/723MangaUpscaler`の`main`へpushした。
- GitHub repositoryはpublicで、既定branchは`main`になった。
- private vulnerability reporting、secret scanning、push protectionを有効にした。Issuesを有効、Wikiを無効にし、`manga`、`image-upscaling`、`line-art`、`windows`、`python`のtopicsを設定した。
- CI、CodeQL、Dependabotの初回GitHub Actions runが開始された。SignPath release workflowは`SIGNPATH_SUBMISSION_ENABLED`未設定のため実行されない。
- SignPath Foundationへの申請、GitHub App接続、SignPath organization/project/policy作成、API tokenやvariable設定、署名要求は行っていない。

### ロードマップ状態

- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、グレースケール対応など次回公開版の機能範囲を確定し、license再監査後にGitHub-hosted buildから同形式のunsigned pre-releaseを公開することです。

## 2026-07-11 初回GitHub CIのPNG再現検査修正

### 原因と修正

- 初回GitHub CIでは全212テスト、Ruff、依存検査、license収集まで成功し、最後の合成sample再現検査だけが失敗した。
- 従来検査はPNG file全体のbyte一致を要求していたため、local Python 3.11.2とGitHub runner Python 3.11.9のencoding/compression差まで失敗対象にしていた。これは描画画素やアプリ出力品質の差ではない。
- `examples/verify_synthetic_lineart.py`を追加し、commit済みPNGをdecodeしたmode、size、全pixel byteを保持してから再生成し、decode後の完全一致を検証するよう変更した。
- GitHub CIは上記scriptを実行し、PNG containerの圧縮表現ではなく、公開sampleの実画像内容を保証する。

### 今後同じミスをしないための有益な失敗

- 画質保証で重要なのはdecode後のpixelであり、PNG圧縮byteはPython patch、Pillow、zlib等の差で変わり得る。reproducible buildのbyte一致と画像品質のpixel一致を混同しない。
- byte-identical成果物が必要な場合はencoderとnative dependencyまで固定した別検査にし、画質回帰testとは分離する。

### 検証

- localで合成sample再生成前後のmode、size、全pixel byteが一致した。
- Ruff、全212テスト、`git diff --check`が成功した。

### ロードマップ状態

- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、GitHub CI成功を確認して`main`のforce push・削除禁止とrequired CI checkを設定することです。

### GitHub検証結果

- 修正commit `edcf8fa`のGitHub CIは、hash固定依存install、`pip check`、Ruff、全212テスト、license bundle収集、合成sampleのdecode後pixel完全一致をすべて通過した。
- 同commitのCodeQL security analysisも成功した。
- `main`保護では`test`と`codeql`をrequired status checksとし、branchを最新に保つこと、管理者を含むforce push禁止、branch削除禁止、conversation解決を必須にする。
- SignPath実申請、GitHub App接続、secret/variable設定、署名要求は引き続き実施していない。

## 2026-07-11 フェーズ33：相対線画・階調分離と3出力モード

### 改修内容

- `src/mlu/layer_separation.py` を追加した。半径6 source pxのグレースケールclosingで局所階調 `B` を推定し、入力輝度 `I` に対して `C=(B-I)/max(B,1/255)` を相対線濃度とする。
- weak相対差0.035・絶対差1/255、strong相対差0.12・絶対差3/255を初期値にし、strong seedをweak support内で8近傍伝播する。これにより黒100%固定ではなく、周囲の階調に対する暗化として線を扱う。
- `grayscale_processing.mode` に後方互換の `legacy` と、`line_only`、`separate`、`composite` を追加した。既定は従来画素を変えない `legacy` のままである。
- `separate` は主線画PNGに加え、拡大済み階調を黒RGB・`alpha=1-tone_luminance` とした `*_tone.png` を出力する。白背景へ合成すると階調を復元できる。
- `composite` は分離した階調を指定upscalerで拡大してから同じ線alphaを合成する。外部upscaler未指定時は階調枝だけLanczosを使う。
- GUIへ「階調の扱い」メニューを追加し、ライブプレビュー、単体出力、フォルダ一括出力へ凍結した選択値を渡すようにした。分離tone副出力も次回の一括入力から除外する。
- CLIの `upscale`、`inspect`、`batch`、`compare` へ `--grayscale-mode` を追加した。run JSONとbatch summaryへモード・副出力・分離診断値を残す。
- 新しい `scipy.ndimage.grey_closing` を配布最小構成の許可APIへ追加した。

### sample07での確認

- `images/input/sample07.png` は不透明RGBA 1448x1086で、既存I/Oによりグレースケール化して処理した。
- 2倍の `line_only`、`separate`、`composite` を `tmp/sample07_grayscale_modes/` に生成した。出力寸法は2896x2172。
- 全体線マスク率は従来35.40%から21.87%へ低下した。
- 暗い空ROI `(x=680..1099, y=10..249)` は、従来100%を線扱いしていたが、新方式では9.01%となった。空の階調面を除去しつつ、電線・電柱・建物線は線画出力へ残った。
- `line_only` と `separate` の主線画は同一処理で、透明階調レイヤーと合成出力は同じ線gammaを使う。

### 今後同じミスをしないための有益な失敗

- 絶対輝度thresholdを調整しても、暗いグラデーション面とその上の線は原理的に分けられない。線を局所背景に対する相対吸収率として扱う必要がある。
- モルフォロジーclosingは単調グラデーションの画像端でpadding由来の偽線を作る。外側の情報がないため、推定半径6pxの画像端は相対分離を抑制した。端に接する線の最初の6pxは既知のトレードオフである。
- `separate` の主出力だけ空いていても既存の `*_tone.png` があれば、先に主出力を書いてから失敗すると部分出力になる。副出力も書き込み前に予約・存在確認する。
- GUI一括出力の除外regexへ `_tone` を追加しないと、入力と出力を同じフォルダにした次回処理で透明階調PNGを入力として拾う。
- 新しいSciPy APIを追加した場合、ソーステストだけでなく最小PyInstaller構成のAPI allowlistと単体EXEを確認する。
- closing半径より太い黒ベタ、密集線、線と階調が完全同化した領域は一意に分離できない。透明階調レイヤーへ密集線の薄い残像が残る場合があり、現段階では設定調整対象とする。

### 検証

- Ruffが成功し、全223テストが成功した。
- 合成fixtureで同じ絶対グレー値の面/線判別、明暗階調をまたぐ乗算線、滑らかなグラデーション、完全同化時の非捏造を確認した。
- `separate` のtone PNGはRGBA、黒RGB、`alpha=1-luminance` で、白背景上の復元誤差が1/255以内である。
- `line_only` と `separate` の主線画一致、2レイヤー再合成と `composite` の差が量子化込み2/255以内、tone副出力の事前衝突検査を確認した。
- 単体EXEを再ビルドし、`--version`、`--check-config`、`--check-ui`、`--check-upscale` が終了コード0となった。
- EXEは33,924,212 byte、SHA-256 `A8E46C9F94CF7D3A80C7EBE453792564B63D9D654B173C161E16AC1F7DD68BC2`。SignPath審査前のため署名状態は `NotSigned` である。

### ロードマップ状態

- 相対線画・階調分離フェーズ33についての未達成ロードマップは残り0件。
- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、ユーザー目視結果に基づき、密集線残像と線幅の初期パラメータを調整することです。

## 2026-07-11 フェーズ34：グレー部分メニュー文言と相対モード線幅調整

### 改修内容

- GUI見出しを「階調の扱い」から「グレー部分の扱い」へ変更した。
- 選択肢を「線画と黒ベタのみ」「グレー部分を除去して線画のみ出力」「線画とグレー部分を分けて出力」「グレー部分を線画と合成して出力」へ変更した。内部識別子 `legacy / line_only / separate / composite` は維持した。
- 最長の日本語選択肢が欠けないよう、見出し幅を112px、プルダウン幅を300pxへ拡張した。
- `grayscale_processing.line_width_bias_source_px` を追加し、既定を `-0.75` source pxとした。SDFの既存 `width_bias_source_px` へ、非legacyの3モードだけ加算する。legacyとPotraceには適用しない。
- run JSONへ補正指定値、適用有無、実効SDF width biasを記録し、CLI表示も実効値を表示するようにした。
- README、設定例、CLI仕様、アルゴリズム設計、ロードマップを更新した。

### 線幅調整の検証

- sample07の2倍・`soft_sdf_threshold=0.22` で `0.0` から `-1.0` source pxまで比較した。
- `-0.75` では50%濃度の代表線幅中央値が6pxから4pxで正確に2/3、線占有面積が67.7%、面積/骨格長による幅指標が71.1%となった。骨格長は95.3%維持した。
- `-0.80` は50%輪郭が `-0.75` と同一だが残存線をさらに薄くし、`-1.0` は細線分断が増えたため、幾何幅を約2/3にする値として `-0.75` を採用した。
- GUI既定相当の閾値0.291でも50%線占有率67.5%、幅指標71.4%で、明るさ設定が変わっても同程度の補正になった。
- 補正後の `line_only` と `separate` 主線画は画素完全一致し、透明グレーレイヤーからの再合成と `composite` の差は最大1LSBだった。

### 今後同じミスをしないための有益な失敗

- 線の「濃さ」を総インク量だけで合わせると、輪郭幅が同じままエッジと芯だけを余計に薄くする場合がある。今回は利用者の指定が線幅なので、50%濃度輪郭、骨格、EDTによる代表幅を主指標にした。
- 固定SDF biasは代表幅を近似的に2/3へする補正であり、あらゆる元線幅を厳密な比例率で縮小するものではない。run JSONへ実効値を残し、後から素材別に調整可能にする。
- pipeline内だけで暗黙に実効biasを変え、run JSONへ元configだけを保存すると再現条件が分からない。指定補正値、適用有無、合算後の実効値を別々に記録する。
- 既定EXEを利用者がGUIとして起動中にPyInstallerを走らせると、最終EXE置換で `PermissionError: [WinError 5]` になる。利用者のプロセスは終了せず、別名のstaged EXEを生成して診断する。

### 検証

- Ruffが成功し、全225テストが成功した。
- GUI実体で見出し、既定表示、4選択肢を確認する回帰テストを追加した。
- 合成3px線の2倍出力で、補正なし6px、補正あり4pxを確認した。legacyは元のSDF biasを変更せず、相対3モードだけ加算するテストも成功した。
- `sample07_line_only_x2.png`、`sample07_separate_x2.png`、tone副出力、`sample07_composite_x2.png` を補正後の内容へ更新した。
- 起動中の既定 `dist/723MangaUpscaler.exe` は置換せず、`dist/723MangaUpscaler_updated.exe` をビルドした。`--version`、`--check-config`、`--check-ui`、`--check-upscale` はすべて終了コード0だった。
- staged EXEは33,925,792 byte、SHA-256 `C7C49019BC7C4192BDC58EECCAA3F03171AF2DA2B52B612EA4539349B5932C84`。SignPath審査前のため署名状態は `NotSigned` である。

### ロードマップ状態

- グレー部分メニュー文言・相対モード線幅調整フェーズ34についての未達成ロードマップは残り0件。
- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、起動中の旧GUIを閉じた後、staged EXEを既定の `723MangaUpscaler.exe` として再ビルドすることです。

## 2026-07-11 フェーズ35：グレー分離時の線画品質回復

### 原因と改修内容

- 旧相対モードは相対コントラストをweak/strong間の検出確信度へ変換し、その確信度をそのまま描画coverageへ使っていた。相対コントラスト0.12以上が即100% coverageになり、線量が近くても輪郭位置、接続、太さがlegacyと一致しなかった。
- 検出確信度 `line_probability`、tone除去用support、物理的な相対線alpha `C=(B-I)/max(B,tone_floor)`、SDF描画用coverageを別の値として扱うようにした。
- `quality_hybrid` を既定coverage方式として追加した。モルフォロジーclosing前の有効な局所背景をルーティング値とし、背景0.90以下では相対coverage、0.98以上ではlegacyの `line_soft`、中間ではsmoothstep補間する。
- 相対側coverageは物理alphaへ固定gain 2.425を掛ける。gainはSDF閾値から動的算出せず、GUIの明るさ操作とCLIのthresholdが線の採否へ引き続き作用するようにした。
- hybridが白地で拾った線もtone置換supportへ含めた。画像端ではborder抑制前の局所背景をtone目標へ使い、分離toneへの線残りとcompositeの二重線を防いだ。
- `grayscale_processing.line_width_bias_source_px` の既定を `-0.75` から `0.0` へ戻した。ユーザー指示どおり線品質の再現を優先し、負biasは追加で細くしたい素材だけの任意設定として維持した。
- run JSONへcoverage方式、固定gain、白地blend範囲、物理線alphaと描画coverageの統計を追加した。デバッグ出力へ相対線alpha、描画coverage、legacy blend weightを追加した。
- CLIの `inspect` も、任意の相対モード線幅biasを含む実効SDF biasを表示するよう統一した。

### sample07での品質評価

- `images/input/sample07.png` を2倍で再生成し、`tmp/sample07_grayscale_modes/` へ `line_only`、`separate`、tone副出力、`composite`、GUI明るさ0相当を保存した。
- 白背景のlegacy比較は、GUI既定threshold 0.291でprecision 99.9950%、recall 99.9952%、IoU 99.9902%だった。CLI既定threshold 0.22ではprecision 99.9903%、recall 99.9928%、IoU 99.9831%だった。
- 平坦グレー内部39,615 source pxでは、両thresholdともsource coverageとHR線alphaの偽線率は0%だった。階調矩形の硬い境界を含めると線候補が生じるため、急峻な階調境界を線と区別できない点は既知制約とする。
- `line_only / separate / composite` のHR線alphaは完全一致し、`line_only` と `separate` の主PNGも画素完全一致した。
- tone副出力を白上で復元して線PNGと乗算した結果は、floatのcompositeと完全一致した。8bit PNGでは最大1LSB、2LSB以上の差は0画素だった。
- 既定の追加線幅biasは0.0であり、今回の出力は従来の約2/3幅を目標にしたものではない。白地の線形状と細線接続をlegacyへ戻すことを優先した。

### 今後同じミスをしないための有益な失敗

- 線の検出確信度は線の物理濃度ではない。確信度をcoverageへ流用すると、strong閾値以上が一律に飽和し、線が膨張して輪郭品質が落ちる。検出、tone除去、描画の値を明示的に分離する。
- 3px線の50%輪郭だけで固定 `-0.75` source pxを選ぶと、二値化後SDFの量子化により1px斜線が方向依存で薄くなり、消える場合がある。代表幅だけでなく1px斜線の最大alpha、接続、legacy一致も必ず回帰確認する。
- coverage gainを現在のSDF閾値から逆算すると、利用者が明るさを変えても実効相対閾値が変わらず、GUI操作を相殺してしまう。gainは固定し、明るさ3点で出力面積の単調性を確認する。
- 白地のlegacy coverageを線枝だけへ混ぜても、tone除去supportへ含めなければcompositeで元線とSDF線が二重になる。3モードの線alpha一致だけでなく、画像端線のtone残像と再合成も確認する。
- モルフォロジー推定のborder抑制後の値だけで白地判定すると、画像端の線をlegacyへルーティングできない。線検出用の安全な推定値と、白地ルーティング用の推定値を分けて保持する。

### 検証

- Ruffが成功し、全231テストが成功した。`pip check`でも壊れた依存はなかった。
- 1px斜線のlegacy完全一致、GUI相当 -10/0/+10のSDF面積単調減少、画像端線のtone除去、3相対モードのHR線alpha完全一致を回帰テストへ追加した。
- `dist/723MangaUpscaler.exe` を再ビルドし、`--version`、`--check-config`、`--check-ui`、`--check-upscale` がすべて終了コード0となった。代表合成線画のEXE版とソース版は画素完全一致した。
- EXEは33,927,120 byte、SHA-256 `4B4582CB8EBC58BE2D27F42F7CB906ED5042188EC6FF199555E2B13937D5FBA8`。ProductVersionは1.00、FileVersionは1.00.0.0、SignPath審査前のため署名状態は `NotSigned` である。

### ロードマップ状態

- グレー分離時の線画品質回復フェーズ35についての未達成ロードマップは残り0件。
- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、次回公開版の機能範囲とlicenseを再監査し、GitHub-hosted buildから同形式のunsigned pre-releaseを公開することです。

## 2026-07-11 フェーズ36：未接続のグレー分離専用線幅補正削除

### 確認結果と改修内容

- `grayscale_processing.line_width_bias_source_px` はGUIへ接続されておらず、YAMLで指定した場合だけ非legacyのSDF幅へ加算する内部専用項目だった。既定は0.0なので通常出力へは作用していなかった。
- 上記専用設定を既定configとvalidationから削除し、非legacy時だけconfigを複製してSDF幅を加算する `effective_line_render_config` を削除した。
- pipelineは全モードで同じconfigをSDF rendererへ直接渡すようにした。既存の全モード共通 `sdf.width_bias_source_px` は、一般的なCLI・設定機能として維持した。
- run JSONから専用補正指定値、適用有無、合算後実効値を削除した。通常のSDF診断には共通width biasが引き続き記録される。
- 専用 `-0.75` 比較テスト、加算テスト、品質テスト内の不要な0.0指定を削除した。1px斜線、明るさ単調性、画像端線、3モード一致の品質回帰は維持した。
- README、設定例、CLI仕様、アルゴリズム設計から専用補正の現行説明を削除し、グレー分離には専用線幅biasを持たない仕様へ統一した。過去フェーズ34・35の記録は変更履歴として維持した。

### 今後同じミスをしないための有益な失敗

- GUIで利用者が操作できず、既定値では作用しない実験設定を「念のため」残すと、config、pipeline分岐、メタデータ、テスト、文書の保守対象だけが増える。採用しない調整経路は履歴へ残し、実行コードからは削除する。
- 共通SDF幅biasとグレー分離専用biasを併存させると、run JSONに指定値と実効値の両方が必要になり、どちらが線品質へ影響したか分かりにくい。線幅は共通設定、グレー分離はcoverage推定という責務へ分ける。

### 検証

- Ruffが成功し、全229テストが成功した。`pip check`でも壊れた依存はなかった。
- sample07のGUI明るさ0相当で `line_only / separate / composite` を再生成し、run JSONの `grayscale_processing` が `mode / tone_output_path / alpha_convention / separation` だけになったことを確認した。
- `dist/723MangaUpscaler.exe` を再ビルドし、`--version`、`--check-config`、`--check-ui`、`--check-upscale` がすべて終了コード0となった。代表合成線画のEXE版とソース版は画素完全一致した。
- EXEは33,926,465 byte、SHA-256 `E5FC688D7BFD04F99E4BA2F7427C5C3FBB86883E1A51B47BC3B6429674ED8A9D`。ProductVersionは1.00、FileVersionは1.00.0.0、署名状態は `NotSigned` である。

### ロードマップ状態

- 未接続のグレー分離専用線幅補正削除フェーズ36についての未達成ロードマップは残り0件。
- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、次回公開版の機能範囲とlicenseを再監査し、GitHub-hosted buildから同形式のunsigned pre-releaseを公開することです。

## 2026-07-11 フェーズ37：グレー分離レイヤーのPSD出力

### 改修内容

- GUIの「線画とグレー部分を分けて出力」を選択した場合だけ「PSDで出力する」チェックを表示し、既定ONとした。他の3モードでは非表示とし、利用者がOFFにした値はモードを切り替えて戻っても保持する。
- 単体・一括とも、処理開始時にPSD選択値をUI threadで確定してworker引数へ渡す。ライブプレビューは表示画素だけを確認するため常に一時PNGを使い、PSDを生成しない。
- GUIのPSD ONでは出力拡張子を `.psd` とし、同名が存在する場合は連番へ進む。OFFでは従来どおり主線 `.png` と `_tone.png` を予約する。
- `grayscale_processing.separate_output_format` に `png / psd` を追加した。CLI・YAML既定は後方互換のPNG、GUIはチェック既定ONを明示的にPSDへ変換する。CLIへ `--separate-output-format` を追加し、batchもPSD拡張子とsummary形式を扱う。
- `src/mlu/psd_output.py` に外部依存なしのPSD v1 writerを追加した。Grayscaleカラーモード、8/16 bits/channel、最大30,000px/辺、PackBits RLEへ対応する。
- PSDレイヤーは上から `Line Art`、`Grayscale Tone`、`Background` とした。線画とグレーは黒いgrayscale channelと透明度channel、背景は不透明白であり、すべてNormal表示したmerged imageは `tone * final_line` になる。
- pipelineはPSD ONで単一PSDだけを保存し、PNG sidecarを作らない。OFFでは従来の2 PNGを維持する。run JSONには出力形式とalpha規約を、batch summaryには出力形式を記録する。
- inspectとcompareは比較・debug画像をPillowで扱うため、設定ファイルがPSD指定でも一時出力だけPNGへ固定した。
- GUI/EXEの隠し診断 `--check-separate-psd` を追加し、配布物自身からPSDを生成できることを検査可能にした。

### sample07と互換性の検証

- `images/input/sample07.png` をGUI明るさ0相当、2倍で `tmp/sample07_grayscale_modes/sample07_separate_gui0_x2.psd` へ出力した。
- PSDは6,517,280 byte、2896x2172、8-bit Grayscale、document channel 1、レイヤー順は `Line Art / Grayscale Tone / Background` だった。
- Pillow、psd-tools 1.10.9、ImageMagickの3系統で再読込した。PSD merged imageと既存 `sample07_composite_gui0_x2.png` は最大差0で、全画素一致した。
- 16-bit小型fixtureもGrayscale depth 16、3レイヤーとしてpsd-toolsとImageMagickで再読込した。
- PSD OFFの既存PNG経路、主線PNGとtone PNGの命名、透明度、最大1LSB再合成は従来テストを維持した。

### 今後同じミスをしないための有益な失敗

- PillowはPSDを読み込めてもレイヤーPSDを書き出せない。環境に偶然入っていたpsd-toolsを未宣言のまま使うと、clean buildで失敗し、scikit-image等の依存とライセンスも増える。配布サイズを維持するため、必要なPSD v1機能だけを独立writerへ閉じ込めた。
- 最初のPackBits実装はliteral blockへ129 byte入る場合があり、制御byte `0x80` がNOPとして解釈された。小型画像のmerged previewは読めてもsample07のlayer channelが短く復号されるという有益な失敗だった。literalを必ず128 byte以下へ分割し、2896 byteの混在scanline round-tripテストを追加した。
- PSDのmerged imageだけが正しくてもlayer channelが壊れている可能性がある。merged画像を読むPillowに加え、layer channelを展開するpsd-toolsと、別実装のImageMagickでも検証する。
- PSD選択をworker内でTk変数から読み直すと、出力開始後のUI変更で一括jobの形式が混在し得る。scale、threshold、modeと同様に開始時点で値を凍結する。

### 検証

- Ruffが成功し、全239テストが成功した。`pip check`でも壊れた依存はなかった。
- 実GUI生成テストでチェックの文言、既定ON、separate時だけ表示、OFF値保持、処理中control管理を確認した。
- `dist/723MangaUpscaler.exe` を再ビルドし、`--version`、`--check-config`、`--check-ui`、`--check-upscale`、`--check-separate-psd` がすべて終了コード0となった。EXE生成PSDも8-bit Grayscale、3レイヤーとして再読込できた。
- EXEは33,935,013 byte、SHA-256 `CA0CE0D1E9677CA78BD4827951BA4C37CFFC6078473D8DD0B5C41C17A54EA75B`。ProductVersionは1.00、FileVersionは1.00.0.0、署名状態は `NotSigned` である。

### ロードマップ状態

- グレー分離レイヤーPSD出力フェーズ37についての未達成ロードマップは残り0件。
- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、次回公開版の機能範囲とlicenseを再監査し、GitHub-hosted buildから同形式のunsigned pre-releaseを公開することです。

## 2026-07-11 フェーズ38：更新版の公開・ライセンス再監査・SignPath申請前ゲート

### 監査と改修内容

- グレースケール相対分離、PNG分離出力、3レイヤーPSD出力を含む更新差分を公開対象として再監査した。新規コードは標準ライブラリと既存のNumPy、SciPy、Pillowだけを使い、新しいPython依存、Adobe SDK、追加codec、AI model、外部EXEを導入していない。
- 更新後のone-file EXE archiveと第三者通知を照合し、CPython、Tcl/Tk、NumPy/OpenBLAS、SciPy、Pillow、PyYAML、CustomTkinter、darkdetect、DIPlib、packaging、PyInstaller bootloader、Microsoft runtimeの収録物とライセンス原文に対応漏れがないことを確認した。
- 旧LICENSEはApache-2.0を名乗っていたが、patent termination、warranty、liabilityの一部を含む公式条項が欠落しており、GitHubも`NOASSERTION`と判定していた。GitHub公式Apache-2.0テンプレート全文へ置換し、正規化後の完全一致を確認した。
- `legacy`、`line_only`、`composite`で`.psd`を指定した場合に、PNGデータを誤った拡張子で保存できる問題を修正した。`separate + psd`は`.psd`だけ、その他は`.png`だけを処理開始前に受け付ける。
- GitHub-hosted build専用の`unsigned-prerelease.yml`を追加した。protected `main`とversion tagの一致、hash固定依存、Ruff、全テスト、ライセンス収集、one-file build、未署名状態、Windows metadata、PNG/PSDのソース版との画素一致を検証し、SHA-256付きの明確な未署名pre-releaseだけを公開する。SignPath token、slug、提出actionは含めていない。
- README、コード署名policy、公開手順、ライセンス監査記録を、更新版のPNG/PSD機能と「未署名pre-release公開、Foundation申請、審査承認後に実署名」という順序へ更新した。

### 今後同じミスをしないための有益な失敗

- ライセンス名と見出しが正しくても、本文を手作業で整形・短縮すると法的意味を持つ句が欠落し得る。OSIライセンス本文は公式テンプレートをそのまま使用し、GitHubのSPDX判定も公開後に確認する。
- 出力形式を追加したとき、writer側だけを分岐して拡張子を検証しないと、PNG bytesの`.psd`のような見かけ上成功する破損成果物を作れる。処理開始前にmode、format、suffixの組を検証し、誤った組のnegative testを持つ。
- Windows PowerShell 5.1の`PSModulePath`へPowerShell 7用moduleが先に入る環境では、`Get-AuthenticodeSignature`の自動importが失敗する。ローカル診断ではWindows PowerShell標準module pathを明示し、CIは隔離された`windows-2022` runnerで再検証する。
- PyInstallerのresource更新は一時的な`EndUpdateResourceW`エラーを返す場合がある。内蔵retryが成功したか最終終了コードと完成EXEのmetadataを確認し、警告1行だけで失敗と判断しない。

### 検証

- Ruff、全243テスト、`pip check`、`git diff --check`が成功した。
- 正規化したルートLICENSEがGitHub公式Apache-2.0本文と完全一致した。
- `dist/723MangaUpscaler.exe`を再ビルドし、`--version`、`--check-config`、`--check-ui`、`--check-upscale`、`--check-separate-psd`がすべて終了コード0となった。PNGとPSD統合画像はソース版と画素完全一致した。
- EXEは33,935,601 byte、SHA-256 `6EDA8F8FB38CF3DE1AB4040277C7C1BB3D372C8EB99AE32E80696F029B2C2E06`。ProductVersionは1.00、FileVersionは1.00.0.0、署名状態は`NotSigned`である。

### ロードマップ状態

- 更新版の公開前監査についての未達成ロードマップは残り0件。
- コード署名フェーズ31についての未達成ロードマップは残り3件。
- 次の作業予定は、更新版をprotected `main`へ反映し、GitHub-hosted buildからunsigned 1.00 pre-releaseを公開することです。
