# 03. アルゴリズム設計

## 1. 基本思想

漫画背景のアップスケールでは、画像全体をニューラル超解像に丸投げしない。線画を「黒い画素群」としてそのまま拡大すると、斜め線や曲線の階段状ジャギが出やすい。ニューラル超解像では線が滑らかになる一方で、線が太る、細線が消える、直線が波打つことがある。

そのため、MVPでは線画を「マスクから再レンダリング」することに集中する。グレー階調やトーンは後続フェーズで既存アップスケーラーに任せる。

## 2. 入力の正規化

### 2.1 グレースケール化

RGB入力はsRGB係数でグレースケール化する。

```text
gray = 0.2126 R + 0.7152 G + 0.0722 B
```

MVPではガンマ線形化を行わず、見た目に近いsRGBコード値で処理する。漫画線画では物理的な線形ブレンドより、見た目の濃度維持が重要なためだ。将来拡張として線形ブレンドを選べるようにする。

### 2.2 濃度方向

内部は `0.0=黒, 1.0=白` とする。

線画らしさは以下で扱う。

```text
darkness = 1.0 - gray
```

背景が黒、線が白の反転素材は `--invert` で明示指定する。自動反転は危険なためMVPでは警告つきの補助機能に留める。

黒ベタ背景に白線が乗る複雑な素材はMVPの正式対応外とする。`--invert` は、反転すれば白地黒線相当として扱える素材のための明示オプションだ。

## 3. 線画マスク抽出

### 3.1 目標

`line_prob`, `line_mask`, `line_soft` を生成する。

- `line_prob`: 0.0〜1.0の線らしさ
- `line_mask`: SDF用の二値マスク
- `line_soft`: アンチエイリアスや薄線の情報を残した補助マップ

### 3.2 推奨手順

MVPでは以下の順に実装する。

```text
1. grayをfloat32化
2. darkness = 1 - gray
3. global thresholdでline_mask候補を作る
4. darknessからline_probを作る
5. hysteresisで強線・弱線を接続する
6. 小ノイズ除去
7. 穴埋め
8. line_softを作る
```

Sauvolaなどの局所閾値は後続のロバスト化として実装する。MVPの品質基準は、前処理済みの白地黒線画像に対する固定閾値とヒステリシスを中心に置く。

### 3.3 グローバル閾値

白地に黒線が明確な画像では、固定閾値が最も安定する。

```text
line_mask = gray < black_threshold
```

初期値は以下を試す。

```yaml
black_threshold: 0.72
```

`gray < 0.72` はやや広めに拾う設定だ。MVPでは細線欠けを避けるため、疑わしい薄線は残す方向を優先する。ただし薄いグレー汚れは入力前処理で除去されている前提にする。

### 3.4 局所閾値

背景に薄いグレーや影がある場合、固定閾値だけでは影を線として拾う。MVPではこのような素材は入力前処理済みとみなし、局所閾値は後続対応とする。

初期値案：

```yaml
adaptive:
  method: sauvola
  window_size: 31
  k: 0.18
```

大きい建物背景では `window_size` を63〜127に上げるプリセットも用意する。

### 3.5 ヒステリシス

細線を切らさないため、強線と弱線を分ける。

```text
strong = darkness >= strong_threshold
weak = darkness >= weak_threshold
line_mask = weakのうちstrongに連結している部分
```

初期値：

```yaml
hysteresis:
  strong: 0.50
  weak: 0.25
```

これにより、薄いアンチエイリアスだけのゴミは拾いにくく、強線につながる薄い線は残せる。

### 3.6 ノイズ除去

- 小連結成分除去
- 小穴埋め
- 細い破線をつなぐ軽いclosing
- 過剰なopeningは細線を消すため避ける

初期値：

```yaml
cleanup:
  min_component_area: 6
  close_radius: 0
  fill_holes_area: 12
```

## 4. tone_source生成

### 4.1 なぜ必要か

Real-CUGANに線を含む画像を渡すと、出力にも線が残る。その上にSDF線を重ねると、線が太る、濃くなりすぎる、二重線になることがある。

そこで階調ブランチには、入力から線を白方向に持ち上げた `tone_source` を渡す。この処理はグレー階調やトーンを扱う拡張ブランチであり、純線画MVPの既定では使わない。

### 4.2 最小方式

