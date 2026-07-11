# 受け入れチェックリスト

## MVP機能

- [x] `mlu --help` が表示される
- [x] `mlu doctor` がPython依存関係を確認できる
- [x] `mlu inspect input.png --preset line_only --debug-dir debug` がマスク系debugを出す
- [x] `mlu upscale input.png -o output.png --scale 2 --preset line_only` が外部バイナリなしで動く
- [x] `mlu upscale input.png -o output.png --scale 3 --preset line_only` が外部バイナリなしで動く
- [x] `mlu upscale input.png -o output.png --scale 4 --preset line_only` が外部バイナリなしで動く
- [x] `--invert` が動く
- [x] GUIでフォルダ直下の対応画像を一括変換できる
- [x] GUI一括変換でファイル名と拡張子のAND絞り込みができる
- [x] GUI一括変換は対象枚数の確認後、OKの場合だけ実行される
- [x] GUI一括変換のプレビューは対象の先頭1枚だけを表示する
- [x] GUIの「プレビューを表示する」が既定ONで、入力選択直後に実出力と同じ画像を表示する
- [x] GUIで倍率・明るさを変更すると、出力プレビューが最新設定へリアルタイム更新される
- [x] GUIの倍率・明るさ変更後も、入力画像上のプレビュー中心位置と表示倍率が維持される
- [x] GUIの明るさは-10から+10で、最低値でも合成線画のプレビューが全面黒にならない
- [x] GUIの明るさ0が旧-3相当、+10が旧+7相当になる
- [x] 明るさスライダー左右の「-」「+」ボタンで値を1ずつ変更できる
- [x] GUIタイトルが「723モノクロ線画拡大ツール　1.00」になる
- [x] 「線画とグレー部分を分けて出力」のときだけ「PSDで出力する」が表示され、既定ONになる
- [x] PSD ONでは8/16-bit Grayscale PSDへ線画・グレー・白背景の3レイヤーを保存する
- [x] PSD OFFでは従来どおり主線PNGと透明グレーPNGを保存する
- [x] 出力サイズが36,000,000画素以上の初回プレビュー前に確認し、「いいえ」で再チェックまで処理を停止する
- [x] 出力プレビュー用の一時出力は実出力先へ残らず、成功時・失敗時とも一時フォルダが削除される
- [x] 純線画プリセットで白キャンバス＋SDF線出力ができる
- [x] 既定出力として最終8bit PNGが出る
- [x] debug指定時に `02_line_prob.png`, `03_line_mask.png`, `05_line_alpha_hr.png`, `06_final.png` が出る
- [x] debug指定時に `line_soft_hr`, `soft_mask_hr`, `sdf_alpha_before_soft_mode_hr` を確認できる
- [x] directional_smoothingの補正前alpha、適用重み、差分がdebug保存される

## 画質

- [ ] 斜め線がニアレスト拡大より滑らか
- [ ] 円弧に階段状ジャギが目立たない
- [ ] 建築線が大きく波打たない
- [ ] 線幅が元画像から大きく変わらない
- [ ] 細い電線、柵、窓枠が欠けすぎない
- [ ] 薄いグレー汚れが白へ飛ぶ
- [ ] 2x/3x/4xで同じ品質方針を満たす
- [ ] 二値化後に線が破綻しにくい
- [ ] directional_smoothing有効時、斜め線のガタつきが無効時より目立たない
- [ ] directional_smoothing有効時、水平・垂直線の端や交差部が不自然に崩れない
- [ ] directional_smoothing有効時、水平に近い屋根線や電線に元画像にない大きな波打ちが出ない
- [x] `line_only` 既定でdirectional_smoothingとsoft alpha重ねが不要に有効化されない

## 堅牢性

- [x] ほぼ白紙画像で落ちない
- [x] ほぼ黒画像で警告が出る
- [x] 透明PNGは白背景に合成して処理できる
- [x] JPEG入力で動く
- [x] 16bit PNG入力は後続対応として扱い、MVPでは必須にしない
- [x] 外部バイナリ未設定でもMVP処理が動く

## 再現性

- [x] 同一入力・同一設定で同一出力になる
- [x] 実効設定がrun JSONに保存される
- [x] プリセット名とバージョンが保存される

## ドキュメント

- [x] Windows導入手順がある
- [x] プリセットの使い分けが書かれている
- [x] デバッグレイヤーの見方が書かれている
- [x] 16bit、外部アップスケーラー、バッチ、Potraceの現状が書かれている
- [x] PotraceなどGPL系外部ツールを同梱しない方針が書かれている
- [x] よくある失敗例が書かれている
- [x] READMEだけでMVPを試せる

## MVP後

- [x] グレー階調プリセットでtone_source＋SDF合成ができる
- [ ] Real-CUGAN実バイナリ環境で `--upscaler realcugan` の品質確認が済んでいる
- [x] 外部コマンドがrun JSONに保存される
- [x] 外部アップスケーラー失敗時にstderrがログへ残る
- [x] バッチ処理が最低限動く
- [x] パラメータ比較出力が最低限動く
- [x] Potraceレンダラーが任意機能として動く
- [ ] 16bit PNG出力が動く
