# -*- coding: utf-8 -*-
"""Generate a Word development report for the vector editor project.

The environment does not require python-docx; this script writes a minimal
OpenXML .docx package directly.
"""

from __future__ import annotations

import datetime as _dt
import html
import zipfile
from pathlib import Path


OUT = Path("Python矢量图编辑器开发报告.docx")


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def r(text: str, bold: bool = False, size: int | None = None) -> str:
    props = []
    if bold:
        props.append("<w:b/>")
    if size:
        half_points = size * 2
        props.append(f'<w:sz w:val="{half_points}"/><w:szCs w:val="{half_points}"/>')
    prop_xml = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    preserve = ' xml:space="preserve"' if text.startswith(" ") or text.endswith(" ") else ""
    return f"<w:r>{prop_xml}<w:t{preserve}>{esc(text)}</w:t></w:r>"


def p(text: str = "", style: str | None = None, align: str | None = None, bold: bool = False, size: int | None = None) -> str:
    p_props = []
    if style:
        p_props.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        p_props.append(f'<w:jc w:val="{align}"/>')
    prop_xml = f"<w:pPr>{''.join(p_props)}</w:pPr>" if p_props else ""
    return f"<w:p>{prop_xml}{r(text, bold=bold, size=size)}</w:p>"


def bullet(text: str) -> str:
    return (
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        f"{r(text)}</w:p>"
    )


def code(text: str) -> str:
    return (
        '<w:p><w:pPr><w:pStyle w:val="Code"/></w:pPr>'
        f"{r(text)}</w:p>"
    )


def table(rows: list[list[str]]) -> str:
    xml = [
        "<w:tbl>",
        "<w:tblPr><w:tblStyle w:val=\"TableGrid\"/><w:tblW w:w=\"0\" w:type=\"auto\"/></w:tblPr>",
    ]
    for row in rows:
        xml.append("<w:tr>")
        for cell in row:
            xml.append(
                "<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr>"
                f"{p(cell)}</w:tc>"
            )
        xml.append("</w:tr>")
    xml.append("</w:tbl>")
    return "".join(xml)