後続フェーズでは複雑なインペイントではなく、線領域を局所背景に近づける簡易方式から始める。

```text
1. line_maskを少し膨張させる
2. 膨張領域の周囲から局所背景を推定する
3. 線領域を background_lift_strength に応じて白側へ寄せる
4. グレー階調領域は保護する
```

初期値：

```yaml
tone_source:
  mode: lift_lines
  dilate_radius: 1.2
  lift_strength: 0.85
  background_blur_radius: 9
  protect_midtones: true
```

実装モードは以下。

- `white_canvas`: 純線画MVP用。白一色を返す。
- `passthrough`: 入力グレーをそのまま返す。比較・切り分け用。
- `lift_lines`: 線領域を膨張し、線周辺を白側へ持ち上げる。`protect_midtones` が有効な場合、線らしさが低い中間階調は強く白飛びさせない。

### 4.3 純線画の場合

MVPの対象である純線画では、tone_sourceは白一色でよい。

```yaml
tone_source:
  mode: white_canvas
```

この場合、Real-CUGANを呼ぶ必要はない。SDF線アルファだけで最終画像を作る。これをMVPの既定動作とする。

### 4.4 グレー階調が重要な場合

影、ハッチング、軽いトーン、空気感がある背景では、後続フェーズでtone_sourceをReal-CUGANなどで拡大する。

ただしMVPでは、ハッチングやカケアミは品質保証対象外とする。入力に含まれる場合、ハッチングやカケアミは線の集合として拾われる可能性があり、点描や網点トーンはノイズ寄りに扱う。

### 4.5 tone_hrの合成条件

`tone_hr` は線のジャギー改善用ではなく、グレー階調やトーンを保持するための下地である。純線画に薄い `tone_hr` を重ねると、SDF線の下にグレー残渣が出て品質を下げるため、既定では自動判定で使用可否を切り替える。

```yaml
composite:
  tone_usage: auto  # auto / always / never
```

- `auto`: 背景midtone比率から純線画に見える場合は白キャンバスへ戻す。
- `always`: 比較やグレー階調素材の検証用に、常に `tone_hr` を下地に使う。
- `never`: upscaler設定に関係なく白キャンバスへ戻す。

## 5. SDF/距離場による線再レンダリング

### 5.1 目的

二値のline_maskを直接リサイズするのではなく、線領域の境界から距離場を作り、高解像度でアンチエイリアス付きの線アルファを生成する。

### 5.2 距離場の作り方

符号規約：

- 線の内側を正
- 線の外側を負

```text
inside_dist  = distanceTransform(line_mask)
outside_dist = distanceTransform(not line_mask)
sdf = inside_dist - outside_dist
```

この `sdf` は元解像度ピクセル単位の距離を持つ。

### 5.3 高解像度soft SDF

source解像度の二値 `line_mask` からSDFを作ってから拡大すると、二値化時点の階段形状も拡大される。MVPの既定では、元画像のアンチエイリアス濃度を含む `line_soft` を先に高解像度化し、高解像度側でsoft supportを二値化してSDFを作る。

`line_soft` の既定coverageは `darkness` とし、元画像の黒さをそのまま使う。線検出用の `line_prob` は `line_mask` 作成には使うが、既定ではsoft SDFの濃度を持ち上げない。旧方式の `max(darkness, line_prob)` は浅角度の建築線に大きな周期の波打ちを出すことがあるため、`max_probability` として比較・診断用に残す。

```text
line_soft_hr = resize(line_soft, target_size, interpolation=lanczos_or_cubic)
soft_mask_hr = line_soft_hr >= soft_sdf_threshold
sdf_hr = distanceTransform(soft_mask_hr) - distanceTransform(not soft_mask_hr)
```

この方式では直線を推定して描き足さないため、Hough/PCA式の補正よりも、元画像に存在しない長い極細線を生成しにくい。既定値は以下。

```yaml
sdf:
  distance_source: soft_mask_hr
  soft_sdf_threshold: 0.22

mask:
  soft_coverage:
    mode: darkness
    gamma: 1.0
```

比較や切り分けでは従来方式に戻せる。

```text
sdf_hr = resize(sdf, target_size, interpolation=lanczos_or_cubic) * scale
```

```yaml
sdf:
  distance_source: binary_mask
```

