# Python 增强版矢量图形编译器

## 运行方法

```bash
pip install -r requirements.txt
python vector_editor.py
```

程序主体仍然使用 `tkinter`，新增的高清 PNG 渲染使用 `Pillow`，图形统计分析优先使用 `NumPy`。

## 新增功能

- 正常中文界面，新增圆角矩形、星形、云形等图元。
- 支持撤销/重做、图层列表、网格显示和网格吸附。
- 支持鼠标拖动框选多个图元，并对选中图元统一移动、删除、复制、粘贴、置顶、置底和样式修改。
- 支持 DSL 编译器：用脚本描述图元和连线，一键生成流程图或结构图。
- 支持 SVG 矢量导出，方便继续编辑或放入报告。
- 支持基于 Pillow 的 1x-4x 高清 PNG 导出，不再依赖 Windows 截图接口。
- 支持图形分析：统计图元数量、覆盖率、平均连线长度和类型分布。
- 支持自动流程图排版、居中、对齐、旋转、缩放、镜像、裁剪等编辑操作。

## DSL 示例

```text
style fill=#eff6ff stroke=#1d4ed8 lineWidth=2 fontSize=16
terminator start 120 70 150 64 "开始"
rect input 120 180 150 76 "读取数据"
diamond check 110 310 170 96 "是否有效"
document report 430 180 180 96 "生成报告"
terminator end 450 340 150 64 "结束"
line start input
line input check
curve check report
line report end
```

图元命令格式：

```text
图元类型 名称 x y w h "显示文字"
```

连线命令格式：

```text
line 起点名称 终点名称
curve 起点名称 终点名称
```

支持的图元类型包括：`rect`、`roundrect`、`ellipse`、`diamond`、`terminator`、`document`、`star`、`cloud`、`resistor`、`capacitor`、`text`。

## 数据格式

JSON 文件仍保存为可继续编辑的矢量数据，每个图元包含 `type`、`x`、`y`、`w`、`h`、`rotation`、`flipX`、`flipY`、`fill`、`stroke`、`lineWidth`、`fontSize`、`text` 等字段。曲线会额外保存 `control` 控制点，自由曲线会额外保存 `points` 点列。
