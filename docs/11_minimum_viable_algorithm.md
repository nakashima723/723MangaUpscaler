# 11. 最小実用アルゴリズム仕様

このファイルは、Codexが迷ったときにMVP実装の最小挙動を確認するための仕様だ。

MVPでは白地黒線の純線画を対象にし、外部アップスケーラーやtone_sourceは使わない。

## 1. 入力

`gray` はfloat32、形状 `(H, W)`、値域 `[0, 1]`、`0=黒, 1=白`。

## 2. 線画マスク

```text
darkness = 1 - gray
line_prob = clamp((darkness - weak) / (strong - weak), 0, 1)
line_mask = gray < black_threshold
line_soft = where(line_mask support, darkness, 0)
```

Sauvolaが未実装でも、この固定閾値版でパイプラインを通す。ヒステリシスは細線保持のためMVP内で追加する。`line_soft` は既定では元画像の黒さ `darkness` を使い、`line_prob` で濃度を持ち上げない。

## 3. 白キャンバス

MVPでは階調を保持しない。最小版は白キャンバスを使う。

```text
canvas = ones((H * scale, W * scale), float32)
```

## 4. SDF

```text
line_soft_hr = resize(line_soft, (H*scale, W*scale))
soft_mask_hr = line_soft_hr >= 0.22
inside = distance_transform(soft_mask_hr)
outside = distance_transform(not soft_mask_hr)
sdf_hr = inside - outside
sdf_hr = sdf_hr + width_bias_source_px * scale
alpha = smoothstep(-aa_radius_hr_px, aa_radius_hr_px, sdf_hr)
```

比較用に `distance_source: binary_mask` を指定した場合は、source解像度で以下を行う。

```text
inside = distance_transform(line_mask)
outside = distance_transform(not line_mask)
sdf = inside - outside
sdf_hr = resize(sdf, (H*scale, W*scale)) * scale
```

`smoothstep(edge0, edge1, x)` は以下。

```text
t = clamp((x - edge0) / (edge1 - edge0), 0, 1)
return t * t * (3 - 2 * t)
```

## 5. tone_hr

MVPでは使わない。グレー階調対応フェーズで、外部アップスケーラーが使える場合はtone_sourceを渡し、使えない場合は内部リサイズで拡大する。

## 6. 合成

```text
final = canvas * (1 - alpha * line_darkness)
final = clamp(final, 0, 1)
```

## 7. 重要な失敗条件

- `line_mask.mean() < 0.001` なら線がほぼ抽出できていない警告を出す。
- `line_mask.mean() > 0.60` なら線として拾いすぎている警告を出す。
- 出力配列にNaN/Infがあればエラーにする。
- 出力サイズが0または上限超過ならエラーにする。
- `scale` は2, 3, 4, 6, 8に対応する。
