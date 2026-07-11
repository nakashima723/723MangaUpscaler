# 05. 開発ロードマップ

MVPの確定スコープは `docs/00_mvp_scope.md` を正とする。

MVPでは白地黒線の純線画を対象にし、外部アップスケーラー、グレー階調保持、tone_source、バッチ、Potraceは必須にしない。まずフェーズ0〜4と、フェーズ7の最小パイプライン接続を完了させる。

## フェーズ0：リポジトリ初期化

### 目的

Codexが安全に実装を開始できる土台を作る。

### タスク

- `pyproject.toml` 作成
- `src/mlu` パッケージ作成
- `tests` 作成
- `README.md` 仮作成
- `ruff` / `pytest` 設定
- 型ヒント方針の決定（公開関数に型ヒント、配列値域はdocstring）
- ライセンス方針の決定（本体はApache-2.0候補）

### 完了条件

- `python -m mlu --help` または `mlu --help` が表示される。
- `pytest` が空でも通る。
- `ruff check` が通る。

## フェーズ1：画像I/OとCLI骨格

### 目的

実画像を読み、グレースケール化し、保存できる状態にする。

### タスク

- `io.py` に画像読み込み関数を実装
- `grayscale.py` にグレースケール正規化を実装
- `config.py` にYAML読み込みと設定マージを実装
- `cli.py` に `upscale`, `inspect`, `doctor` の骨格を作る
- MVP出力は8bit PNGを既定にする
- 16bit PNGとEXIF orientation対応を後続優先項目として設計に残す

### 完了条件

- 入力画像を読み、同じサイズのグレースケールPNGとして保存できる。
- `--invert` が動く。
- 設定ファイルとCLI引数がマージされる。
- 8bit PNGの基本テストがある。

## フェーズ2：線画マスク抽出MVP

### 目的

入力画像から線らしい領域を安定して抽出する。

### タスク

- `darkness = 1 - gray` 実装
- 固定閾値抽出
- Sauvola閾値抽出（MVP後のロバスト化）
- ヒステリシス接続
- 小連結成分除去
- 穴埋め
- `line_prob`, `line_mask`, `line_soft` 出力
- `inspect` コマンドでデバッグ画像を保存

### 完了条件

- 斜め線、円、建築線風の合成fixtureで線が抽出される。
- 固定閾値とヒステリシスで、薄いグレーを白へ飛ばし、十分暗い線を残せる。
- `debug_dir` に `line_prob.png` と `line_mask.png` が出る。
- 線マスク面積率がログに出る。

## フェーズ3：SDF線再レンダリング

### 目的

line_maskから高解像度のアンチエイリアス線アルファを生成する。

### タスク

- 距離変換でinside/outside距離を作る
- signed distance fieldを作る
- 高解像度へresizeしてscale倍補正する
- smoothstepでline_alpha_hrを生成
- 線幅補正パラメータを実装
- AA半径パラメータを実装
- `line_soft` 合成を実装
- SDFプレビューを保存

### 完了条件

- ニアレスト拡大より明確に滑らかな斜め線が出る。
- 線幅補正が正負に効く。
- `line_alpha_hr` のサイズが正しい。
- SDF単体テストが通る。

## フェーズ4：合成処理

### 目的

白キャンバスにline_alpha_hrを自然に合成する。

### タスク

- 黒線合成式の実装
- `line_darkness` 実装
- `edge_alpha_gamma` 実装
- アルファチャンネル復元は後続対応
- 出力clamp
- 白キャンバス合成モード

### 完了条件

- `upscaler=none` かつ `tone_source=white_canvas` で純線画2x/3x/4x/6x/8x出力ができる。
- 黒線の濃度が設定で変わる。
- 半透明エッジが破綻しない。

## フェーズ4.5：線画再レンダリング画質改善

### 目的

フェーズ4時点のSDF出力では、二値化した `line_mask` の階段状形状を高解像度化してしまい、長い斜線や浅い角度の水平線に元画像より強いジャギーが出る。これはユーザー確認で、waifu2x等の既存アップスケーラーより劣って見える重大な画質問題として扱う。

MVP後フェーズへ進む前に、元画像に含まれるアンチエイリアス由来のグレー濃度を捨てず、`line_soft` / coverage alphaとして高解像度レンダリングへ反映する。

### タスク

- `line_soft` を二値マスク補助ではなく、元画像の濃度coverageを残す情報として扱う
- SDF alphaと高解像度化した `line_soft` をブレンドするレンダリングモードを追加する
- `line_only` 既定を、二値SDF単独ではなくsoft coverage併用に変更する
- 長い浅角度線のジャギーが悪化しない合成fixtureを追加する
- debug出力とREADMEに、現時点ではsoft coverageが既定であることを反映する
- 後続候補として、中心線推定、直線/円弧フィット、Potrace比較を残す

### 完了条件

- 元画像のアンチエイリアス濃度が `line_alpha_hr` に反映される。
- 二値マスクSDF単独より、浅角度線の階段状ジャギーが弱くなる。
- 線幅補正やSDF設定を完全に捨てず、必要時に従来SDFモードへ戻せる。

## フェーズ4.6：建築線スタビライザー

### 目的

soft coverageだけでは、二値化由来の階段は弱まっても、建築背景に多い長い直線の微細な波打ちや段差が残る。長い直線候補だけを検出し、高解像度alpha上で控えめに幾何補正する。

### タスク

- Hough風の投票で長い直線候補を検出する
- PCAで線分端点、幅、RMS誤差を推定する
- 長さ、密度、RMS誤差で候補を絞る
- 高解像度alpha上に直線coverageを生成し、既存alphaへ限定的にblendする
- debug出力に幾何補正レイヤーを保存する
- run JSONに検出線分数を保存する
- 誤検出しやすい曲線、葉、短線、交差部を壊さないため、既定強度は控えめにする

### 完了条件

- 長い建築線fixtureで直線候補が検出される。
- 短線は補正対象にならない。
- 実サンプルでdebugの幾何補正レイヤーが出る。
- 既存のsoft coverage出力へ戻せる。

### 現状判断

ユーザー目視では、ジャギー抑制では強めのline stabilizerが有効だった。一方で、線分ごとの実支持点近傍だけに補正を制限しても、元画像に存在しない極細線が出る現象を完全には避けられなかった。この現象は実用上非常に困るため、現行line stabilizerはMVP既定として不採用にする。

コードとCLIは実験比較用に残すが、`line_only` 既定は `enabled: false` とする。再検討する場合は、幾何coverageを直接足す前に、support clamp、差分debug、交差点保護、曲線/カケアミ除外を先に実装する。

## フェーズ4.7：高解像soft SDFによるジャギー低減

### 目的

line stabilizerのように直線を推定して描き足す方式では、元画像にない極細線を生成するリスクがある。代替として、元画像由来の `line_soft` を高解像度化してからSDFを作り、source解像度の二値マスク階段を拡大しない線画レンダリングに切り替える。

### タスク

- `sdf.distance_source` を追加し、`binary_mask` と `soft_mask_hr` を選べるようにする
- `soft_mask_hr` では `line_soft` を高解像度化し、`soft_sdf_threshold` でsupportを作ってHR上で距離変換する
- `soft_mask_hr` では距離値へ `scale` を掛けない
- `line_only` 既定を `distance_source: soft_mask_hr` にする
- line stabilizer既定を `enabled: false` に戻す
- CLIで `--sdf-distance-source` と `--soft-sdf-threshold` を指定できるようにする
- 設定validationとSDF単体テストを追加する
- 実サンプルから目視確認用の比較画像を生成する

### 完了条件

- `line_soft` のsupportがない場所にSDF線を生成しない。
- 従来の `binary_mask` SDFへ切り替えて比較できる。
- `line_only` 通常実行で `line_stabilizer.enabled=false` がrun JSONに残る。
- `sample01` からbinary SDFとsoft SDFの比較PNGが生成される。

### 後続候補

- `soft_supersample`: `line_soft` を目標倍率より高く拡大してからarea downsampleし、soft alphaの階段をさらに抑える。
- `support_clamp`: `line_soft_hr` 由来support外でalphaが増えないようにする。
- `support_gated_edge_smoothing`: support内だけで軽いedge-preserving smoothingをかける。