`binary_mask` では `* scale` が重要だ。元解像度で1pxの距離は、4倍出力では4pxの距離に相当する。`soft_mask_hr` では最初から高解像度ピクセル単位の距離場なので、scale倍補正はしない。

### 5.4 線幅補正

`width_bias` で線の太さを調整する。

```text
sdf_adjusted = sdf_hr + width_bias_px
```

- `width_bias_px > 0`: 線を太くする
- `width_bias_px < 0`: 線を細くする

単位は高解像度ピクセルにする。設定では元解像度基準も指定できるようにする。

```yaml
sdf:
  width_bias_source_px: -0.05
```

内部で `width_bias_hr_px = width_bias_source_px * scale` に変換する。

### 5.5 アンチエイリアス

SDFから線アルファを作る。

```text
alpha = smoothstep(-aa_radius, aa_radius, sdf_adjusted)
```

`aa_radius` は高解像度ピクセル単位で0.75〜1.0程度を初期値にする。MVPでは漫画原稿でのシャープさと二値化耐性を優先するため、過度に柔らかいアンチエイリアスは避ける。

```yaml
sdf:
  aa_radius_hr_px: 1.0
```

### 5.6 line_softの反映

二値マスクだけだと薄いアンチエイリアス線が消えることがある。そのため、元画像の `line_soft` を高解像度化して、SDFアルファと合成できるようにする。

```text
line_soft_hr = resize(line_soft, target_size)
alpha = max(alpha_from_sdf, line_soft_hr * soft_gain)
```

ただし `line_soft` を強く重ねると、薄いグレー層が線を補助するほど濃くならず、最終画像に不要な薄い汚れだけを足すことがある。また `max_probability` で持ち上げた `line_soft` を `soft_mask_hr` と `blend` の両方で使うと、浅角度線の濃度揺れが大きな周期の波打ちとして固定されやすい。したがって `line_only` の既定では、SDF形状を作るために `line_soft` を使い、最終alphaへの追加合成は行わない。

```yaml
sdf:
  soft_alpha_mode: none
  soft_gain: 0.0
```

`blend` は以下の式で、SDFの線幅情報を残しつつ、二値マスク化で失われたアンチエイリアス濃度を戻す実験設定として残す。

```text
alpha = alpha_from_sdf * (1 - soft_gain) + line_soft_hr * soft_gain
```

薄い汚れを拾う素材では `blend` が汚れも復活させる可能性があるため、使う場合は入力前処理、`mask.soft_coverage.mode`、`soft_sdf_threshold` と合わせて比較する。

### 5.7 建築線スタビライザー

soft coverageでも、建築背景に多い長い直線の微細な波打ちは残る。実験実装として、長い直線候補だけを高解像度alpha上で補強する `line_stabilizer` を用意した。

```text
1. line_mask / line_soft のsupport点を集める
2. Hough風に角度/rhoへ投票する
3. 密度、長さ、RMS誤差で直線候補を絞る
4. PCAで線分端点と幅を推定する
5. 高解像度alphaへ直線coverageを生成し、既存alphaへstrength分だけblendする
```

ユーザー目視では、ジャギー抑制だけを見ると強めのline stabilizerが有効だった。一方で、局所support制限後も、元画像に存在しない極細線が出る現象を実用上許容できない品質と判断した。したがってMVP既定では採用せず、明示opt-inの実験機能に留める。

```yaml
line_stabilizer:
  enabled: false
  strength: 0.55
```

これは全面的なベクター化ではない。交差部、葉、カケアミ、曲線、手描きの揺れを壊しすぎないため、再検討する場合も、幾何coverageを直接足す前にsupport clamp、差分debug、交差点保護を入れて評価する。幾何補正候補はdebugの `*_line_geometry_hr.png` で確認する。

### 5.8 方向性スムージング

soft SDFでも、元画像が浅い斜線をピクセル階段として持っている場合、その階段が高解像度alphaへ残ることがある。`directional_smoothing` は、このガタつきを減らすため、SDF後の `line_alpha_hr` に対して局所的な方向性平滑化を行う実験機能である。

旧 `line_stabilizer` との違いは、直線を検出して新しいcoverageを描き足さない点だ。構造テンソルで局所的な線の接線方向を推定し、候補角へ量子化せず、その局所推定角に沿って既存alphaを平均する。水平・垂直に近い線は `min_angle_from_axis_degrees` から `full_strength_angle_from_axis_degrees` まで連続的に強度を上げる。適用範囲は既存alpha近傍に制限し、1回の変更量も `max_delta` で制限する。

