import os
from PIL import Image
import numpy as np
import cv2


def analyze_image(img_path):
    """
    分析单张图片：
    - 黑白比例
    - RGB直方图
    - 边缘密度
    - 亮度均值/方差
    - 连通域数量
    - Sobel梯度强度
    - HSV饱和度/明度均值
    """
    try:
        im = Image.open(img_path).convert("RGB")
        arr = np.array(im)

        # 灰度
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        total = gray.size
        near_white_ratio = np.count_nonzero(gray >= 245) / total
        near_black_ratio = np.count_nonzero(gray <= 10) / total
        gray_mean = gray.mean()
        gray_std = gray.std()

        # RGB直方图
        hist_r = np.histogram(arr[:, :, 0], bins=16, range=(0, 255))[0] / total
        hist_g = np.histogram(arr[:, :, 1], bins=16, range=(0, 255))[0] / total
        hist_b = np.histogram(arr[:, :, 2], bins=16, range=(0, 255))[0] / total

        # 边缘密度
        edges = cv2.Canny(gray, 100, 200)
        edge_density = np.count_nonzero(edges) / total

        # Sobel梯度
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        sobel_mean = (np.mean(np.abs(sobelx)) + np.mean(np.abs(sobely))) / 2

        # 连通域数量
        _, labels = cv2.connectedComponents((gray < 245).astype(np.uint8))
        connected_components = labels.max()

        # HSV 饱和度/明度均值
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        sat_mean = hsv[:, :, 1].mean()
        val_mean = hsv[:, :, 2].mean()

        return {
            "file": os.path.basename(img_path),
            "white_ratio": near_white_ratio,
            "black_ratio": near_black_ratio,
            "edge_density": edge_density,
            "gray_mean": gray_mean,
            "gray_std": gray_std,
            "sobel_mean": sobel_mean,
            "connected_components": connected_components,
            "sat_mean": sat_mean,
            "val_mean": val_mean,
            "hist_r": hist_r.tolist(),
            "hist_g": hist_g.tolist(),
            "hist_b": hist_b.tolist(),
        }

    except Exception as e:
        return {"file": os.path.basename(img_path), "error": str(e)}


if __name__ == "__main__":
    # PyInstaller onefile 下 __file__ 会指向临时解包目录，不能用来定位图片。
    # 默认扫描当前工作目录；也允许手动传入图片目录。
    import sys

    dir_path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    dir_path = os.path.abspath(dir_path)

    # 获取所有 JPEG/PNG 文件
    all_images = [
        os.path.join(dir_path, f)
        for f in os.listdir(dir_path)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    if not all_images:
        print(f"未找到图片文件: {dir_path}")
        raise SystemExit(1)

    # 按文件大小排序（升序）并只取前10个最小
    all_images.sort(key=lambda f: os.path.getsize(f))
    images_to_probe = all_images[:10]

    # 分析并打印结果
    for img_path in images_to_probe:
        result = analyze_image(img_path)
        print(f"分析文件: {result['file']}")
        print(f"  白色比例      : {result.get('white_ratio', 'N/A'):.3f}")
        print(f"  黑色比例      : {result.get('black_ratio', 'N/A'):.3f}")
        print(f"  边缘密度      : {result.get('edge_density', 'N/A'):.3f}")
        print(f"  灰度均值      : {result.get('gray_mean', 'N/A'):.1f}")
        print(f"  灰度标准差    : {result.get('gray_std', 'N/A'):.1f}")
        print(f"  Sobel 梯度均值: {result.get('sobel_mean', 'N/A'):.3f}")
        print(f"  连通域数量    : {result.get('connected_components', 'N/A')}")
        print(f"  饱和度均值    : {result.get('sat_mean', 'N/A'):.1f}")
        print(f"  明度均值      : {result.get('val_mean', 'N/A'):.1f}")

        # 可选打印 RGB 直方图
        print("  RGB直方图(16 bins)：")
        for channel, hist in zip(["R", "G", "B"], ["hist_r", "hist_g", "hist_b"]):
            h = result.get(hist, [])
            if h:
                hist_str = ", ".join(f"{v:.3f}" for v in h)
                print(f"    {channel}: [{hist_str}]")
        print("-" * 60)