## フェーズ5：tone_source生成（MVP後）

### 目的

Real-CUGANに渡す階調素材から線を軽く除去し、二重線を防ぐ。

### タスク

- line_mask膨張
- 背景ぼかし推定
- 線領域の白方向リフト
- 中間階調保護
- `tone_source` デバッグ出力
- 純線画検出の簡易判定

### 完了条件

- tone_source上で黒線が薄くなる。
- グレー影が白飛びしすぎない。
- `lift_strength` と `dilate_radius` が効く。
- 合成結果で二重線が軽減する。

### 現状

`white_canvas` / `passthrough` / `lift_lines` の `tone_source` 生成、設定validation、debug出力、run JSON診断値までは実装済み。外部アップスケーラーで `tone_source` を高解像度化し、最終合成で二重線軽減を確認する作業はフェーズ6へ回す。

## フェーズ6：外部アップスケーラー連携（MVP後）

### 目的

Real-CUGANなどのローカルCLIを安全に呼び出す。

### タスク

- 外部バイナリ存在確認
- 一時入力PNG保存
- subprocess呼び出し
- stdout/stderrログ保存
- tile-size指定
- Real-CUGAN adapter
- waifu2x adapter
- Real-ESRGAN adapter
- Lanczos fallback
- `doctor` コマンド実装

### 完了条件

- Real-CUGANパスが正しければtone_sourceを拡大できる。
- パスがない場合、わかりやすいエラーかfallbackになる。
- 外部コマンドラインがrun JSONに保存される。
- 失敗時stderrがログに残る。

### 現状

`none` / `lanczos` / `realcugan` / `waifu2x` / `realesrgan` adapter、`lanczos` fallback、外部コマンド実行、stdout/stderr/run JSON記録、`doctor` での外部ツール確認まで実装済み。実バイナリでの動作確認はユーザー環境依存のため、現時点の自動テストではsubprocess mockとLanczos fallbackで検証している。

ユーザー目視で、純線画に薄い `tone_hr` を重ねてもジャギー改善に寄与せず、グレー残渣として品質を下げることが確認された。そのため `composite.tone_usage: auto` を追加し、純線画判定時は `tone_hr` を最終合成に使わず白キャンバスへ戻す。強制比較したい場合だけ `always` を使う。

## フェーズ7：パイプライン統合

### 目的

単一コマンドで最終出力まで生成する。

### タスク

- `pipeline.py` で全処理を接続
- 一時ディレクトリ管理
- `debug_layers.py` 整備
- run JSON保存
- 出力名ルール
- overwrite制御
- 例外ハンドリング

### 完了条件

以下が動く。

```bash
mlu upscale input.png -o output.png --scale 4 --preset line_only --debug-dir debug
```

`output.png` とデバッグレイヤーが生成される。

## フェーズ8：バッチ処理（MVP後）

### 目的

複数背景素材をまとめて処理できるようにする。

### タスク

- [x] 入力ディレクトリ探索
- [x] 対象拡張子フィルタ
- [x] 出力パス生成
- [x] 失敗ファイルをスキップして継続
- [x] summary JSON/CSV出力
- [x] 逐次処理を既定にする

### 完了条件

- 10枚程度の画像を連続処理できる。
- 1枚失敗しても残りが続く。
- 処理結果サマリが出る。

### 現状

`mlu batch` を実装済み。既定対象は `png,jpg,jpeg,tif,tiff`、出力は `stem_x{scale}.png`、summaryは `summary.json` / `summary.csv`。`--workers` は受け付けるが、現時点では再現性優先で `1` のみ対応する。

## フェーズ9：品質比較支援（MVP後）

### 目的

実務でパラメータを詰めやすくする。

### タスク

- [x] `compare` コマンド
- [x] パラメータグリッド読み込み
- [x] 複数出力のコンタクトシート作成
- [x] 中央切り出し比較
- [x] 等倍・200%比較画像

### 完了条件

- 1枚の入力から複数設定の比較PNGが出る。
- 設定名が画像内またはファイル名でわかる。

### 現状

`mlu compare` を実装済み。`parameters` の直積または `variants` の明示列挙を読み込み、variant別出力、`contact_sheet.png`、`center_crop_1x.png`、`center_crop_200pct.png`、`compare-summary.json` を生成する。

## フェーズ10：Potraceオプション（MVP後）

### 目的

白地黒線が明確な素材で、ベクター化による滑らかな線出力を選べるようにする。

### タスク

- [x] PBM/BMP書き出し
- [x] Potrace CLI呼び出し
- [x] SVG出力
- [x] CairoSVGまたはInkscape CLIでPNG化
- [x] Potrace設定パラメータ対応
- [x] SDFとの比較出力

### 完了条件

- `--line-renderer potrace` が動く。
- Potrace未設定時は明確なエラーが出る。
- SVGとline_alpha_hrがdebugに保存される。

### 現状

`pipeline.line_renderer: potrace` / `--line-renderer potrace` を実装済み。PotraceでSVG化し、CairoSVGまたはInkscapeで目標サイズPNGにラスタライズして `line_alpha_hr` として使う。debugには `04_potrace.svg`、`05_line_alpha_hr.png`、`07_sdf_reference_line_alpha_hr.png` を保存する。外部ツール未設定時はSDFへfallbackせずエラーにする。

## フェーズ11：ドキュメント整備

### 目的

非エンジニアでも使える最低限の説明を用意する。

### タスク

- [x] Windows導入手順
- [x] Real-CUGAN導入手順
- [x] プリセット説明
- [x] よくある失敗例
- [x] サンプル画像での比較
- [x] ライセンス注意書き

### 完了条件

- READMEだけでMVPを試せる。
- 外部バイナリの導入ミスを `doctor` で発見できる。

### 現状

READMEにWindows導入、仮想環境作成、最小実行、プリセット、バッチ、比較出力、debugレイヤー、調整パラメータ、Potrace、Real-CUGAN導入、よくある失敗、ライセンス方針を集約済み。サンプル比較画像は `docs/assets/` に保存し、READMEから参照する。`doctor` はPython依存関係とReal-CUGAN/waifu2x/Real-ESRGAN/Potrace/CairoSVG/Inkscapeの設定状況を表示し、READMEでは `not configured` / `unavailable` の見方も説明する。受け入れチェックリストでは、実装済みの外部コマンド記録とユーザー環境依存の実バイナリ品質確認を分離した。

## フェーズ12：斜め線ジャギー低減

### 目的

SDFの既定出力で残る斜め線の階段状ガタつきを、元画像にない直線を描き足さずに低減する。

### タスク

- [x] SDF後の既存alphaに対する方向性スムージング
- [x] 水平・垂直線を主対象から外す角度gate
- [x] 既存alpha近傍だけに限定するsupport gate
- [x] 変更量の上限設定
- [x] CLI/configによる強度・半径調整
- [x] debug用の補正前alpha、適用重み、差分出力
- [x] 比較グリッド追加
- [x] 単体テストとpipeline/CLIテスト

### 完了条件

- 斜め線では方向性スムージングによるalpha変化が確認できる。
- 水平・垂直線への影響は限定的である。
- 旧line stabilizerのように検出直線を新規描画しない。
- ユーザーが `--disable-directional-smoothing` と強度指定で調整できる。

### 現状

`directional_smoothing` を追加した。構造テンソルで局所接線方向を推定し、候補角へ量子化せず、線の進行方向へ既存alphaを平滑化する。浅角度線の波打ちを避けるため、水平・垂直からの角度に応じた連続gateを使う。`config/grids/directional_smoothing.yaml` でoff/default/strong/diagonal_onlyを比較できる。`sample01` の比較画像は `docs/assets/sample_compare_directional_smoothing_*.png` に保存した。Potraceレンダラーでは適用しない。フェーズ14で浅角度線の副作用が確認されたため、MVP既定では無効化し、明示opt-inの実験機能に戻した。

## フェーズ13：浅角度線の波打ち抑制

### 目的

斜め線ジャギー低減の副作用として、水平に近い屋根線や電線に元画像にない大きな周期の波打ちが出る問題を抑える。

