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
- PDF 优先无损提取铺满整页的 JPEG；复杂或损坏页面按书籍原生扫描尺寸渲染为 WebP
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
pypdfium2
rapidocr
onnxruntime
numpy
opencv-python
beautifulsoup4
```

---

## 编译 EXE

使用 PyInstaller 打包 EPUB 入口：

```bash
pyinstaller --onefile --name epub2cbz main.py
```

Windows PowerShell 也可以直接运行项目内的固定打包脚本：

```powershell
.\build_pdf.ps1
```

PDF 入口请使用固定脚本，不要直接运行 `pyinstaller --onefile pdf_main.py`：RapidOCR 的 Python 模块虽然会被发现，
但 `default_models.yaml` 和 ONNX 模型等数据文件不会自动包含在 EXE 中。固定脚本还会排除
Torch、OpenVINO、Paddle 等未使用推理后端，并打包 PDFium 与 Poppler 备用渲染器。

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
   如果同名 CBZ 已存在且封面正常，则在解码 PDF 前直接跳过；空白或损坏封面的旧 CBZ
   会自动重建。需要整批无条件重建时运行 `pdf2cbz.exe --force`。

PDF 页面优先由 PyMuPDF 无损提取或渲染；检测到异常纯白页时，按 PDFium、Poppler 顺序
自动重试。渲染尺寸从同一本书的正常扫描页推断，并用 WebP 控制体积，避免损坏页盲目
按 300 DPI 放大。只有三个渲染器都无法恢复时才将该书标记为失败，不再静默生成白页 CBZ。

PDF 期刊文件名会转换为 Kavita 可识别的 Volume/Special 格式：

```text
掌机迷vol037.pdf       -> 掌机迷 v037.cbz
掌机迷vol037副刊.pdf   -> 掌机迷 SP037 副刊.cbz
掌机迷vol073~074.pdf   -> 掌机迷 v073-074 合刊.cbz
游戏机实用技术 2002增刊.pdf -> 游戏机实用技术 SP000 2002增刊.cbz
```

文件名命中副刊、增刊、特刊、别册、攻略、典藏/珍藏、纪念、周年、专门志、之书、档案、大全、特辑或专辑时，
按 Special 处理。有明确 `VOL`/总编号时使用该编号；无主刊编号或开头只是年份时使用
`SP000` 并保留原标题。
主刊或有编号特刊只接受 1–1500 的期号；更大数字（如 2002）不作为总编号解析。
`UCG Vol.029` 这类系列别名会回落到当前文件夹作为系列名；主刊文件名中的年月、A/B/AB
分期标记以及 `CRAZ/full_CRAZ` 发布组标记不写入 CBZ 名称，只保留总编号。

每个 PDF 生成的 CBZ 都包含根目录 `ComicInfo.xml`。ComicInfo 记录系列名、标题、页数和
Magazine/Special 类型；Volume、Number 和 Count 留空，由 Kavita 按上述文件名解析编号，
避免合刊范围或副刊标记被元数据覆盖。

PDF 转换还会对开头连续最多 3 页执行离线 OCR。只有页面上半部命中免责声明标题及版权/责任等语义，
或同时命中至少 4 类声明语义时才会删除；遇到第一张正常页后立即停止检查，避免误删正文、
目录、编辑寄语及带底部免责声明的封面。同一次批量运行中，OCR 确认过的免责声明页会记录为内存图片指纹；后续
PDF 优先做快速相似度匹配，只有未匹配时才回退 OCR。PDF 不运行 EPUB 使用的全书 OpenCV
垃圾页扫描。

把一个或多个 PDF 直接拖到 `pdf_main.exe` 上时，只转换拖入的文件，并进入直接转换模式：
不执行广告/免责声明图片指纹探测，也不对前三页执行关键字 OCR，所有页面都会保留。

中文杂志文件名支持把 `创刊号 YYYY.MM` 识别为 `v001`，并把 `第06期 YYYY.MM`
这类名称按期号识别为 `v006`；出版年月不会写入输出文件名。带 `试刊VOL.1/2`
的早期刊物会分别识别为 `SP001/SP002`，不占用正式刊物的卷号。

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
