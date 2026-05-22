# EPUB to CBZ Converter

**自动将 EPUB 漫画转换为 CBZ 文件，支持拆页、过滤垃圾页和自动命名。**

---

## 功能

- 自动扫描当前目录下的 `.epub` 文件
- HTML解析抽取漫画页
- 图片过滤：去除广告页、尾页和高留白垃圾图
- 自动拆页：横置跨页拆左右、上下堆叠拆上下
- 自动命名 CBZ 文件，保留中文漫画名 + 卷/期/特典
- 支持期刊特刊、合刊、番外、月刊等多种格式
- 生成 CBZ 后自动保存在 EPUB 同目录

---

## 安装依赖

使用 Python 3.10+ 建议：

```bash
pip install -r requirements.txt
```

`requirements.txt` 示例内容：

```
Pillow
numpy
```

---

## 编译 EXE

使用 PyInstaller 打包成单文件 exe：

```bash
pyinstaller --onefile main.py
```

生成的 exe 文件可直接在 Windows 下运行。

---

## 使用方法

1. 将 `main.exe` 放在 EPUB 所在目录
2. 双击或命令行运行：
```bash
main.exe
```
3. 程序会自动扫描当前目录的 EPUB 文件，生成 CBZ：

```
漫画名 - 第001卷.cbz
漫画名 - 特典.cbz
```

---

## 项目结构（模块化）

```
epub2cbz/
├─ main.py
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