### タスク

- [x] 候補角量子化を廃止し、局所推定角そのものに沿ってサンプリングする
- [x] 浅角度線を急なON/OFFではなく連続重みで弱める
- [x] 既定の角度gateを保守側へ調整する
- [x] `full_strength_angle_from_axis_degrees` をconfig/CLIへ追加する
- [x] 浅角度線への影響が急斜線より小さいことをテストする
- [x] 屋根線付近の目視比較画像を再生成する

### 完了条件

- 水平に近い線ではdirectional smoothingの適用重みが小さい。
- より角度のある線では局所角に沿った平滑化が残る。
- 比較グリッドでoff/default/strong/diagonal_onlyを確認できる。

### 現状

`directional_smoothing` は `sampling_mode: local_angle` としてrun JSONへ記録される。既定値は `min_angle_from_axis_degrees: 20.0`、`full_strength_angle_from_axis_degrees: 34.0` とし、水平・垂直から20度未満の線には基本的に適用しない。`tmp/directional_smoothing_phase13/roof_compare/` に屋根線付近の比較画像を生成し、README用assetsも更新した。

## フェーズ14：line_soft起点の波打ち抑制

### 目的

浅角度の屋根線や電線に出る元画像由来ではない大きな周期の波打ちを、`line_soft` とsoft SDFの設計から抑える。

### タスク

- [x] Pro拡張レビューZIPを原本保管し、展開して参照可能にする
- [x] `mask.soft_coverage.mode` / `gamma` を追加する
- [x] `line_soft` の既定coverageを `darkness` に戻す
- [x] 旧挙動を `max_probability` として比較用に残す
- [x] `line_only` 既定を `soft_sdf_threshold: 0.22`、`soft_alpha_mode: none`、`soft_gain: 0.0` にする
- [x] `directional_smoothing` を既定OFFに戻す
- [x] debugに `line_soft_hr`、`soft_mask_hr`、`sdf_alpha_before_soft_mode_hr` を追加する
- [x] 浅角度線の回帰テストと比較グリッドを追加する
- [x] 屋根線付近の目視比較画像を再生成する

### 完了条件

- 旧 `max_probability` 系と現行 `darkness` 系の差を比較できる。
- run JSONに `mask.soft_coverage` とSDF診断情報が残る。
- debugレイヤーから `line_soft` 起点の波打ちを確認できる。
- `line_only` 既定で方向性スムージングとsoft alpha重ねが不要に有効化されない。

### 現状

レビューZIPは `reviews/wave_artifact_review_for_codex/` に保管した。`line_soft` は既定で元画像の黒さを使い、`line_prob` で持ち上げない。旧挙動は `mask.soft_coverage.mode: max_probability` で再現できる。`config/grids/wave_investigation.yaml` で旧挙動、現行候補、診断用 `line_probability` を比較できる。比較画像は `tmp/wave_soft_coverage_phase14/roof_compare/` と `docs/assets/sample_compare_wave_soft_coverage_*.png` に保存した。

## フェーズ15：support拡張による線太り切り分け

### 目的

`soft_sdf_threshold: 0.26` を固定し、ジャギー・波打ち低減とは別の線太り要因がどの程度効いているかを目視確認できるようにする。

### タスク

- [x] `soft_sdf_threshold: 0.26` 固定の比較グリッドを追加する
- [x] ヒステリシス弱線support拡張と小穴埋めを 0 / 1/3 / 2/3 / current で比較する
- [x] 屋根線付近の目視比較画像を生成する
- [x] 比較画像を `docs/assets/` に保存する

### 完了条件

- `support_fattening_0`、`support_fattening_1of3`、`support_fattening_2of3`、`support_fattening_current` を横並びで確認できる。
- 直接的な線幅補正 `width_bias_source_px`、soft alpha重ね、directional smoothing、line stabilizerは無効のまま比較する。

### 現状

`config/grids/support_fattening_isolation.yaml` を追加した。比較出力は `tmp/support_fattening_phase15/roof_compare/` と `docs/assets/sample_compare_support_fattening_*.png` に保存した。

## フェーズ16：weak support無効時のsoft SDF閾値比較

### 目的

ヒステリシスによるweak support拡張と小穴埋めを無効化した状態で、`soft_sdf_threshold` だけを変えたときの線幅・ジャギー・波打ちを目視確認できるようにする。

### タスク

- [x] `hysteresis.enabled: false`、`fill_holes_area: 0` 固定の比較グリッドを追加する
- [x] `soft_sdf_threshold: 0.26 / 0.30 / 0.34` の屋根クロップ比較を生成する
- [x] `sample01` 全体の個別PNGを3枚生成する
- [x] 比較シートを `docs/assets/` に保存する

### 完了条件

- weak support拡張と小穴埋めが無効な状態で、閾値ごとの結果を比較できる。
- クロップ比較だけでなく、`sample01` 全体の出力も確認できる。

### 現状

`config/grids/no_hysteresis_threshold_sweep.yaml` を追加した。比較出力は `tmp/no_hysteresis_threshold_phase16/roof_compare/` と `tmp/no_hysteresis_threshold_phase16/sample01_full/` に保存した。全体出力は `sample01_no_hysteresis_thr026.png`、`sample01_no_hysteresis_thr030.png`、`sample01_no_hysteresis_thr034.png` として個別確認できる。

## フェーズ17：Windows GUI exe

### 目的

CLIを使わずに、入力画像選択、倍率指定、`soft_sdf_threshold` 調整、プレビュー確認、出力フォルダ指定をGUIで行えるWindows exeを用意する。

### タスク

- [x] Tkinter GUIを追加する
- [x] 入力ファイル選択ボタンを追加する
- [x] 出力倍率を4倍既定、2/3/4/6/8倍選択にする
- [x] `soft_sdf_threshold` を0.34既定、0.04刻みのスライダーで調整できるようにする
- [x] 出力結果プレビュー、拡大・縮小、ドラッグ移動を実装する
- [x] 出力フォルダ指定と出力ボタンを実装する
- [x] 処理本体を6倍・8倍対応へ拡張する
- [x] PyInstallerでexeを生成する
- [x] exeの最低限の起動終了を確認する

### 完了条件

- `dist/723UpScalerGUI.exe` が生成される。
- GUIから単一画像を選択し、指定倍率・指定閾値でPNGを出力できる。
- 出力後にGUI内でプレビュー、ズーム、ドラッグ移動ができる。

### 現状

`src/mlu/gui.py` を追加し、`tools/build_gui_exe.ps1` で再ビルドできるようにした。PyInstallerビルド済みexeは `dist/723UpScalerGUI.exe`。未使用のpytest、matplotlib、Qt系を除外し、`config/` を同梱して `line_only` プリセットを読めるようにしている。

## フェーズ18：GUI exeのプリセット読込修正と入力プレビュー

### 目的

PyInstaller one-file exeで `line_only` プリセットを読めず出力に失敗する問題を修正し、出力前から入力画像をプレビューできるようにする。

### タスク

- [x] exe環境で同梱 `config/` を探索できるようにする
- [x] GUIの入力ファイル選択直後にプレビューを表示する
- [x] exe内プリセット読込を確認する診断引数を追加する
- [x] 修正版exeをビルドする
- [x] 修正版exeでプリセット読込を検証する

### 完了条件

- GUI exeから `line_only` プリセットを読み込める。
- 入力画像選択後、出力前にプレビュー領域へ画像が表示される。

### 現状

`repo_root()` はPyInstallerの `_MEIPASS` を優先して同梱 `config/` を探す。入力選択時にEXIF向きを反映したグレースケールプレビューを表示する。既存 `dist/723UpScalerGUI.exe` はユーザー環境で起動中のため上書きできず、修正版は `dist/723UpScalerGUI_fixed.exe` として作成した。

## フェーズ19：GUI左右比較プレビュー

### 目的

GUIで一度出力したあと、出力前画像と出力後画像を左右に並べ、同じ位置・同じ倍率で比較できるようにする。

### タスク