def document_xml() -> str:
    today = _dt.date.today().strftime("%Y年%m月%d日")
    body: list[str] = []

    body += [
        p("Python矢量图编辑器开发报告", align="center", bold=True, size=22),
        p("计算机图形学大作业", align="center", size=14),
        p("项目名称：基于 Tkinter 的矢量图形编辑系统", align="center"),
        p("开发语言：Python 3", align="center"),
        p(f"生成日期：{today}", align="center"),
        p(),
        p("摘要", "Heading1"),
        p(
            "本项目实现了一个桌面端矢量图形编辑器，使用 Python 标准库 Tkinter 构建界面与画布，"
            "支持基础几何图元、流程图图元、电路符号、直线箭头、二次贝塞尔曲线和自由曲线的绘制。"
            "系统以可编辑的图元数据结构保存作品，并提供选择、移动、复制、粘贴、删除、置顶、置底、"
            "样式修改、几何变换、JSON 存取和 PNG 导出等功能。"
        ),
        p("关键词：计算机图形学；矢量图形；Tkinter；贝塞尔曲线；图形变换；JSON", bold=True),
        p("目录", "Heading1"),
        p("1 项目概述"),
        p("2 需求分析"),
        p("3 系统总体设计"),
        p("4 数据结构设计"),
        p("5 关键算法与实现"),
        p("6 功能模块说明"),
        p("7 测试与运行结果"),
        p("8 总结与展望"),
    ]

    body += [
        p("1 项目概述", "Heading1"),
        p(
            "矢量图形编辑器是计算机图形学中典型的交互式绘图应用。本项目围绕“图元建模、图形绘制、"
            "坐标变换、曲线生成、命中检测、文件序列化”等核心内容展开，完成了一个可运行、可编辑、"
            "可保存的图形编辑系统。程序入口为 vector_editor.py，运行命令如下："
        ),
        code("python vector_editor.py"),
        p(
            "程序启动后会创建 1380×780 的主窗口，左侧为工具栏，中间为绘图区，右侧为对象操作与属性面板。"
            "画布逻辑尺寸为 1100×680，并显示浅色网格以辅助定位。"
        ),
        p("2 需求分析", "Heading1"),
        p("2.1 功能需求", "Heading2"),
        bullet("支持矩形、椭圆、菱形判断框、开始/结束框、文档框、文本等常用图形绘制。"),
        bullet("支持电阻、电容等课程相关示意图元，以及直线箭头、曲线箭头和自由手绘曲线。"),
        bullet("支持对象选择、拖拽移动、复制、粘贴、删除、置顶和置底。"),
        bullet("支持填充色、描边色、线宽、字号和文字内容编辑。"),
        bullet("支持旋转、缩放、水平镜像、垂直镜像和裁剪到画布。"),
        bullet("支持保存为 JSON 以便后续继续编辑，支持导出当前画布为 PNG 图片。"),
        p("2.2 非功能需求", "Heading2"),
        bullet("界面操作直观，绘制和编辑操作尽量通过鼠标拖拽完成。"),
        bullet("图形数据保持矢量化，保存文件不应只是截图，而应保留图元类型、坐标和样式。"),
        bullet("尽量减少第三方依赖，项目主体仅使用 Python 标准库，便于在教学环境中运行。"),
        p("3 系统总体设计", "Heading1"),
        p(
            "系统采用单文件、面向对象的结构设计，核心类为 VectorEditor。该类负责管理界面控件、画布事件、"
            "图元列表、当前工具、选中对象、剪贴板和文件操作。绘制流程可概括为：用户选择工具并在画布上操作，"
            "事件处理函数更新图元数据，render 方法清空并重绘画布。"
        ),
        table(
            [
                ["模块", "主要职责"],
                ["界面构建模块", "创建顶部按钮区、左侧工具栏、中央 Canvas 和右侧属性面板。"],
                ["事件交互模块", "处理鼠标按下、拖动、释放以及 Delete、Ctrl+C、Ctrl+V、Ctrl+S 快捷键。"],
                ["图元绘制模块", "根据图元 type 分发到矩形、椭圆、曲线、电路符号等绘制函数。"],
                ["几何变换模块", "实现旋转、缩放、镜像、裁剪以及坐标归一化。"],
                ["文件模块", "实现 JSON 保存/加载与 PNG 导出。"],
            ]
        ),
        p("4 数据结构设计", "Heading1"),
        p(
            "每一个图元都保存为一个字典对象，所有图元按绘制层级顺序存放在 self.shapes 列表中。列表越靠后，"
            "绘制层级越靠上，因此置顶操作就是将图元移动到列表末尾，置底操作则移动到列表开头。"
        ),
        table(
            [
                ["字段", "含义"],
                ["id", "图元唯一标识，用于选中和操作。"],
                ["type", "图元类型，如 rect、ellipse、curve、freehand、text 等。"],
                ["x, y, w, h", "图元位置与尺寸，直线和曲线中 w、h 表示终点相对起点的偏移。"],
                ["rotation", "旋转角度，单位为度。"],
                ["flipX, flipY", "水平/垂直镜像状态。"],
                ["fill, stroke, lineWidth", "填充色、描边色和线宽。"],
                ["fontSize, text", "文字大小与图元文字内容。"],
                ["control", "曲线控制点，仅曲线图元使用。"],
                ["points", "自由曲线采样点数组，仅自由曲线使用。"],
            ]
        ),
        p("典型图元数据示例："),
        code('{"type": "rect", "x": 90, "y": 175, "w": 135, "h": 72, "fill": "#f8fafc", "stroke": "#334155", "text": "读取数据"}'),
        p("5 关键算法与实现", "Heading1"),
        p("5.1 多边形近似与参数化绘制", "Heading2"),
        p(
            "矩形、菱形等图元可直接由顶点构成；椭圆通过 40 个采样点近似，按照参数方程 "
            "x = cx + cos(t)·rx，y = cy + sin(t)·ry 生成轮廓点；开始/结束框和文档框也通过采样点构造特殊轮廓。"
        ),
        p("5.2 坐标变换", "Heading2"),
        p(
            "rotate_point 函数先将点平移到以图元中心为原点的局部坐标系，再根据 flipX、flipY 执行镜像，"
            "最后使用二维旋转矩阵完成旋转，并平移回画布坐标。其核心公式为："
        ),
        code("x' = cx + x·cosθ - y·sinθ,  y' = cy + x·sinθ + y·cosθ"),
        p("5.3 曲线生成", "Heading2"),
        p(
            "曲线箭头采用二次贝塞尔曲线。给定起点 P0、控制点 P1、终点 P2，程序按 t 从 0 到 1 采样，"
            "生成曲线上的点，用于命中检测和视觉辅助。公式如下："
        ),
        code("B(t) = (1-t)^2·P0 + 2(1-t)t·P1 + t^2·P2, 0 ≤ t ≤ 1"),
        p("5.4 命中检测", "Heading2"),
        p(
            "普通封闭图元使用边界框近似检测；直线、曲线和自由曲线则计算鼠标点到线段或折线的最短距离。"
            "distance_to_segment 函数将鼠标点投影到线段方向上，并用 clamp 将投影参数限制在 0 到 1 之间，"
            "从而得到最近点距离。"
        ),
        p("5.5 PNG 导出", "Heading2"),
        p(
            "PNG 导出分为两步：先通过 Windows GDI 接口截取 Canvas 像素，再由 write_png 函数手工写入 PNG 文件结构。"
            "该函数构造 PNG 文件头、IHDR、IDAT 和 IEND 数据块，并使用 zlib 压缩像素数据。"
        ),
        p("6 功能模块说明", "Heading1"),
        table(
            [
                ["功能", "实现说明"],
                ["新建", "清空 shapes 列表并重绘画布。"],
                ["绘图", "按当前工具创建 shape_base 数据对象，拖拽时动态更新尺寸或点集。"],
                ["选择与移动", "hit_test 从顶层向底层查找命中图元，拖动时根据鼠标位移更新坐标。"],
                ["复制粘贴", "使用 deepcopy 复制图元，粘贴时生成新 id 并偏移 24 像素。"],
                ["样式修改", "属性面板同步选中对象的填充、描边、线宽、字号和文字。"],
                ["层级调整", "通过调整图元在 shapes 列表中的位置改变绘制顺序。"],
                ["JSON 存取", "保存 app、version、canvas 和 shapes 字段，加载时恢复 shapes。"],
                ["示例图", "load_sample 预置流程图、电路符号和自由曲线，便于展示功能。"],
            ]
        ),
        p("7 测试与运行结果", "Heading1"),
        p("7.1 测试环境", "Heading2"),
        table(
            [
                ["项目", "说明"],
                ["操作系统", "Windows 桌面环境"],
                ["语言版本", "Python 3"],
                ["主要依赖", "tkinter、json、math、ctypes、zlib、struct 等标准库"],
                ["运行命令", "python vector_editor.py"],
            ]
        ),
        p("7.2 测试用例", "Heading2"),
        table(
            [
                ["测试项", "操作步骤", "预期结果"],
                ["基础绘图", "选择矩形、椭圆、菱形并拖拽绘制", "画布出现对应图元，边框和填充正常。"],
                ["曲线编辑", "绘制曲线后切回选择工具并拖动控制点", "曲线弯曲方向和幅度随控制点变化。"],
                ["对象操作", "选中对象后移动、复制、粘贴、删除", "图元位置与数量按操作正确变化。"],
                ["几何变换", "对选中图元执行旋转、缩放、镜像", "图元形状按预期发生变换。"],
                ["文件保存", "保存 JSON 后重新加载", "图元类型、坐标、颜色和文字保持一致。"],
                ["图片导出", "选择保存图片", "生成 PNG 图片，可用于报告或展示。"],
            ]
        ),
        p(
            "经语法检查，vector_editor.py 可通过 Python 编译检查。结合源码逻辑，系统能够完成课程大作业要求的"
            "交互绘图、矢量数据保存、曲线控制和几何变换等核心功能。"
        ),
        p("8 总结与展望", "Heading1"),
        p(
            "本项目以 Tkinter Canvas 为基础，实现了一个功能较完整的矢量图形编辑器。项目的主要特点是数据结构清晰、"
            "图元可继续编辑、曲线和自由线条支持较好，并且不依赖复杂外部框架，适合作为计算机图形学课程中图形生成、"
            "图形变换和交互设计的综合实践。"
        ),
        p("后续可改进方向包括：", "Heading2"),
        bullet("增加撤销/重做栈，提高编辑容错能力。"),
        bullet("增加多选、组合、对齐、吸附和缩放画布等专业编辑功能。"),
        bullet("扩展 SVG 导入/导出能力，使作品具备更好的跨平台兼容性。"),
        bullet("修复部分源码中文字符串在不同编码环境下的显示问题，提高可读性和展示效果。"),
        p("参考资料", "Heading1"),
        bullet("Python 官方文档：tkinter 图形界面库。"),
        bullet("PNG 文件格式基础结构：IHDR、IDAT、IEND 数据块。"),
        bullet("计算机图形学基础：二维几何变换、参数曲线与交互式绘图。"),
    ]

    sect = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}{sect}</w:body></w:document>"
    )


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/><w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>
    <w:pPr><w:spacing w:after="120" w:line="360" w:lineRule="auto"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:before="360" w:after="180"/><w:outlineLvl w:val="0"/></w:pPr>
    <w:rPr><w:b/><w:rFonts w:eastAsia="黑体"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="1"/></w:pPr>
    <w:rPr><w:b/><w:rFonts w:eastAsia="黑体"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Code">
    <w:name w:val="Code"/><w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="80"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="等线"/><w:sz w:val="20"/></w:rPr>
  </w:style>
  <w:style w:type="table" w:styleId="TableGrid">
    <w:name w:val="Table Grid"/><w:basedOn w:val="TableNormal"/><w:uiPriority w:val="59"/><w:qFormat/>
    <w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="888888"/><w:left w:val="single" w:sz="4" w:space="0" w:color="888888"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="888888"/><w:right w:val="single" w:sz="4" w:space="0" w:color="888888"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="888888"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="888888"/></w:tblBorders></w:tblPr>
  </w:style>
</w:styles>
"""

NUMBERING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="singleLevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>
"""

CORE = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Python矢量图编辑器开发报告</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{_dt.datetime.now().isoformat(timespec='seconds')}Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{_dt.datetime.now().isoformat(timespec='seconds')}Z</dcterms:modified>
</cp:coreProperties>
"""

APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Word</Application>
</Properties>
"""


def main() -> None:
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
        zf.writestr("word/document.xml", document_xml())
        zf.writestr("word/styles.xml", STYLES)
        zf.writestr("word/numbering.xml", NUMBERING)
        zf.writestr("docProps/core.xml", CORE)
        zf.writestr("docProps/app.xml", APP)
    print(OUT.resolve())


if __name__ == "__main__":
    main()