```yaml
directional_smoothing:
  enabled: false
  strength: 0.55
  radius_hr_px: 2
  min_angle_from_axis_degrees: 20.0
  full_strength_angle_from_axis_degrees: 34.0
  max_delta: 0.35
```

この処理はSDFレンダラー用であり、Potraceレンダラーでは適用しない。debugでは補正前alpha、適用重み、差分を `*_directional_smoothing_*.png` として確認できる。強くしすぎると短い斜線の端や細かい装飾が眠くなり、浅角度線では元画像にない波打ちを増やすことがある。MVP既定では無効化し、`compare` で `strength`、`radius_hr_px`、角度gateを見比べる実験機能に留める。

### 5.9 長いストロークを単純化

`centerline_simplification` は、SDF後のalphaをsource解像度へ集約してZhang-Suen thinningで中心線化し、8近傍グラフから厳格に選んだ長い枝の短周期ノイズだけを減衰させる実験機能である。ユーザー向け名称は「長いストロークを単純化」とする。内部キーは設定互換性のため維持する。

対象枝は64 source px以上、最大半径2.25 source px以下とし、明確な角を含まず、弦長/弧長比0.985以上、直線近似RMS 0.35 source px以下、最大偏差1.0 source px以下、線幅変動係数0.20以下、線幅P90/P10比1.50以下をすべて満たす必要がある。条件外の枝は全体を保護し、単純化しない。複雑なsupport成分全体を除外するgateも検討したが、建築線は細部と同じ連結成分になりやすく、有用候補がほぼ消えるため採用していない。

対象中心線を0.5 source px間隔へ等弧長化し、正係数・ゼロ位相の1次元Gaussian低域通過をY/Xへ適用する。低域通過後の接線を求め、変位の接線成分を除いて法線成分だけを採用する。端点と角近傍は変位0とし、3 sigmaの範囲でsmoothstepにより復帰する。最終変位は設定上限でベクトル長clampする。

元の高解像度alphaを中心線の法線方向にサンプリングして局所線幅を再推定し、線幅系列にも同じGaussian低域通過を適用する。各ストロークの局所bboxを原則4倍supersamplingで再描画し、丸キャップは両端だけに置く。新しい独立線を作らないよう、置換範囲は元supportの対象枝とその局所近傍だけに制限し、元alphaの局所最大値を濃度上限にする。

```yaml
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
```

`enabled: false` または `filter_sigma_source_px: 0` では処理を完全に迂回し、従来alphaと画素一致する。フィルタ有効時は、supersamplingとLanczosで得たcoverageを内部の形状判定に使った後、`binary_threshold` で最終alphaを0または1へ戻す。これにより出力PNGにはアンチエイリアス由来のグレーを残さない。

二値alphaを小数 `strength` で混ぜると、二値化閾値との組み合わせで旧輪郭と新輪郭が非対称に残る。このため、二値出力時のalpha置換率は常に1.0とし、強度は元中心線からGaussian低域通過中心線への法線変位率 `geometry_strength` で表す。

実験比較はlow=`sigma 0.75 / geometry_strength 0.50 / max displacement 0.50`、medium=`1.00 / 0.75 / 0.75`、high=`1.25 / 1.00 / 1.00`とする。Gaussianはsigma増加に対して短周期成分を単調に減衰させ、RDPの制御点削減や多角形化を行わない。

再ラスタライズ後は、小さな新規孤立成分を除去してから、元画像と候補画像を出力解像度の8近傍でラベル付けする。変更領域を最寄りのsource成分へ帰属させ、元成分と候補成分の重なり対応を比較する。元成分の消失・分割、候補成分の誤接続、元と重ならない新規成分を1件でも検出した場合、そのsource成分に属する変更画素を元へ戻す。トポロジーを保っていても、帰属する置換領域内の黒画素比が0.80未満または1.20超なら同様に戻す。

二値出力の復元値は元alphaではなく元の二値判定値とし、ロールバックによってグレーを再混入させない。run JSONには平均、P95、最大変位、高周波energy減衰率、clamp率、候補前後とロールバック後の成分数を記録する。debugには `filtered_centerline_source`、`centerline_filter_displacement_source`、`component_rollback_source` を保存する。

## 6. Potraceオプション