- [x] 出力前画像と出力後画像を別々に保持する
- [x] 出力後に左ペインへ出力前、右ペインへ出力後を表示する
- [x] 入力画像を出力倍率相当へ表示上スケールし、出力画像と座標を合わせる
- [x] 拡大・縮小を左右ペインで連動する
- [x] クリック＆ドラッグ移動を左右ペインで連動する
- [x] ペインごとに表示範囲を切り出し、画像が隣のペインへはみ出さないようにする
- [x] 通常名のGUI exeを再ビルドする

### 完了条件

- 出力後、左に出力前、右に出力後が表示される。
- ズームとパンで左右の表示位置が同期する。

### 現状

`src/mlu/gui.py` のプレビューを左右比較対応にした。`dist/723UpScalerGUI.exe` は再ビルド済みで、`--check-config` の確認も通過している。

## フェーズ20：長いストロークを単純化（本採用見送り・凍結）

### 判断

実サンプルの目視評価では、処理対象や補正を広くすると元画像の必要なディテールが崩れ、厳しく限定すると出力に有意義な改善がほとんど残らなかった。ディテール保持と有効なガタつき低減を両立する実用的な設定域を得られなかったため、本採用を見送り、このフェーズを凍結する。

実験コード、設定、比較画像、run JSON、debugレイヤーは調査記録として既定OFFのまま保持する。製品機能やGUIには追加せず、新しい原理の手法または明確な改善根拠が得られるまで追加調整を行わない。

### 目的

CLIP STUDIO PAINTの「ベクター線単純化」に近い考え方で、出力線画に残る微細なガタつきを、線の中心線を単純化してから再描画する方式として検討する。

現行パイプラインの本線はSDFで生成したラスタalphaであり、CSPのような制御点付きベクター線は保持していない。そのため、同等の処理を安全に行うには、出力後の黒線alphaから中心線を推定し、幅を再推定してラスタへ戻す新しい実験ブランチが必要になる。これは既存の線画検出やsoft SDFを置き換えるものではなく、既定OFFの後処理として扱う。

### タスク

- [x] `line_alpha_hr` から中心線を抽出し、枝分かれ、端点、閉曲線を扱う方法を調査する
- [x] 交差部、端点、短線、装飾、葉や複雑ディテールを単純化対象から保護する判定を設計する
- [x] 64 source px以上かつ角なし、直線性・線幅安定性を満たす枝だけに処理対象を厳しく限定する
- [x] 単純化後に成分の消失・分割・誤接続・新規生成・過剰な黒画素変化を検査し、危険な成分だけを自動ロールバックする
- [x] RDP制御点削減を廃止し、等弧長Gaussian低域通過による高周波ノイズ除去へ置き換える
- [x] 単純化した中心線に元の線幅を再付与し、元supportの局所近傍外へ新しい線を生成しないように再ラスタライズする
- [x] debugレイヤーに中心線、フィルタ後中心線、変位量、差分、保護領域を保存する
- [x] 比較グリッドと実サンプル出力を作り、波打ち低減とディテール欠落を目視確認できるようにする
- [x] 目視評価に基づき本採用を見送り、実験機能を既定OFFのまま凍結する

### 凍結により中止した項目

- Gaussian sigmaと幾何強度をUIで0から調整できる仕様の策定
- GUIへの「長いストロークを単純化」スライダー追加

### 評価条件

- 既定値0では既存出力と画素一致する。
- 補正値を上げた場合だけ中心線単純化が有効になる。
- 元画像にない長い細線や余分な線を生成しない。
- 細い電線、柵、窓枠を欠落させず、複雑ディテールでは過剰な単純化を避けられる。
- GUIの調整値、run JSON、debugレイヤーから適用内容を追跡できる。

### 現状

`src/mlu/centerline_simplification.py` に既定OFFの実験ブランチを追加した。ユーザー向け名称は「長いストロークを単純化」とし、内部キーは互換性のため `centerline_simplification` を維持する。Zhang-Suen thinning、8近傍グラフ追跡、等弧長Gaussian低域通過、高解像度alphaからの線幅再推定、局所support gate付き再ラスタライズを実装している。

現在は処理対象を、64 source px以上、半径2.25 source px以下、角なし、弦長/弧長比0.985以上、直線近似RMS 0.35 source px以下、最大偏差1.0 source px以下、線幅変動係数0.20以下、線幅P90/P10比1.50以下をすべて満たす枝に限定した。run JSONには条件別の拒否本数を、debugには `long_stroke_eligible_source` を保存する。

候補出力は8近傍の成分対応表と局所黒画素比0.80〜1.20で検査し、危険なsource成分の変更だけを元へ戻す。高周波フィルタ版の `sample01` では3成分を評価し、分割を起こした1成分を戻して2成分を採用した。候補の連結成分数396→397は最終396へ復元され、出力は0/255の完全二値を維持した。

`config/grids/centerline_simplification.yaml` でなし・弱・中・強を比較できる。`sample01` 全体の個別PNGと比較画像は `tmp/high_frequency_filter_phase20/sample01_full/` に保存した。30,891枝中79枝がgateを通過し、19〜32枝に実変位があった。最大変位は0.12/0.21/0.32 source px、黒画素変化は最大+0.013%、最終成分数は全variantで396だった。

初回比較では、supersampling後のLanczos coverageと小数 `strength` のalpha混合により、単純化variantだけにグレーのにじみが残った。現在は単純化有効variantを `strength: 1.0` に統一し、形状coverageを合成した後で `binary_threshold: 0.50` により最終alphaを完全二値化する。再生成した `sample01` 全体4枚はすべて画素値0/255のみで、グレー画素0件を確認済み。

旧RDP方式は制御点削減による長い曲線の多角形化とディテール破壊が避けられないため、実行経路と制御点削減統計を削除した。Gaussian方式は密な中心線点数を維持して短周期の法線変位だけを減衰させたが、適用を広げた場合のディテール破壊と、限定した場合の効果不足というトレードオフは解消できなかった。評価条件を満たさないため、本採用とGUI追加を見送り、フェーズ20を凍結した。

## フェーズ21：配布GUI向け表示・出力整理

### 目的

内部パラメータ名をユーザーへ直接見せず、配布用GUIでは直感的な整数の「明るさ」として調整できるようにする。また、通常出力を最終PNGだけにし、パラメータJSONはデバッグ時だけ生成する。

### タスク

- [x] GUIの `soft_sdf_threshold` 表示を「明るさ」へ変更する
- [x] 明るさを-9から+9の整数値とし、0を内部閾値0.36、1段階を0.04へ対応させる
- [x] 通常のGUI・CLI・バッチでは `.mlus-run.json` を生成しないようにする
- [x] `--save-run-json`、`--debug-dir`、`inspect`、`compare` ではデバッグ用JSONを生成できる状態を維持する
- [x] 回帰テスト、利用文書、配布用GUI exeを更新する

### 完了条件

- GUI初期表示が「明るさ: 0」で、内部の `soft_sdf_threshold` は0.36になる。
- GUIのスライダー表示範囲が-9から+9で、上下限の内部値が0.00と0.72になる。
- 通常出力ではPNG以外の画像別パラメータJSONが生成されない。
- 明示的なデバッグ処理では従来どおりJSONを取得できる。

### 現状

GUI表示と内部閾値の変換を分離し、通常処理の `debug.save_run_json` 既定値をfalseへ変更した。CLIには `--save-run-json` を追加し、デバッグディレクトリ指定時と `inspect`、`compare` では実行記録を維持する。バッチの `summary.json` と `summary.csv` は処理結果サマリであるため通常時も生成する。更新版は `dist/723UpScalerGUI_updated.exe` としてビルド・起動検証済み。通常名の旧exeはユーザーが2プロセス起動中だったため、強制終了や上書きは行っていない。

## フェーズ22：CustomTkinterによるGUI外観改善

### 目的

既存の画像処理と同期プレビュー操作を維持しながら、配布GUIをCustomTkinterへ移行し、操作のまとまり、余白、ボタン寸法、文字揃え、配色を実用ソフトとして一貫した見た目へ改善する。

### タスク

