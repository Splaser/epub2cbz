# EPUB/PDF to CBZ Converter

**自动将 EPUB 漫画或 PDF 图书转换为 CBZ 文件。**

---

## 功能

- 自动扫描当前目录下的 `.epub` 文件
- HTML解析抽取漫画页
- 图片过滤：去除广告页、尾页和高留白垃圾图
- 自动拆页：横置跨页拆左右、上下堆叠拆上下
- 自动命名 CBZ 文件，保留中文漫画名 + 卷/期/特典
- 支持期刊特刊、合刊、番外、月刊等多种格式
- 生成 CBZ 后自动保存在 EPUB 同目录
- 独立的 PDF 入口自动扫描当前系列目录下的 `.pdf` 文件
- PDF 优先无损提取铺满整页的 JPEG，复杂页面回退到 300 DPI 逐页渲染
- PDF 保留原始页序，不执行自动拆页

---

## 安装依赖

使用 Python 3.10+ 建议：

```bash
pip install -r requirements.txt
```

`requirements.txt` 示例内容：

```
Pillow
PyMuPDF
rapidocr
onnxruntime
numpy
opencv-python
beautifulsoup4
```

---

## 编译 EXE

使用 PyInstaller 分别打包 EPUB 和 PDF 入口：

```bash
pyinstaller --onefile --name epub2cbz main.py
pyinstaller --onefile --name pdf2cbz --collect-all rapidocr --collect-all onnxruntime pdf_main.py
```

生成的 exe 文件可直接在 Windows 下运行。

---

## 使用方法

### EPUB

1. 将 `epub2cbz.exe` 放在 EPUB 系列目录
2. 双击或命令行运行：
```bash
epub2cbz.exe
```
3. 程序会自动扫描当前目录的 EPUB 文件，生成 CBZ：

```
漫画名 - 第001卷.cbz
漫画名 - 特典.cbz
```

### PDF

1. 将 `pdf2cbz.exe` 放在 PDF 系列目录，例如 `掌机迷/`
2. 双击或命令行运行：

```bash
pdf2cbz.exe
```

3. 程序会按文件名排序转换当前目录下的全部 PDF，并将 CBZ 写回同一目录。

PDF 期刊文件名会转换为 Kavita 可识别的 Volume/Special 格式：

```text
掌机迷vol037.pdf       -> 掌机迷 v037.cbz
掌机迷vol037副刊.pdf   -> 掌机迷 SP037 副刊.cbz
掌机迷vol073~074.pdf   -> 掌机迷 v073-074 合刊.cbz
```

每个 PDF 生成的 CBZ 都包含根目录 `ComicInfo.xml`。ComicInfo 记录系列名、标题、页数和
Magazine/Special 类型；Volume、Number 和 Count 留空，由 Kavita 按上述文件名解析编号，
避免合刊范围或副刊标记被元数据覆盖。

PDF 转换还会对开头连续最多 3 页执行离线 OCR。只有命中免责声明标题及版权/责任等语义，
或同时命中至少 4 类声明语义时才会删除；遇到第一张正常页后立即停止检查，避免误删正文、
目录或编辑寄语。PDF 不运行 EPUB 使用的全书 OpenCV 垃圾页扫描。

---

## 项目结构（模块化）

```
epub2cbz/
├─ main.py
├─ pdf_main.py
├─ pdf/
│  ├─ pdf_to_cbz.py
│  └─ pdf_utils.py
├─ parser/
│   └─ html_parser.py
├─ images/
│   ├─ filter.py
│   └─ splitter.py
├─ builder/
│   └─ cbz_builder.py
├─ utils/
│   ├─ consts.py
│   ├─ epub_utils.py
│   └─ metadata_utils.py
└─ requirements.txt
```

---

## 注意事项

- 文件名中带网站或站点的方括号会自动删除
- 自动生成 CBZ 名称严格复刻原版逻辑
- 支持多卷、多期、特刊、番外等多种 EPUB 漫画格式
