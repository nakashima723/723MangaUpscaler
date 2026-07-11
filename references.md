# 参照元メモ

このロードマップで前提にした外部ツール・ライブラリの参照先だ。開発時は各ツールの最新README、ライセンス、CLI引数を再確認する。

## Real-CUGAN

- 公式README: https://github.com/bilibili/ailab/blob/main/Real-CUGAN/README_EN.md
- ncnn Vulkan実装: https://github.com/nihui/realcugan-ncnn-vulkan

メモ：Real-CUGANはアニメ画像向け超解像モデルで、公式READMEでは2x/3x/4x対応が説明されている。ncnn Vulkan実装はVulkan GPU上で動き、CUDAやPyTorchランタイムなしで使える旨が説明されている。

## Real-ESRGAN ncnn Vulkan

- https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan

メモ：Real-ESRGANのncnn実装。一般画像復元とアニメ画像向け最適化に言及がある。写真寄り・劣化補正用の代替候補。

## waifu2x ncnn Vulkan

- https://github.com/nihui/waifu2x-ncnn-vulkan

メモ：Vulkan APIでIntel/AMD/NVIDIA/Apple Silicon上で高速に動くncnn版waifu2x。保守的フォールバック候補。

## Potrace

- 公式サイト: https://potrace.sourceforge.net/
- README: https://potrace.sourceforge.net/README
- man page: https://potrace.sourceforge.net/potrace.1.html

メモ：ビットマップを滑らかなスケーラブル画像へ変換するツール。公式サイトでは任意解像度でレンダリングでき、ジャギらない結果を得られる旨が説明されている。ソースコードはGNU GPLであるため、同梱や改変には注意する。

## scikit-image

- threshold_sauvola API: https://scikit-image.org/docs/stable/api/skimage.filters.html#skimage.filters.threshold_sauvola
- Niblack/Sauvola example: https://scikit-image.org/docs/0.25.x/auto_examples/segmentation/plot_niblack_sauvola.html

メモ：Sauvolaは背景が一様でない画像向けの局所閾値候補。

## CairoSVG

- https://cairosvg.org/documentation/

メモ：SVGをPNG/PDF/PSなどへ変換できるCLIおよびPythonライブラリ。Potraceで作ったSVGのラスタライズ候補。

## OpenCV Python

- https://pypi.org/project/opencv-python/
- https://github.com/opencv/opencv

メモ：画像処理の基盤候補。MVPでは距離変換、形態処理、画像保存などに使う想定。