- [x] ルート、設定欄、ボタン、倍率選択、明るさスライダーをCustomTkinterへ移行する
- [x] 入力画像・出力先・画質設定を上部の設定パネルへ整理する
- [x] 拡大・縮小・全体表示をプレビューツールバーへ移し、寸法と中央揃えを統一する
- [x] 処理中に無効化するウィジェットを明示管理し、プレビュー操作は維持する
- [x] 依存関係とPyInstallerビルドをCustomTkinterのデータ同梱に対応させる
- [x] 全テスト、静的検査、GUI目視確認、配布ビルドを実施する

### 完了条件

- ボタン文字が中央に揃い、主要ボタンと補助ボタンの視覚的優先度が区別される。
- 入力・出力パス、倍率、明るさ、出力操作が安定した寸法と余白で配置される。
- 既存の入力プレビュー、左右比較、同期ズーム、同期パンが維持される。
- CustomTkinterのテーマデータを含むWindows配布物からGUIを起動できる。

### 現状

白とニュートラルグレーを基調に青を主操作へ限定したCustomTkinter UIへ移行した。設定は上部パネル、表示操作はプレビューツールバーへ整理し、ボタン高34〜42px、角丸6〜8px、外側余白16pxへ統一した。プレビュー描画には既存のTk Canvasと `ImageTk.PhotoImage` を継続使用する。`dist/723UpScalerGUI/723UpScalerGUI.exe` はビルド・起動検証済み。

## フェーズ23：CustomTkinter GUIの単体EXE配布

### 目的

フォルダ版を安定版として維持しながら、利用者が `723UpScalerGUI.exe` 1ファイルだけを配布・実行できるポータブルビルドを用意する。

### タスク

- [x] ビルドスクリプトへ `-OneFile` オプションを追加する
- [x] CustomTkinter本体、テーマJSON、フォント、プリセット設定をonefileへ同梱する
- [x] frozen exe内部でCustomTkinterウィンドウを生成する `--check-ui` を追加する
- [x] 単体EXEで設定読込、バージョン、UI生成を検証する
- [x] READMEと開発ログへ単体版とフォルダ版の使い分けを記録する

### 完了条件

- `dist/723UpScalerGUI.exe` だけを別環境へ渡せる。
- 単体EXEがCustomTkinterのテーマデータを一時展開し、UIを生成できる。
- 従来の `dist/723UpScalerGUI/` フォルダ版も再ビルドできる。

### 現状

PyInstallerの `--onefile` と明示的なCustomTkinterデータ同梱を組み合わせ、73,489,142 byteの `dist/723UpScalerGUI.exe` を生成した。単体EXEの `--check-config`、`--version`、`--check-ui` はすべて終了コード0だった。起動時には依存データを一時ディレクトリへ展開するため、初回起動に約4秒かかる。

## フェーズ24：出力完全一致を維持する高速化

### 目的

既定の線画アップスケール品質と出力画素を一切変えず、SDF距離変換、無効機能の中間配列、二値線の合成、source解像度のマスク処理に残る不要コストを削減する。

### タスク

- [x] 実サンプルを段階計測し、高解像度SDF距離変換を主要ホットスポットとして特定する
- [x] smoothstepが完全飽和する条件を導出し、通常出力で不要なEDTを省略する
- [x] 条件外では内側・外側のうち必要なEDTだけを計算する
- [x] Apache-2.0のDIPlib 3.6.1系列を導入し、SciPy参照距離とのfloat32完全一致を検証する
- [x] 二値alphaと白キャンバスの条件下で合成を`1 - alpha`へ厳密に短絡する
- [x] 無効な補正機能の高解像度zero配列を通常経路で生成しない
- [x] 純線画判定の固定半径膨張と小穴埋めを完全一致する単一pass処理へ置き換える
- [x] ランダム、境界、全倍率、AA、線幅bias、soft mode、空・全面maskで完全一致を回帰検証する
- [x] DIPlib DLLとApache-2.0告知を含むGUI配布フォルダをビルドし、起動検証する

### 完了条件

- `sample01` 4倍の通常出力で、変更前のfinal float32、復号PNG画素、PNG SHA-256が一致する。
- デバッグ・run JSON経路でも完全なSDF診断を保持し、通常経路と最終出力が一致する。
- 既定条件外では従来と同じalphaを生成し、必要な距離側だけを計算する。
- 全テスト、静的検査、配布exeの`--check-config`と`--version`が成功する。

### 現状

既定 `line_only` は高解像度EDT 2回を省略し、条件外では必要な側だけをDIPlibのexact separable EDTで計算する。`sample01` 4倍のwarm中央値は変更前8.234秒から0.884秒へ短縮し、約9.3倍となった。peak working setは1384.4MiBから664.4MiBへ約52%減少した。変更前後のfinal float32とPNG SHA-256は完全一致し、完全SDF診断を保持する経路も中央値0.933秒で同じ最終画素を維持した。

`dist/723UpScalerGUI_fast/723UpScalerGUI_fast.exe` はDIPlibの`DIP.dll`、本体LICENSE、第三者告知を含むonedir配布として生成し、`--check-config`と`--version`の終了コード0を確認した。

## フェーズ25：GUIのフォルダ一括変換

### 目的

単一ファイル変換を維持しながら、GUIでフォルダ直下の対応画像を条件指定してまとめて変換できるようにする。

### タスク

- [x] 入力ファイル選択の横へ「フォルダを指定して一括変換」ボタンを追加する
- [x] フォルダ時だけファイル名部分一致チェック、入力欄、拡張子メニューを表示する
- [x] 空白・Windows禁止文字だけの検索語を無効扱いにし、拡張子と有効な検索語をAND条件で適用する
- [x] 対象枚数の確認でOKされた場合だけ、確定済み一覧を順次変換する
- [x] 同じstemの入力や既存出力があっても出力名が衝突しないようにする
- [x] 対象の先頭1枚だけを入力・出力比較プレビューへ使用する
- [x] 途中の1枚が失敗しても残りを継続し、成功・失敗数を通知する
- [x] 回帰テスト、利用文書、配布用GUI exeを更新する

### 完了条件

- フォルダモード時だけ追加条件が表示され、文字列チェックは既定OFFになる。
- `png, jpg, jpeg, tif, tiff, bmp` の全対応形式または選択した1形式だけを対象にできる。
- ファイル名条件と拡張子条件の両方を満たすファイルだけが確認枚数と実処理対象になる。
- キャンセル時は変換せず、OK時は表示枚数と同じ確定済み一覧を処理する。
- プレビューと左右比較に使用する画像は、決定的に並べた対象一覧の先頭1枚だけになる。

### 現状

GUI一括変換は選択フォルダ直下を対象とし、対応形式すべてまたは拡張子1種類へ絞り込める。任意のファイル名条件はWindows禁止文字を除いた有効部分で大文字小文字を区別せずに照合する。自動出力先は入力内の専用サブフォルダとし、入力自身を出力先に明示してもGUI生成名のPNGは再入力しない。確認後は対象一覧を固定して同じ設定で順次処理し、出力名を予約して衝突を避ける。処理失敗は個別に記録して残りを継続し、先頭画像だけをプレビューする。

## フェーズ26：実出力一致のリアルタイムプレビュー

### 目的

変換本体の出力品質と画素を変えず、入力選択直後および倍率・明るさ変更時に、現在設定での実出力と同じ画像をGUI内へ安全にプレビューする。

### タスク

- [x] 出力倍率メニュー右側へ既定ONの「プレビューを表示する」チェックボックスを追加する
- [x] 単一入力とフォルダ入力の先頭画像を読み込んだ直後に、現在設定の出力プレビューを生成する
- [x] 倍率・明るさ変更をdebounceし、最新設定のプレビューへリアルタイム更新する
- [x] 実出力と同じpipelineを一時フォルダ上で実行し、復号画素をコピーしてから一時出力を確実に削除する
- [x] 出力が36,000,000画素以上になる入力では初回生成前に確認し、「いいえ」で再チェックまで停止する
- [x] ワーカーを単一実行に限定し、処理中の複数変更は最新1件だけを待機させ、古い結果を表示しない
- [x] 実出力とプレビュー生成を同じlockで直列化し、同時実行によるメモリ増加と競合を防ぐ
- [x] 画素一致、一時削除、境界値、確認、debounce、最新結果、GUI配置の回帰テストを追加する
- [x] README、受け入れチェックリスト、開発ログ、配布用GUIを更新する