### 6.1 位置づけ

Potraceは、ビットマップを滑らかなベクター画像に変換し、任意解像度でレンダリングできるため、白地に黒線が明確な素材では有効だ。一方で、細かいカケアミ、薄いグレー線、ノイズ、複雑な葉、砂利、木肌では形状を整理しすぎる可能性がある。

したがって既定にはしない。SDFを既定のまま維持し、明示的に `--line-renderer potrace` を指定した場合だけ使う。

### 6.2 Potrace処理案

```text
1. line_maskをPBM/BMPに保存
2. potraceでSVG化
3. CairoSVGまたはInkscape CLIで目標サイズへPNGレンダリング
4. PNGをline_alpha_hrとして読み込む
5. debug用にSDF版line_alpha_hrも出して比較する
```

### 6.3 注意点

- PotraceはGPLライセンスのため、同梱・改変・再配布の扱いに注意する。
- 外部CLIとしてユーザーが別途導入する形にするのが安全だ。
- 色や階調は基本的に扱わず、線形状のベクター化に使う。
- 設定が悪いと建築線が丸まりすぎる。
- `line_stabilizer` はSDF向けのため、Potrace時は同時利用しない。

## 7. 階調ブランチ

### 7.1 Real-CUGAN

後続フェーズの候補。アニメ・イラスト系超解像向けで、2x/3x/4xに対応する。ncnn Vulkan版はCUDAやPyTorch環境なしで動かせる。

推奨初期値：

```yaml
upscaler:
  engine: realcugan
  scale: 4
  noise: -1
  tile_size: 256
```

線を含まないtone_sourceを渡すため、ノイズ除去は弱め、またはなしから始める。

### 7.2 waifu2x

保守的なフォールバック。線やアニメ画像向けに安定しやすいが、やや眠くなることがある。

### 7.3 Real-ESRGAN

写真由来のグレー階調や圧縮劣化が強い場合の候補。線画主体ではディテールを作りすぎることがあるため、既定にはしない。

### 7.4 Lanczos

後続フェーズの開発・テスト用フォールバック。品質本命ではないが、外部バイナリなしでも階調ブランチのパイプラインテストを可能にする。

## 8. 合成

### 8.1 基本式

内部表現を `0.0=黒, 1.0=白` とする。MVPでは `tone_hr` の代わりに白キャンバスを使う。黒線の合成は以下を基本にする。

```text
final = canvas_or_tone_hr * (1 - line_alpha_hr * line_darkness)
```

`line_darkness=1.0` なら完全な黒インクになる。少し柔らかい線にしたい場合は0.85〜0.95にする。

```yaml
composite:
  line_darkness: 1.0
```

### 8.2 階調保護

線の下に影やグレーがある場合、黒線合成で自然に暗くなる。背景を消しすぎる場合は、line_alphaのエッジだけ弱める。

```yaml
composite:
  edge_alpha_gamma: 1.1
```

`edge_alpha_gamma > 1` で半透明エッジが薄くなる。

### 8.3 二重線防止

tone_sourceで線を十分に持ち上げていない場合、tone_hr側に既存線が残る。デバッグレイヤーで `tone_source` と `tone_hr` を確認し、以下で調整する。

- `tone_source.lift_strength` を上げる
- `tone_source.dilate_radius` を上げる
- `line_mask.black_threshold` を上げて線を広く拾う
- `sdf.width_bias_source_px` を少し下げる

## 9. プリセット方針

### `line_only`

- 純線画用
- tone_sourceは白キャンバス
- Real-CUGANを使わない
- SDF重視

### `gray_tone`

- 線とグレー階調が混在するAI漫画背景用
- tone_source生成あり
- Real-CUGAN使用
- line_soft反映あり
- ユーザー目視確認に基づき、既定の線幅補正は `width_bias_source_px: -0.25`

### `conservative`

- 破綻を避ける設定
- 閾値は狭め
- SDF線幅補正は控えめ
- waifu2xまたはLanczosフォールバック可

## 10. パラメータ探索

品質確認用に、1枚の入力から複数パラメータを一括生成する `mlu compare` を使う。

```text
black_threshold: 0.55, 0.65, 0.75
width_bias_source_px: -0.25, -0.10, 0.00, 0.10
soft_gain: 0.0, 0.25, 0.5
```

出力はコンタクトシートにして比較する。