### 完了条件

- チェックONで入力を選ぶと、実際のPNGを復号した画素と完全一致する左右比較プレビューが自動表示される。
- 倍率・明るさを変更してもプレビューworkerが並列に増えず、最後の設定だけが表示される。
- 36,000,000画素以上では入力ごとの初回だけ確認し、「いいえ」後はチェックを再びONにするまで処理しない。
- プレビュー用ファイルが指定出力先や一時領域へ堆積しない。

### 現状

`src/mlu/gui.py` に一時出力を使う実出力一致プレビュー、200ms debounce、単一worker、最新1件待機、revisionによる古い結果の破棄、実出力との共通lockを実装した。36,000,000画素以上は縦横サイズを示して確認し、「いいえ」でチェックを外す。単体・フォルダ先頭入力、倍率、明るさ、出力後表示を同じON/OFF状態へ統合した。自動テスト200件、静的検査、ソース版診断、実画面操作を通過した。フォルダ版 `dist/723UpScalerGUI/723UpScalerGUI.exe` と単体版 `dist/723UpScalerGUI.exe` を再ビルドし、両方の `--check-config`、`--version`、`--check-ui` が終了コード0となった。

## フェーズ27：GUI配布を単体EXEへ統一

### 目的

GUIの配布・更新対象を単体EXEだけに統一し、フォルダ版の誤生成、誤配布、旧成果物との混同を防ぐ。

### タスク

- [x] `tools/build_gui_exe.ps1` を引数なしで常にPyInstaller onefileを生成する仕様へ変更する
- [x] `-OneFile` スイッチとonedir分岐を削除する
- [x] READMEと依存・配布設計を単体EXE専用へ更新する
- [x] 旧onedir用specと既存のフォルダ版配布成果物を削除する
- [x] 単体EXEを再ビルドし、設定読込、バージョン、UI生成を検証する

### 完了条件

- 通常のビルドコマンドが `dist/723UpScalerGUI.exe` だけを生成する。
- リポジトリの `dist/` にGUIフォルダ版が残っていない。
- 単体EXEの `--check-config`、`--version`、`--check-ui` が成功する。

### 現状

フェーズ23で併存させたフォルダ版の方針は、本フェーズの決定により廃止した。過去のロードマップ・開発ログにあるonedir生成記録は当時の履歴として残すが、今後の配布とビルドはonefileだけを正とする。旧フォルダ版 `dist/723UpScalerGUI/`、`dist/723UpScalerGUI_fast/`、`dist/723UpScalerGUI_updated/` と旧onedir用specを削除した。引数なしのビルドで73,070,465 byteの `dist/723UpScalerGUI.exe` を生成し、3種類の診断がすべて終了コード0となった。

## フェーズ28：プレビュー視点保持・明るさ再マップ・製品名表示

### 目的

リアルタイムプレビューの更新前後で利用者が見ている箇所と表示倍率を維持し、SDF閾値0.00による全面黒化を防ぎながら明るさ範囲を-10～+10へ拡張する。GUIタイトルを製品名とバージョンへ統一する。

### タスク

- [x] プレビュー更新前の中心座標と表示倍率を入力画像座標で保存する
- [x] 出力倍率変更後の座標系へ表示状態を逆変換し、明るさ変更時も同じ視点を復元する
- [x] ズーム上限を入力画像座標基準へ統一し、倍率間の往復で表示倍率が変わらないようにする
- [x] 明るさを-10～+10、SDF閾値を0.06～0.72へ連続線形マップする
- [x] sample02の最低明るさプレビューが全面黒にならない回帰テストを追加する
- [x] GUIタイトルを「723モノクロ線画拡大ツール　0.10」へ変更し、パッケージバージョンを同期する
- [x] README、受け入れチェックリスト、開発ログ、単体EXEを更新する

### 完了条件

- 明るさ変更では表示倍率とオフセットが変化しない。
- 出力倍率変更では、入力画像上の中心座標と1入力pxあたりの表示倍率が変化しない。
- 明るさ-10の内部閾値が0より大きく、sample02が全面黒にならない。
- スライダーが整数21段階、タイトルとバージョンが指定どおり表示される。

### 現状

プレビュー視点を出力pxではなく入力画像座標の中心と表示倍率として保存・復元するpure helperを追加した。出力倍率に依存していたズーム境界も入力座標基準へ変更した。明るさは1段0.033の線形対応で、-10=0.06、0=0.39、+10=0.72となる。バージョンは0.10へ更新した。全204テスト、静的検査、依存検査、実画面確認を通過し、73,070,798 byteの単体版 `dist/723UpScalerGUI.exe` を再ビルドした。

## フェーズ29：既定明るさの暗め調整と段階操作ボタン

### 目的

既定出力が元画像より明るくなりすぎる傾向を抑え、従来の明るさ-3相当を新しい既定値、従来の+7相当を新しい最大値にする。旧端値ラベルを、1段階ずつ操作できるボタンへ置き換える。

### タスク

- [x] 新しい明るさ0を従来-3相当のSDF閾値0.291へ変更する
- [x] 新しい明るさ+10を従来+7相当のSDF閾値0.621へ切り下げる
- [x] 安全な最低値0.060を維持し、全域を連続・単調な区分線形で対応させる
- [x] 旧固定表示「-9」「+9」を削除する
- [x] 同じ位置へ「-」「+」ボタンを配置し、明るさを1ずつ変更できるようにする
- [x] 上下限では値とプレビュー要求を増減させず、出力処理中は両ボタンを無効化する
- [x] 回帰テスト、README、受け入れチェックリスト、開発ログ、単体EXEを更新する

### 完了条件

- 明るさ0が0.291、+10が0.621、-10が0.060になる。
- -10～+10の21値がすべて狭義単調増加し、0の前後で不連続にならない。
- 「-」「+」ボタンがスライダーの左右に表示され、1クリックで1段階だけ変化する。
- 端値でボタンを押しても不要なプレビューを生成しない。

### 現状

新しい負側は0.060～0.291を1段約0.0231、正側は0.291～0.621を1段0.033で結ぶ区分線形とした。これにより新しい-10は従来-10、0は従来-3、+10は従来+7と一致する。旧端値ラベルは30px角の段階操作ボタンへ置き換え、スライダーと同じ処理中無効化対象に含めた。全205テストと実画面確認を通過し、73,070,063 byteの単体EXEを再ビルドした。

## フェーズ30：単体EXEの配布最小化

### 目的

出力画素、処理速度、単体配布を維持したまま、GUIが使わない依存機能と重複ランタイムを配布EXEから除外する。第三者ライセンス原文も単体EXE内で完結させる。

### タスク

- [x] PyInstallerアーカイブの圧縮後内訳を計測する
- [x] GUI非対応のPillow AVIFデコーダを除外する
- [x] 未使用のSciPyサブパッケージを除外する
- [x] ndimageの未使用import連鎖とSciPy側OpenBLASを凍結用フックで除外する
- [x] 使用中のndimage APIを回帰テストで固定する
- [x] CustomTkinterのデータ収集をassetsだけに限定する
- [x] 凍結EXE自身で代表画像を処理する診断引数を追加する
- [x] 全第三者ライセンス原文をビルド時に収集・内包する
- [x] PNG完全一致、対応6拡張子、速度、空フォルダ単体起動を検証する

### 完了条件

- `dist/723UpScalerGUI.exe` 1ファイルだけで起動・設定読込・UI生成・画像処理が成功する。
- 代表画像の凍結EXE出力がソース版と画素完全一致する。
- ソース処理時間と単体EXE起動時間が従来値から悪化しない。
- 配布対象の第三者ライセンス原文がEXE内に揃う。

### 現状

未使用SciPy群、対応外AVIF、開発用依存、CustomTkinter重複データを除外し、ndimageが使用しないspecial連鎖を凍結版だけ最小stubへ置き換えた。NumPy側OpenBLAS、DIPlib、Python、Tcl/Tkは必要なため維持した。単体EXEは73,070,063 byteから33,977,278 byteへ53.5%縮小した。代表 `sample01` 4倍出力はソース版と全画素一致し、PNG SHA-256も一致した。対応6拡張子、単体起動、全208テスト、静的検査、依存検査を通過した。

## フェーズ31：無料範囲のWindowsコード署名導入

### 目的

秘密鍵をリポジトリへ置かず、単体EXE、画質、速度、最小サイズを維持したまま、信頼済みAuthenticode署名を安全に適用できる配布工程を用意する。無料の自己署名を信頼済み署名と誤認させない。

### タスク

- [x] 自己署名、SignPath Foundation、Sigstore、Microsoft Storeの信頼性と費用を比較する
- [x] EXEへWindows version resourceを追加する
- [x] thumbprint固定、SHA-256、RFC 3161 timestampの署名スクリプトを追加する
- [x] SignTool、timestamp、EKU、signer、改ざんを検査する検証スクリプトを追加する
- [x] 署名失敗時に既存配布物を置換しないstaging release buildを追加する
- [x] PFX、PEM、private keyをgitignoreへ追加する
- [x] SignPath Foundation申請用のコード署名・承認・privacy policyを文書化する
- [x] 一時自己署名証明書で署名工程を実証し、出力画素と単体起動が変わらないことを確認する
- [x] 公開対象を権利監査し、権利未確定の画像・派生画像・レビュー資料を除外する
- [x] 公開用合成素材、hash固定依存、GitHub CI、SignPath release workflow、公開policy文書を用意する
- [x] Microsoft runtimeの取得元を公式Visual Studio Redistへ固定し、不要なpywin32を配布物から除外する
- [x] ローカルGit repositoryを`main` branchで初期化し、公開候補のsecret scanを行う
- [x] GitHub owner、repository名、Authors、Reviewers、Approversを確定してpublic repositoryへ初回pushする
- [ ] GitHub-hosted buildから同じonefile形式のunsigned 1.00 pre-releaseを公開する
- [ ] SignPath Foundation審査、GitHub App、Project、Artifact Configuration、Signing Policy連携を完了する
- [ ] protected `main`のrelease workflowで最終EXEへ信頼済み署名を付け、検証済みSHA-256とともに公開する

### 完了条件

- クリーンな利用者PCでsigner chainがValidになり、RFC 3161 timestampを確認できる。
- 署名済みEXEの1 byte改変をWindowsとSignToolが拒否する。
- 署名前後の代表PNGが画素完全一致し、単体起動と処理速度が悪化しない。
- 署名済みEXEだけで配布でき、秘密鍵ファイルを同梱しない。

### 現状

ローカルの署名・検証・fail-closed release工程とWindows version resourceは実装済み。一時的なnon-exportable自己署名証明書で、SHA-256 Authenticode、DigiCert RFC 3161 timestamp、改ざん検知、代表画像の画素一致を確認し、証明書と一時成果物は削除した。公開準備では、権利未確定assetを公開対象から除外し、合成sample、hash固定wheel、SHA固定GitHub Actions、SignPath Artifact Configurationと手動承認workflowを追加した。MSVC/OpenMP runtimeは公式Visual Studio Redist由来を検証し、不要なpywin32は除外した。公開先は`nakashima723/723MangaUpscaler`、管理者は`nakashima723`として確定し、公開リポジトリ、protected `main`、CI、CodeQLを設定済みである。グレースケール・PSD対応後の依存関係と実EXEも再監査し、公式Apache-2.0全文へLICENSEを是正した。未署名pre-release専用workflowはSignPath提出と分離して用意したが、公開とFoundation申請は未実施である。自己署名は配布先で信頼されないため、本番 `dist/723MangaUpscaler.exe` は意図的に未署名のままである。

## フェーズ32：バージョン1.00・初期プレビュー文言更新

### 目的

GUI左上とWindows版情報のバージョンを1.00へ統一し、画像読込前のプレビュー説明を入力と出力の両方を示す文言へ修正する。

### タスク

- [x] GUIとCLIが参照するアプリバージョンを1.00へ変更する
- [x] Python package metadataを1.00へ同期する
- [x] Windows ProductVersionを1.00、FileVersionを1.00.0.0へ更新する
- [x] 初期プレビュー文言を「入力画像および出力結果」へ変更する
- [x] GUI Canvasの実表示文字列を回帰テストへ追加する
- [x] README、受け入れチェック、開発ログを更新する
- [x] 単体EXEを再ビルドし、診断3種と代表画像処理を確認する

### 完了条件

- GUIタイトルに「723モノクロ線画拡大ツール　1.00」と表示される。
- 画像読込前に「入力画像および出力結果のプレビューがここに表示されます。」と表示される。
- EXEのProductVersionが1.00、FileVersionが1.00.0.0になる。
- 全テスト、静的検査、単体EXE診断が成功する。

### 現状

ソース、package metadata、Windows version resource、README、受け入れチェックを1.00へ同期した。初期Canvas文言を「入力画像および出力結果」へ変更し、実際のCanvas item textを検査するテストを追加した。単体EXEは再ビルド済みで、診断3種と代表画像の出力hash一致を確認した。

## フェーズ33：相対線画・階調分離と3出力モード

### 目的

グレースケールまたは階調を含む画像で、広い階調面とその上の線を局所的な相対値から分離し、線画のみ・透明階調レイヤー分離・階調合成の3方式を選択可能にする。

### タスク

- [x] モルフォロジーclosingで局所階調を推定する
- [x] `I = tone * (1 - line_alpha)` に基づく相対線濃度を実装する
- [x] weak/strong相対差と絶対差を併用した線supportを実装する
- [x] `legacy / line_only / separate / composite` を設定とCLIへ追加する
- [x] GUIへグレー部分の扱いを選ぶメニューを追加し、プレビュー・単体・一括出力へ伝搬する
- [x] `separate` で黒RGB・`alpha = 1 - tone_luminance` のRGBA PNGを副出力する
- [x] `composite` で拡大階調と線画を合成する
- [x] カラー/RGBA入力が既存グレースケール化を経由することを維持する
- [x] 合成fixture、I/O、CLI、GUI、パイプライン、packaging回帰テストを追加する
- [x] `sample07.png` で3方式を出力し、暗い空ROIと線保持を確認する
- [x] README、CLI仕様、開発ログを更新する
- [x] 単体EXEを再ビルドし、設定・UI・代表画像診断を確認する

### 完了条件

- 同じ絶対グレー値でも、広い面は階調、細い局所暗化は線として分けられる。
- 明るい階調と暗い階調をまたぐ乗算的な薄線を連続して検出できる。
- `line_only` と `separate` の主線画PNGが一致する。
- `separate` の2レイヤーを白上で合成した結果と `composite` が量子化誤差内で一致する。
- `sample07` の暗い空ROIを全面線扱いせず、電線・電柱・建物線を保持する。
- 全テストと静的検査、単体EXE診断が成功する。

### 現状

局所背景に対する相対暗化率を使う実験分離を追加し、CLI・GUI・バッチで3方式を選択可能にした。`sample07` の暗い空ROIの線誤判定率は従来100%から約9.0%、全体線マスク率は35.4%から21.9%へ低下した。密集線や局所背景半径より太い構造が透明階調レイヤーへ薄く残る場合、完全同化線、画像端6pxは既知の実験上の限界として残る。

## フェーズ34：グレー部分メニュー文言と相対モード線幅調整

### 目的

GUIのグレー処理選択肢を利用者向けの明確な文言へ変更し、相対分離3モードで濃く太く見える線を同一明るさの約2/3幅へ調整する。

### タスク

- [x] 見出しを「グレー部分の扱い」へ変更する
- [x] 4つの選択肢を指定文言へ変更し、内部mode識別子は維持する
- [x] 長い日本語ラベルが欠けないよう見出しとプルダウン幅を拡張する
- [x] sample07でSDF線幅補正候補を比較する
- [x] 非legacyの3モードだけへ `-0.75` source pxの線幅biasを加算する
- [x] legacy出力へ補正を適用しない
- [x] run JSONへ補正値・適用有無・実効SDF biasを記録する
- [x] GUI文言、線幅2/3、3モード整合性の回帰テストを追加する
- [x] README、設定例、CLI仕様、アルゴリズム設計、開発ログを更新する
- [x] sample07の3出力を再生成し、単体EXEを再ビルド・診断する

### 完了条件

- GUIに指定された見出しと4つの選択肢が表示される。
- sample07の2倍・同一明るさで、相対モードの50%濃度代表線幅が6pxから4pxになる。
- `line_only` と `separate` の主線画が一致し、分離レイヤー再合成と `composite` の差が1LSB以内となる。
- legacyの実効SDF biasは従来値のままとなる。
- 全テスト、静的検査、単体EXE診断が成功する。

### 現状

指定文言への変更と相対3モード専用の `-0.75` source px補正を実装した。sample07では50%濃度の代表幅が6pxから4px、線占有面積が補正前の67.7%となり、同じ輪郭幅となる `-0.80` より残存線濃度を保った。legacyは補正対象外である。なお、この補正の既定値は細斜線の品質を優先したフェーズ35で `0.0` へ戻し、現在は任意設定として残している。

## フェーズ35：グレー分離時の線画品質回復

### 目的

グレー部分を分離・合成する3モードで、検出確信度と描画coverageを分離する。白地では従来処理の線形状を再現し、グレー地では局所階調に対する相対暗化を使うことで、線の接続、細線、斜線を保ったまま階調面を除去する。

### タスク

- [x] 旧相対モードの線膨張と固定負biasによる細線欠落を定量診断する
- [x] 検出用 `line_probability` と物理的な相対線alpha、描画用coverageを分離する
- [x] 白地の従来coverageとグレー地の相対coverageを連続的に切り替える `quality_hybrid` を実装する
- [x] 相対側の固定coverage gainと白地ルーティング範囲を設定・検証可能にする
- [x] hybridで拾った線をtone側から除去し、分離・合成時の二重線を防ぐ
- [x] 非legacyモードの既定線幅補正を `0.0` に戻し、`-0.75` は任意設定として残す
- [x] run JSONとデバッグ画像へcoverage方式、gain、ルーティング重み、描画coverageを記録する
- [x] 1px斜線、明るさ単調性、画像端線、3モード線alpha一致の回帰テストを追加する
- [x] sample07のGUI既定値とCLI既定値で白地線再現、平坦グレー偽線、再合成誤差を検証する
- [x] README、設定例、CLI仕様、アルゴリズム設計、開発ログを更新する
- [x] 単体EXEを再ビルドし、設定・UI・代表画像診断とソース版画素一致を確認する

### 完了条件

- sample07の白背景で、hybridとlegacyの線IoUが99%以上となる。
- 平坦なグレー面内部を線として出力しない。
- 1px斜線が既定設定で消えず、白地ではlegacyと同じHR線alphaとなる。
- `line_only / separate / composite` のHR線alphaが完全一致する。
- 分離したtoneと線PNGの再合成が `composite` と最大1LSB以内で一致する。
- 全テスト、静的検査、単体EXE診断が成功する。

### 現状

既定を `quality_hybrid` とし、局所背景0.90以下は相対coverage、0.98以上は従来coverage、その間はsmoothstepで連続補間する。相対側には固定gain 2.425を適用し、現在のSDF閾値からは逆算しない。sample07の白背景IoUはGUI既定0.291で99.9902%、CLI既定0.22で99.9831%となり、平坦グレー内部の偽線は0%だった。3モードのHR線alphaは完全一致し、分離レイヤー再合成とcompositeの差は最大1LSBである。硬い階調境界は線として解釈され得るため、実験機能の既知制約として残る。任意設定として残したグレー分離専用線幅biasは、GUIに接続されていなかったためフェーズ36で完全削除した。

## フェーズ36：未接続のグレー分離専用線幅補正削除

### 目的

GUIから操作できず、既定値0.0で通常は作用しないグレー分離専用の線幅biasを削除する。線幅設定を全モード共通の既存SDF設定へ一本化し、不要な内部分岐とメタデータを残さない。

### タスク

- [x] GUIと専用線幅補正の接続有無を確認する
- [x] `grayscale_processing` の専用設定と検証を削除する
- [x] 非legacy時だけSDF設定を複製・加算するpipeline helperを削除する
- [x] 専用補正値・適用有無・実効値のrun JSON項目を削除する
- [x] 専用補正の比較テストと不要な0.0指定を削除する
- [x] README、設定例、CLI仕様、アルゴリズム設計を現行仕様へ更新する
- [x] sample07の3モードを再生成し、run JSONから旧項目が消えたことを確認する
- [x] 全テストと単体EXE診断を完了する

### 完了条件

- ソース、テスト、現行設定例、現行仕様にグレー分離専用線幅設定が残らない。
- `legacy / line_only / separate / composite` が同じ `sdf.width_bias_source_px` を参照する。
- sample07の出力品質と3モード整合性を維持する。
- 全テスト、静的検査、単体EXE診断が成功する。

### 現状

グレー分離専用の設定、加算処理、メタデータ、テスト、現行文書説明を削除した。全モードは共通の `sdf.width_bias_source_px` を直接参照し、GUI既定では0.0のまま動作する。sample07の再生成後run JSONには旧専用項目が存在せず、単体EXEとソース版の代表出力も画素完全一致した。

## フェーズ37：グレー分離レイヤーのPSD出力

### 目的

GUIで「線画とグレー部分を分けて出力」を選んだ場合に、既定ONのPSD出力を選べるようにする。PSDはGrayscaleカラーモードとし、線画・グレー・白背景を独立レイヤーとして保存する。PSDをOFFにした場合は従来の2枚のPNG出力を維持する。

### タスク

- [x] GUIへseparate時だけ表示される「PSDで出力する」を既定ONで追加する
- [x] 単体・一括出力開始時にPSD選択値を凍結し、workerへ渡す
- [x] 8/16-bit Grayscale PSD v1 writerを外部依存なしで実装する
- [x] `Line Art / Grayscale Tone / Background` の3レイヤーと統合画像を保存する
- [x] PSD ONでは単一PSD、OFFでは主線PNGと透明グレーPNGを出力する
- [x] GUI出力名予約、CLI、batch、run JSON、batch summaryへ形式を伝搬する
- [x] inspect・compare・ライブプレビューでは従来どおり一時PNGを使用する
- [x] sample07をPSD化し、独立readerでモード・深度・レイヤー・統合画像を確認する
- [x] README、設定例、CLI仕様、アルゴリズム設計、受け入れチェックを更新する
- [x] 全テストと単体EXEのPSD診断を完了する

### 完了条件

- GUI初期状態ではPSDチェックがONで、separate以外では非表示となる。
- PSDはGrayscale、8または16 bits/channel、3レイヤーで再読込できる。
- PSD統合画像が同設定のcomposite出力と最大1LSB以内で一致する。
- PSD OFFのPNG命名・透明度・再合成を維持する。
- 単体・一括・EXEからPSDを書き出せる。
- 全テスト、静的検査、単体EXE診断が成功する。

### 現状

GUIのseparate選択時だけ「PSDで出力する」を表示し、既定ONとした。PSD v1のGrayscale header、レイヤーrecord、透明度channel、PackBits RLE、merged imageを専用writerで実装した。sample07の2倍PSDは8-bit Grayscale、2896x2172、3レイヤーとしてPillow、psd-tools、ImageMagickで再読込でき、merged imageは既存composite PNGと全画素一致した。CLI・YAMLは後方互換のPNG既定を維持する。

## Codex向け実装単位

Codexには一度に巨大実装を依頼しない。以下の粒度で依頼する。

1. `config.py` と設定マージだけ
2. `io.py` と保存テストだけ
3. `mask_extract.py` の固定閾値だけ
4. `mask_extract.py` にSauvolaとヒステリシス追加
5. `sdf_render.py` のSDF生成だけ
6. `composite.py` だけ
7. `pipeline.py` で白キャンバス合成まで統合
8. CLI接続
9. 2x/3x/4x/6x/8xのテスト拡充
10. MVP後に `tone_source.py` と外部アップスケーラーadapter

各依頼では「既存テストを通し、新規テストを追加し、変更ファイル全体を提示」と指定する。
