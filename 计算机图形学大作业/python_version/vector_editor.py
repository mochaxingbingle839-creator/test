
"""计算机图形学大作业：增强版 Python/Tkinter 矢量图编译器。"""

import json
import math
import re
import time
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from xml.sax.saxutils import escape

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - optional dependency
    Image = ImageDraw = ImageFont = None


CANVAS_W = 1100
CANVAS_H = 680
GRID = 24
APP_VERSION = "2.1"
SOLID_3D_TYPES = {"rect", "roundrect", "ellipse", "diamond", "terminator", "document", "star", "cloud"}


def uid():
    return f"s_{int(time.time() * 1000)}_{time.perf_counter_ns() % 100000}"


def clamp(value, low, high):
    return max(low, min(high, value))


def rotate_point(px, py, cx, cy, angle_deg, flip_x=False, flip_y=False):
    x = px - cx
    y = py - cy
    if flip_x:
        x = -x
    if flip_y:
        y = -y
    angle = math.radians(angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a


def color_or_none(value):
    if not value or value == "transparent":
        return None
    return value


def shade_color(value, factor):
    color = color_or_none(value) or "#f8fafc"
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#f8fafc"
    r = clamp(int(color[1:3], 16) * factor, 0, 255)
    g = clamp(int(color[3:5], 16) * factor, 0, 255)
    b = clamp(int(color[5:7], 16) * factor, 0, 255)
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def flatten(points):
    return [value for point in points for value in point]


def shape_center(shape):
    return shape["x"] + shape["w"] / 2, shape["y"] + shape["h"] / 2


def font_for(size):
    names = [
        "msyh.ttc",
        "simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    if ImageFont is None:
        return None
    for name in names:
        try:
            return ImageFont.truetype(name, int(size))
        except OSError:
            continue
    return ImageFont.load_default()


class VectorEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("矢量图形编译器 - Python 增强版")

        self.shapes = []
        self.selected_id = None
        self.selected_ids = set()
        self.selection_box = None
        self.tool = tk.StringVar(value="select")
        self.fill = tk.StringVar(value="#f4f8ff")
        self.stroke = tk.StringVar(value="#1f2937")
        self.line_width = tk.IntVar(value=2)
        self.font_size = tk.IntVar(value=16)
        self.text_value = tk.StringVar(value="文本")
        self.depth_3d = tk.IntVar(value=28)
        self.preview_angle_x = tk.IntVar(value=55)
        self.preview_angle_y = tk.IntVar(value=-25)
        self.snap_to_grid = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self.export_scale = tk.IntVar(value=2)

        self.clipboard = None
        self.drag = None
        self.current = None
        self.history = []
        self.redo_stack = []
        self.suspend_history = False

        self._build_ui()
        self._bind_events()
        self.load_sample(record=False)
        self.push_history("initial")

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill=tk.X)
        ttk.Label(top, text="矢量图形编译器", font=("Microsoft YaHei UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Button(top, text="新建", command=self.new_file).pack(side=tk.RIGHT, padx=3)
        ttk.Button(top, text="保存 JSON", command=self.save_json).pack(side=tk.RIGHT, padx=3)
        ttk.Button(top, text="加载 JSON", command=self.load_json).pack(side=tk.RIGHT, padx=3)
        ttk.Button(top, text="导出 SVG", command=self.save_svg).pack(side=tk.RIGHT, padx=3)
        ttk.Button(top, text="导出 PNG", command=self.save_image).pack(side=tk.RIGHT, padx=3)

        body = ttk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)

        tools = ttk.Frame(body, padding=8)
        tools.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(tools, text="工具箱", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))
        tool_defs = [
            ("选择", "select"),
            ("矩形", "rect"),
            ("圆角矩形", "roundrect"),
            ("椭圆", "ellipse"),
            ("判断菱形", "diamond"),
            ("开始/结束", "terminator"),
            ("文档", "document"),
            ("星形", "star"),
            ("云形", "cloud"),
            ("电阻", "resistor"),
            ("电容", "capacitor"),
            ("直线箭头", "line"),
            ("曲线箭头", "curve"),
            ("自由曲线", "freehand"),
            ("文本", "text"),
        ]
        for label, value in tool_defs:
            ttk.Radiobutton(tools, text=label, value=value, variable=self.tool).pack(fill=tk.X, pady=2)

        ttk.Separator(tools).pack(fill=tk.X, pady=10)
        ttk.Checkbutton(tools, text="显示网格", variable=self.show_grid, command=self.render).pack(anchor=tk.W)
        ttk.Checkbutton(tools, text="吸附网格", variable=self.snap_to_grid).pack(anchor=tk.W)
        ttk.Button(tools, text="DSL 编译器", command=self.open_dsl_compiler).pack(fill=tk.X, pady=(8, 2))
        ttk.Button(tools, text="图形分析", command=self.show_analysis).pack(fill=tk.X, pady=2)

        center = ttk.Frame(body, padding=(0, 8, 0, 8))
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            center,
            width=CANVAS_W,
            height=CANVAS_H,
            bg="white",
            highlightthickness=1,
            highlightbackground="#d7dce3",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        panel = ttk.Frame(body, padding=8)
        panel.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Label(panel, text="对象操作", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        self._button_row(panel, [("复制", self.copy_selected), ("粘贴", self.paste_clipboard), ("删除", self.delete_selected)])
        self._button_row(panel, [("撤销", self.undo), ("重做", self.redo)])
        self._button_row(panel, [("置顶", self.bring_to_front), ("置底", self.send_to_back)])

        ttk.Separator(panel).pack(fill=tk.X, pady=10)
        ttk.Label(panel, text="智能排版", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        self._button_row(panel, [("自动流程图", self.auto_flow_layout), ("居中", self.center_selected)])
        self._button_row(panel, [("左对齐", lambda: self.align_selected("left")), ("顶对齐", lambda: self.align_selected("top"))])

        ttk.Separator(panel).pack(fill=tk.X, pady=10)
        ttk.Label(panel, text="样式", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Button(panel, text="填充颜色", command=lambda: self.choose_color(self.fill, "fill")).pack(fill=tk.X, pady=2)
        ttk.Button(panel, text="描边颜色", command=lambda: self.choose_color(self.stroke, "stroke")).pack(fill=tk.X, pady=2)
        ttk.Label(panel, text="线宽").pack(anchor=tk.W, pady=(6, 0))
        ttk.Spinbox(panel, from_=1, to=24, textvariable=self.line_width, command=self.apply_style).pack(fill=tk.X)
        ttk.Label(panel, text="字号").pack(anchor=tk.W, pady=(6, 0))
        ttk.Spinbox(panel, from_=8, to=72, textvariable=self.font_size, command=self.apply_style).pack(fill=tk.X)
        ttk.Label(panel, text="文字").pack(anchor=tk.W, pady=(6, 0))
        text_entry = ttk.Entry(panel, textvariable=self.text_value)
        text_entry.pack(fill=tk.X)
        text_entry.bind("<KeyRelease>", lambda _event: self.apply_style())

        ttk.Separator(panel).pack(fill=tk.X, pady=10)
        ttk.Label(panel, text="几何变换", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        self._button_row(panel, [("左转15°", lambda: self.rotate_selected(-15)), ("右转15°", lambda: self.rotate_selected(15))])
        self._button_row(panel, [("放大", lambda: self.scale_selected(1.15)), ("缩小", lambda: self.scale_selected(0.85))])
        self._button_row(panel, [("水平镜像", lambda: self.mirror_selected("x")), ("垂直镜像", lambda: self.mirror_selected("y"))])
        ttk.Button(panel, text="裁剪到画布", command=self.clip_to_canvas).pack(fill=tk.X, pady=2)

        ttk.Separator(panel).pack(fill=tk.X, pady=10)
        ttk.Label(panel, text="3D 立体", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(panel, text="挤出厚度").pack(anchor=tk.W, pady=(4, 0))
        ttk.Spinbox(panel, from_=0, to=120, textvariable=self.depth_3d).pack(fill=tk.X)
        self._button_row(panel, [("应用立体", self.apply_3d_depth), ("取消立体", self.clear_3d_depth)])
        ttk.Button(panel, text="打开 3D 预览", command=self.open_3d_preview).pack(fill=tk.X, pady=2)

        ttk.Separator(panel).pack(fill=tk.X, pady=10)
        ttk.Label(panel, text="PNG倍率").pack(anchor=tk.W)
        ttk.Spinbox(panel, from_=1, to=4, textvariable=self.export_scale).pack(fill=tk.X)
        ttk.Button(panel, text="载入示例图", command=self.load_sample).pack(fill=tk.X, pady=(8, 2))

        ttk.Label(panel, text="图层", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        self.layers = tk.Listbox(panel, height=8, exportselection=False)
        self.layers.pack(fill=tk.BOTH, expand=False)
        self.layers.bind("<<ListboxSelect>>", self.on_layer_select)

        self.status = ttk.Label(panel, text="未选择对象", foreground="#697386", wraplength=230)
        self.status.pack(fill=tk.X, pady=8)

    def _button_row(self, parent, buttons):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        for text, command in buttons:
            ttk.Button(row, text=text, command=command).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

    def _bind_events(self):
        self.canvas.bind("<Button-1>", self.on_down)
        self.canvas.bind("<B1-Motion>", self.on_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_up)
        self.root.bind("<Delete>", lambda _event: self.delete_selected())
        self.root.bind("<Control-c>", lambda _event: self.copy_selected())
        self.root.bind("<Control-v>", lambda _event: self.paste_clipboard())
        self.root.bind("<Control-s>", lambda _event: self.save_json())
        self.root.bind("<Control-z>", lambda _event: self.undo())
        self.root.bind("<Control-y>", lambda _event: self.redo())
        self.root.bind("<Control-a>", lambda _event: self.select_all())

    def push_history(self, _reason="edit"):
        if self.suspend_history:
            return
        snapshot = deepcopy({"shapes": self.shapes, "selected_id": self.selected_id, "selected_ids": sorted(self.selected_ids)})
        if self.history and self.history[-1] == snapshot:
            return
        self.history.append(snapshot)
        if len(self.history) > 80:
            self.history.pop(0)
        self.redo_stack.clear()

    def restore_snapshot(self, snapshot):
        self.suspend_history = True
        self.shapes = deepcopy(snapshot["shapes"])
        self.selected_id = snapshot.get("selected_id")
        self.selected_ids = set(snapshot.get("selected_ids", []))
        self.suspend_history = False
        self.sync_panel()
        self.render()

    def undo(self):
        if len(self.history) < 2:
            return
        self.redo_stack.append(self.history.pop())
        self.restore_snapshot(self.history[-1])

    def redo(self):
        if not self.redo_stack:
            return
        snapshot = self.redo_stack.pop()
        self.history.append(deepcopy(snapshot))
        self.restore_snapshot(snapshot)

    def snap(self, x, y):
        if not self.snap_to_grid.get():
            return x, y
        return round(x / GRID) * GRID, round(y / GRID) * GRID

    def shape_base(self, shape_type, x, y, w=120, h=70):
        labels = {
            "rect": "处理",
            "roundrect": "模块",
            "ellipse": "节点",
            "diamond": "判断",
            "terminator": "开始",
            "document": "文档",
            "star": "重点",
            "cloud": "云端",
            "text": self.text_value.get() or "文本",
        }
        return {
            "id": uid(),
            "type": shape_type,
            "x": float(x),
            "y": float(y),
            "w": float(w),
            "h": float(h),
            "rotation": 0,
            "flipX": False,
            "flipY": False,
            "fill": "transparent" if shape_type in ("line", "curve", "freehand", "resistor", "capacitor", "text") else self.fill.get(),
            "stroke": self.stroke.get(),
            "lineWidth": int(self.line_width.get()),
            "fontSize": int(self.font_size.get()),
            "depth3D": 0,
            "text": labels.get(shape_type, ""),
        }

    def selected_shape(self):
        return next((shape for shape in self.shapes if shape["id"] == self.selected_id), None)

    def selected_shapes(self):
        if self.selected_ids:
            return [shape for shape in self.shapes if shape["id"] in self.selected_ids]
        shape = self.selected_shape()
        return [shape] if shape else []

    def selection_bounds(self):
        shapes = self.selected_shapes()
        if not shapes:
            return None
        boxes = [self.bounds(shape) for shape in shapes]
        x1 = min(box[0] for box in boxes)
        y1 = min(box[1] for box in boxes)
        x2 = max(box[0] + box[2] for box in boxes)
        y2 = max(box[1] + box[3] for box in boxes)
        return x1, y1, x2 - x1, y2 - y1

    def set_selection(self, ids, primary_id=None):
        self.selected_ids = set(ids)
        if primary_id and primary_id in self.selected_ids:
            self.selected_id = primary_id
        elif self.selected_ids:
            self.selected_id = next((shape["id"] for shape in reversed(self.shapes) if shape["id"] in self.selected_ids), None)
        else:
            self.selected_id = None

    def render(self):
        self.canvas.delete("all")
        if self.show_grid.get():
            self.draw_grid()
        for shape in self.shapes:
            self.draw_shape(shape)
        for shape in self.selected_shapes():
            self.draw_selection(shape)
        if self.selection_box:
            self.draw_selection_box()
        self.update_layers()
        self.update_status()

    def draw_grid(self):
        for x in range(0, CANVAS_W + 1, GRID):
            self.canvas.create_line(x, 0, x, CANVAS_H, fill="#eef2f7")
        for y in range(0, CANVAS_H + 1, GRID):
            self.canvas.create_line(0, y, CANVAS_W, y, fill="#eef2f7")

    def draw_shape(self, shape):
        kind = shape["type"]
        if self.is_3d_shape(shape):
            self.draw_extruded_shape(shape)
        if kind in ("line", "curve"):
            self.draw_connector(shape)
        elif kind == "freehand":
            self.draw_freehand(shape)
        elif kind == "rect":
            self.draw_polygon_shape(shape, self.rect_points(shape))
            self.draw_center_text(shape)
        elif kind == "roundrect":
            self.draw_polygon_shape(shape, self.roundrect_points(shape))
            self.draw_center_text(shape)
        elif kind == "ellipse":
            self.draw_polygon_shape(shape, self.ellipse_points(shape))
            self.draw_center_text(shape)
        elif kind == "diamond":
            self.draw_polygon_shape(shape, self.diamond_points(shape))
            self.draw_center_text(shape)
        elif kind == "terminator":
            self.draw_polygon_shape(shape, self.terminator_points(shape))
            self.draw_center_text(shape)
        elif kind == "document":
            self.draw_polygon_shape(shape, self.document_points(shape))
            self.draw_center_text(shape)
        elif kind == "star":
            self.draw_polygon_shape(shape, self.star_points(shape))
            self.draw_center_text(shape)
        elif kind == "cloud":
            self.draw_polygon_shape(shape, self.cloud_points(shape))
            self.draw_center_text(shape)
        elif kind == "resistor":
            self.draw_polyline(shape, self.resistor_points(shape))
        elif kind == "capacitor":
            self.draw_capacitor(shape)
        elif kind == "text":
            self.draw_text(shape)

    def is_3d_shape(self, shape):
        return shape.get("depth3D", 0) > 0 and shape.get("type") in SOLID_3D_TYPES

    def extrusion_offset(self, shape):
        depth = float(shape.get("depth3D", 0))
        return depth * 0.72, -depth * 0.46

    def face_points(self, shape):
        table = {
            "rect": self.rect_points,
            "roundrect": self.roundrect_points,
            "ellipse": self.ellipse_points,
            "diamond": self.diamond_points,
            "terminator": self.terminator_points,
            "document": self.document_points,
            "star": self.star_points,
            "cloud": self.cloud_points,
        }
        return self.transformed(shape, table[shape["type"]](shape))

    def draw_extruded_shape(self, shape):
        front = self.face_points(shape)
        if len(front) < 3:
            return
        dx, dy = self.extrusion_offset(shape)
        back = [(x + dx, y + dy) for x, y in front]
        fill = shape.get("fill", "#f8fafc")
        stroke = shape.get("stroke", "#111827")
        side_fill = shade_color(fill, 0.78)
        top_fill = shade_color(fill, 1.08)
        self.canvas.create_polygon(
            flatten(back),
            fill=shade_color(fill, 0.9),
            outline=stroke,
            width=max(1, int(shape.get("lineWidth", 2) * 0.65)),
        )
        for i in range(len(front)):
            j = (i + 1) % len(front)
            shade = top_fill if front[i][1] + front[j][1] > back[i][1] + back[j][1] else side_fill
            self.canvas.create_polygon(
                flatten([front[i], front[j], back[j], back[i]]),
                fill=shade,
                outline=stroke,
                width=max(1, int(shape.get("lineWidth", 2) * 0.65)),
            )

    def transformed(self, shape, points):
        cx, cy = shape_center(shape)
        return [
            rotate_point(x, y, cx, cy, shape.get("rotation", 0), shape.get("flipX"), shape.get("flipY"))
            for x, y in points
        ]

    def draw_polygon_shape(self, shape, points):
        self.canvas.create_polygon(
            flatten(self.transformed(shape, points)),
            fill=shape["fill"] if shape["fill"] != "transparent" else "",
            outline=shape["stroke"],
            width=shape["lineWidth"],
            smooth=False,
        )

    def draw_polyline(self, shape, points):
        self.canvas.create_line(
            flatten(self.transformed(shape, points)),
            fill=shape["stroke"],
            width=shape["lineWidth"],
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )

    def rect_points(self, s):
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def roundrect_points(self, s, steps=8):
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        r = min(abs(w), abs(h)) * 0.22
        corners = [
            (x + w - r, y + r, -math.pi / 2, 0),
            (x + w - r, y + h - r, 0, math.pi / 2),
            (x + r, y + h - r, math.pi / 2, math.pi),
            (x + r, y + r, math.pi, math.pi * 1.5),
        ]
        points = []
        for cx, cy, a0, a1 in corners:
            for i in range(steps + 1):
                a = a0 + (a1 - a0) * i / steps
                points.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        return points

    def ellipse_points(self, s):
        cx, cy = shape_center(s)
        rx, ry = abs(s["w"]) / 2, abs(s["h"]) / 2
        return [(cx + math.cos(i / 48 * math.tau) * rx, cy + math.sin(i / 48 * math.tau) * ry) for i in range(48)]

    def diamond_points(self, s):
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        return [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]

    def terminator_points(self, s):
        return self.roundrect_points(s, steps=10)

    def document_points(self, s):
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        points = [(x, y), (x + w, y), (x + w, y + h * 0.78)]
        for i in range(12):
            t = i / 11
            points.append((x + w * (1 - t), y + h * (0.86 + 0.10 * math.sin(t * math.pi * 2))))
        points.append((x, y))
        return points

    def star_points(self, s):
        cx, cy = shape_center(s)
        outer = min(abs(s["w"]), abs(s["h"])) / 2
        inner = outer * 0.46
        points = []
        for i in range(10):
            radius = outer if i % 2 == 0 else inner
            angle = -math.pi / 2 + i * math.pi / 5
            points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
        return points

    def cloud_points(self, s):
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        cx, cy = shape_center(s)
        points = []
        for i in range(72):
            angle = i / 72 * math.tau
            bump = 1 + 0.13 * math.sin(5 * angle) + 0.08 * math.cos(8 * angle)
            points.append((cx + math.cos(angle) * w / 2 * bump, cy + math.sin(angle) * h / 2 * bump))
        points.append((x, y + h * 0.58))
        return points

    def resistor_points(self, s):
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        cy = y + h / 2
        amp = h * 0.28
        points = [(x, cy), (x + w * 0.15, cy)]
        for i in range(6):
            px = x + w * (0.15 + (i + 1) * 0.1)
            points.append((px, cy + (-amp if i % 2 == 0 else amp)))
        points.extend([(x + w * 0.85, cy), (x + w, cy)])
        return points

    def draw_capacitor(self, s):
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        cy = y + h / 2
        gap = w * 0.08
        plate = h * 0.35
        lines = [
            [(x, cy), (x + w / 2 - gap, cy)],
            [(x + w / 2 + gap, cy), (x + w, cy)],
            [(x + w / 2 - gap, cy - plate), (x + w / 2 - gap, cy + plate)],
            [(x + w / 2 + gap, cy - plate), (x + w / 2 + gap, cy + plate)],
        ]
        for points in lines:
            self.draw_polyline(s, points)

    def draw_connector(self, s):
        x1, y1 = s["x"], s["y"]
        x2, y2 = s["x"] + s["w"], s["y"] + s["h"]
        if s["type"] == "curve":
            cx, cy = self.curve_control_point(s)
            self.canvas.create_line(x1, y1, cx, cy, x2, y2, smooth=True, arrow=tk.LAST, fill=s["stroke"], width=s["lineWidth"])
        else:
            self.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, fill=s["stroke"], width=s["lineWidth"])

    def curve_control_point(self, s):
        if "control" in s:
            return s["control"]["x"], s["control"]["y"]
        return s["x"] + s["w"] / 2, min(s["y"], s["y"] + s["h"]) - abs(s["w"]) * 0.18

    def draw_freehand(self, s):
        points = s.get("points", [])
        if len(points) < 2:
            return
        flat = []
        for point in points:
            flat.extend((point["x"], point["y"]))
        self.canvas.create_line(
            flat,
            fill=s["stroke"],
            width=s["lineWidth"],
            smooth=True,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND,
        )

    def draw_center_text(self, s):
        if not s.get("text"):
            return
        cx, cy = shape_center(s)
        self.canvas.create_text(
            cx,
            cy,
            text=s["text"],
            fill=s["stroke"],
            font=("Microsoft YaHei UI", int(s.get("fontSize", 16))),
            width=max(30, abs(s["w"]) - 10),
        )

    def draw_text(self, s):
        options = {
            "text": s.get("text") or "文本",
            "fill": s["stroke"],
            "font": ("Microsoft YaHei UI", int(s.get("fontSize", 16))),
            "anchor": tk.NW,
        }
        try:
            options["angle"] = s.get("rotation", 0)
        except tk.TclError:
            pass
        self.canvas.create_text(s["x"], s["y"], **options)

    def draw_selection(self, s):
        x, y, w, h = self.bounds(s)
        self.canvas.create_rectangle(x - 5, y - 5, x + w + 5, y + h + 5, outline="#0f766e", dash=(5, 3), width=2)
        for hx, hy in [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]:
            self.canvas.create_rectangle(hx - 4, hy - 4, hx + 4, hy + 4, fill="#0f766e", outline="")
        if s["type"] == "curve":
            cx, cy = self.curve_control_point(s)
            x1, y1 = s["x"], s["y"]
            x2, y2 = s["x"] + s["w"], s["y"] + s["h"]
            self.canvas.create_line(x1, y1, cx, cy, x2, y2, fill="#0f766e", dash=(3, 3))
            self.canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#ffffff", outline="#0f766e", width=2)

    def draw_selection_box(self):
        x1, y1, x2, y2 = self.normalized_box(self.selection_box)
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#dbeafe", stipple="gray25", outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#2563eb", dash=(4, 3), width=2)

    def normalized_box(self, box):
        x1, y1, x2, y2 = box
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def shape_inside_box(self, shape, box):
        x1, y1, x2, y2 = self.normalized_box(box)
        sx, sy, sw, sh = self.bounds(shape)
        return x1 <= sx and y1 <= sy and sx + sw <= x2 and sy + sh <= y2

    def bounds(self, s):
        if s["type"] in ("line", "curve"):
            x2, y2 = s["x"] + s["w"], s["y"] + s["h"]
            xs = [s["x"], x2]
            ys = [s["y"], y2]
            if s["type"] == "curve":
                cx, cy = self.curve_control_point(s)
                xs.append(cx)
                ys.append(cy)
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        if s["type"] == "freehand":
            points = s.get("points", [])
            if not points:
                return s["x"], s["y"], 1, 1
            xs = [point["x"] for point in points]
            ys = [point["y"] for point in points]
            return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        return s["x"], s["y"], s["w"], s["h"]

    def on_down(self, event):
        point = self.snap(event.x, event.y)
        if self.tool.get() == "select":
            control_hit = self.curve_control_hit(point)
            if control_hit:
                self.set_selection([control_hit["id"]], control_hit["id"])
                self.drag = {"mode": "control", "start": point, "original": deepcopy(control_hit)}
                self.sync_panel()
                self.render()
                return
            hit = self.hit_test(point)
            add_mode = bool(event.state & 0x0001) or bool(event.state & 0x0004)
            if hit:
                if add_mode:
                    ids = set(self.selected_ids)
                    if hit["id"] in ids:
                        ids.remove(hit["id"])
                    else:
                        ids.add(hit["id"])
                    self.set_selection(ids, hit["id"] if hit["id"] in ids else None)
                    self.sync_panel()
                    self.render()
                    return
                if hit["id"] not in self.selected_ids:
                    self.set_selection([hit["id"]], hit["id"])
                originals = {shape["id"]: deepcopy(shape) for shape in self.selected_shapes()}
                self.drag = {"mode": "move", "start": point, "originals": originals}
                self.sync_panel()
                self.render()
                return
            if not add_mode:
                self.set_selection([])
            self.selection_box = (point[0], point[1], point[0], point[1])
            self.drag = {"mode": "marquee", "start": point}
            self.sync_panel()
            self.render()
            return

        shape = self.shape_base(self.tool.get(), point[0], point[1], 1, 1)
        if shape["type"] == "text":
            shape["w"], shape["h"] = 150, 30
        if shape["type"] == "freehand":
            shape["points"] = [{"x": point[0], "y": point[1]}]
        self.shapes.append(shape)
        self.set_selection([shape["id"]], shape["id"])
        self.current = {"start": point, "shape": shape}
        self.render()

    def on_move(self, event):
        point = self.snap(event.x, event.y)
        if self.current:
            sx, sy = self.current["start"]
            shape = self.current["shape"]
            if shape["type"] == "text":
                shape["x"], shape["y"] = point
            elif shape["type"] == "freehand":
                points = shape.setdefault("points", [])
                if not points or math.hypot(point[0] - points[-1]["x"], point[1] - points[-1]["y"]) >= 3:
                    points.append({"x": point[0], "y": point[1]})
                self.update_freehand_bounds(shape)
            else:
                shape["w"], shape["h"] = point[0] - sx, point[1] - sy
                if shape["type"] not in ("line", "curve", "freehand"):
                    self.normalize(shape)
            self.render()
            return
        if self.drag and self.drag.get("mode") == "marquee":
            sx, sy = self.drag["start"]
            self.selection_box = (sx, sy, point[0], point[1])
            self.render()
            return
        if self.drag and self.selected_shapes():
            dx = point[0] - self.drag["start"][0]
            dy = point[1] - self.drag["start"][1]
            shape = self.selected_shape()
            if self.drag.get("mode") == "control" and shape and shape["type"] == "curve":
                shape["control"] = {"x": point[0], "y": point[1]}
            else:
                originals = self.drag.get("originals", {})
                for shape in self.selected_shapes():
                    original = originals.get(shape["id"])
                    if not original:
                        continue
                    if shape["type"] == "freehand":
                        shape["points"] = [{"x": p["x"] + dx, "y": p["y"] + dy} for p in original.get("points", [])]
                        self.update_freehand_bounds(shape)
                    else:
                        shape["x"] = original["x"] + dx
                        shape["y"] = original["y"] + dy
                        if shape["type"] == "curve" and "control" in original:
                            shape["control"] = {"x": original["control"]["x"] + dx, "y": original["control"]["y"] + dy}
            self.render()

    def on_up(self, _event):
        changed = bool(self.current or (self.drag and self.drag.get("mode") != "marquee"))
        if self.current:
            shape = self.current["shape"]
            if shape["type"] == "freehand":
                self.update_freehand_bounds(shape)
            if abs(shape["w"]) < 8 and abs(shape["h"]) < 8 and shape["type"] not in ("text", "freehand"):
                shape["w"], shape["h"] = self.default_size(shape["type"])
            if shape["type"] == "curve":
                shape["control"] = {"x": shape["x"] + shape["w"] / 2, "y": min(shape["y"], shape["y"] + shape["h"]) - abs(shape["w"]) * 0.18}
            if shape["type"] not in ("line", "curve", "freehand"):
                self.normalize(shape)
        if self.drag and self.drag.get("mode") == "marquee" and self.selection_box:
            ids = [shape["id"] for shape in self.shapes if self.shape_inside_box(shape, self.selection_box)]
            self.set_selection(ids)
            self.selection_box = None
        self.current = None
        self.drag = None
        if changed:
            self.push_history("mouse")
        self.render()

    def default_size(self, shape_type):
        sizes = {
            "diamond": (130, 80),
            "terminator": (140, 62),
            "document": (150, 90),
            "resistor": (170, 60),
            "capacitor": (140, 70),
            "star": (100, 100),
            "cloud": (150, 90),
            "line": (150, 0),
            "curve": (160, 70),
        }
        return sizes.get(shape_type, (130, 76))

    def normalize(self, shape):
        if shape["w"] < 0:
            shape["x"] += shape["w"]
            shape["w"] = abs(shape["w"])
        if shape["h"] < 0:
            shape["y"] += shape["h"]
            shape["h"] = abs(shape["h"])

    def update_freehand_bounds(self, shape):
        points = shape.get("points", [])
        if not points:
            return
        xs = [point["x"] for point in points]
        ys = [point["y"] for point in points]
        shape["x"] = min(xs)
        shape["y"] = min(ys)
        shape["w"] = max(xs) - min(xs)
        shape["h"] = max(ys) - min(ys)

    def curve_points(self, shape, steps=24):
        x1, y1 = shape["x"], shape["y"]
        cx, cy = self.curve_control_point(shape)
        x2, y2 = shape["x"] + shape["w"], shape["y"] + shape["h"]
        points = []
        for i in range(steps + 1):
            t = i / steps
            x = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t ** 2 * x2
            y = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t ** 2 * y2
            points.append((x, y))
        return points

    def distance_to_segment(self, point, start, end):
        px, py = point
        x1, y1 = start
        x2, y2 = end
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = clamp(t, 0, 1)
        nearest = (x1 + t * dx, y1 + t * dy)
        return math.hypot(px - nearest[0], py - nearest[1])

    def distance_to_polyline(self, point, points):
        if len(points) < 2:
            return float("inf")
        return min(self.distance_to_segment(point, points[i], points[i + 1]) for i in range(len(points) - 1))

    def curve_control_hit(self, point):
        for shape in reversed(self.shapes):
            if shape["type"] != "curve":
                continue
            cx, cy = self.curve_control_point(shape)
            if math.hypot(point[0] - cx, point[1] - cy) <= 10:
                return shape
        return None

    def hit_test(self, point):
        px, py = point
        for shape in reversed(self.shapes):
            if shape["type"] == "line":
                start = (shape["x"], shape["y"])
                end = (shape["x"] + shape["w"], shape["y"] + shape["h"])
                if self.distance_to_segment(point, start, end) <= max(8, shape["lineWidth"] + 4):
                    return shape
                continue
            if shape["type"] == "curve":
                if self.distance_to_polyline(point, self.curve_points(shape)) <= max(8, shape["lineWidth"] + 4):
                    return shape
                continue
            if shape["type"] == "freehand":
                points = [(p["x"], p["y"]) for p in shape.get("points", [])]
                if self.distance_to_polyline(point, points) <= max(8, shape["lineWidth"] + 4):
                    return shape
                continue
            x, y, w, h = self.bounds(shape)
            if x - 6 <= px <= x + w + 6 and y - 6 <= py <= y + h + 6:
                return shape
        return None

    def apply_selected(self, fn, record=True):
        shapes = self.selected_shapes()
        if not shapes:
            messagebox.showinfo("提示", "请先选择对象")
            return
        for shape in shapes:
            fn(shape)
        if record:
            self.push_history("selected")
        self.render()

    def choose_color(self, var, field):
        color = colorchooser.askcolor(color=var.get())[1]
        if not color:
            return
        var.set(color)
        shapes = self.selected_shapes()
        if shapes:
            for shape in shapes:
                shape[field] = color
            self.push_history("style")
        self.render()

    def apply_style(self):
        shapes = self.selected_shapes()
        if shapes:
            for shape in shapes:
                if shape["type"] not in ("line", "curve", "freehand", "resistor", "capacitor", "text"):
                    shape["fill"] = self.fill.get()
                shape["stroke"] = self.stroke.get()
                shape["lineWidth"] = int(self.line_width.get())
                shape["fontSize"] = int(self.font_size.get())
                shape["text"] = self.text_value.get()
            self.push_history("style")
        self.render()

    def rotate_selected(self, degree):
        self.apply_selected(lambda s: s.__setitem__("rotation", (s.get("rotation", 0) + degree) % 360))

    def scale_selected(self, factor):
        def scale(s):
            cx, cy = shape_center(s)
            if s["type"] == "freehand":
                s["points"] = [
                    {"x": cx + (point["x"] - cx) * factor, "y": cy + (point["y"] - cy) * factor}
                    for point in s.get("points", [])
                ]
                self.update_freehand_bounds(s)
                return
            if s["type"] == "curve" and "control" in s:
                s["control"] = {
                    "x": cx + (s["control"]["x"] - cx) * factor,
                    "y": cy + (s["control"]["y"] - cy) * factor,
                }
            s["w"] *= factor
            s["h"] *= factor

        self.apply_selected(scale)

    def mirror_selected(self, axis):
        key = "flipX" if axis == "x" else "flipY"
        self.apply_selected(lambda s: s.__setitem__(key, not s.get(key, False)))

    def apply_3d_depth(self):
        depth = max(0, int(self.depth_3d.get()))
        solid = [shape for shape in self.selected_shapes() if shape["type"] in SOLID_3D_TYPES]
        if not solid:
            messagebox.showinfo("提示", "请先选择可立体化的封闭图元")
            return
        for shape in solid:
            shape["depth3D"] = depth
        self.push_history("3d")
        self.render()

    def clear_3d_depth(self):
        solid = [shape for shape in self.selected_shapes() if shape.get("depth3D", 0) > 0]
        if not solid:
            messagebox.showinfo("提示", "请先选择已有 3D 效果的图元")
            return
        for shape in solid:
            shape["depth3D"] = 0
        self.push_history("3d-clear")
        self.render()

    def open_3d_preview(self):
        source = self.selected_shapes() or self.shapes
        solids = [deepcopy(shape) for shape in source if shape["type"] in SOLID_3D_TYPES]
        if not solids:
            messagebox.showinfo("提示", "当前没有可预览的封闭图元")
            return
        fallback_depth = max(1, int(self.depth_3d.get()))
        for shape in solids:
            if shape.get("depth3D", 0) <= 0:
                shape["depth3D"] = fallback_depth

        win = tk.Toplevel(self.root)
        win.title("3D 立体预览")
        win.geometry("920x700")
        canvas = tk.Canvas(win, bg="#f8fafc", highlightthickness=1, highlightbackground="#cbd5e1")
        canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

        controls = ttk.Frame(win, padding=(10, 4, 10, 10))
        controls.pack(fill=tk.X)
        ttk.Label(controls, text="X 轴").pack(side=tk.LEFT)
        x_scale = ttk.Scale(controls, from_=15, to=80, variable=self.preview_angle_x, command=lambda _value: self.render_3d_preview(canvas, solids))
        x_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Label(controls, text="Y 轴").pack(side=tk.LEFT)
        y_scale = ttk.Scale(controls, from_=-80, to=80, variable=self.preview_angle_y, command=lambda _value: self.render_3d_preview(canvas, solids))
        y_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(controls, text="刷新", command=lambda: self.render_3d_preview(canvas, solids)).pack(side=tk.LEFT, padx=4)
        win.after(80, lambda: self.render_3d_preview(canvas, solids))

    def render_3d_preview(self, canvas, shapes):
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        faces = []
        for shape in shapes:
            faces.extend(self.shape_3d_faces(shape))
        if not faces:
            return

        ax = math.radians(float(self.preview_angle_x.get()))
        ay = math.radians(float(self.preview_angle_y.get()))
        projected_faces = []
        all_points = []
        for face in faces:
            projected = []
            depths = []
            for x, y, z in face["points"]:
                px, py, pz = self.rotate_3d_point(x - CANVAS_W / 2, y - CANVAS_H / 2, z, ax, ay)
                projected.append((px, py))
                depths.append(pz)
                all_points.append((px, py))
            projected_faces.append({**face, "projected": projected, "z": sum(depths) / len(depths)})

        min_x = min(x for x, _y in all_points)
        max_x = max(x for x, _y in all_points)
        min_y = min(y for _x, y in all_points)
        max_y = max(y for _x, y in all_points)
        span_x = max(1, max_x - min_x)
        span_y = max(1, max_y - min_y)
        scale = min((width - 70) / span_x, (height - 70) / span_y, 1.35)
        ox = width / 2 - (min_x + span_x / 2) * scale
        oy = height / 2 - (min_y + span_y / 2) * scale

        canvas.create_rectangle(0, height - 34, width, height, fill="#e2e8f0", outline="")
        canvas.create_text(14, height - 18, anchor=tk.W, text="拖动下方 X/Y 轴滑块旋转视角", fill="#475569", font=("Microsoft YaHei UI", 10))
        for face in sorted(projected_faces, key=lambda item: item["z"]):
            points = [(x * scale + ox, y * scale + oy) for x, y in face["projected"]]
            canvas.create_polygon(
                flatten(points),
                fill=face["fill"],
                outline=face["stroke"],
                width=face["lineWidth"],
            )

    def rotate_3d_point(self, x, y, z, ax, ay):
        cos_x, sin_x = math.cos(ax), math.sin(ax)
        y2 = y * cos_x - z * sin_x
        z2 = y * sin_x + z * cos_x
        cos_y, sin_y = math.cos(ay), math.sin(ay)
        x3 = x * cos_y + z2 * sin_y
        z3 = -x * sin_y + z2 * cos_y
        return x3, y2, z3

    def shape_3d_faces(self, shape):
        front2d = self.face_points(shape)
        depth = float(shape.get("depth3D", 0))
        fill = shape.get("fill", "#f8fafc")
        stroke = shape.get("stroke", "#111827")
        lw = max(1, int(shape.get("lineWidth", 2)))
        front = [(x, y, depth / 2) for x, y in front2d]
        back = [(x, y, -depth / 2) for x, y in front2d]
        faces = [{"points": back, "fill": shade_color(fill, 0.72), "stroke": stroke, "lineWidth": lw}]
        for i in range(len(front)):
            j = (i + 1) % len(front)
            shade = 0.82 if front2d[i][1] < front2d[j][1] else 0.64
            faces.append({"points": [front[i], front[j], back[j], back[i]], "fill": shade_color(fill, shade), "stroke": stroke, "lineWidth": lw})
        faces.append({"points": front, "fill": fill if fill != "transparent" else "#ffffff", "stroke": stroke, "lineWidth": lw})
        return faces

    def clip_to_canvas(self):
        def clip(s):
            if s["type"] in ("line", "curve"):
                end_x = clamp(s["x"] + s["w"], 0, CANVAS_W)
                end_y = clamp(s["y"] + s["h"], 0, CANVAS_H)
                s["x"] = clamp(s["x"], 0, CANVAS_W)
                s["y"] = clamp(s["y"], 0, CANVAS_H)
                s["w"] = end_x - s["x"]
                s["h"] = end_y - s["y"]
                if s["type"] == "curve" and "control" in s:
                    s["control"]["x"] = clamp(s["control"]["x"], 0, CANVAS_W)
                    s["control"]["y"] = clamp(s["control"]["y"], 0, CANVAS_H)
                return
            if s["type"] == "freehand":
                s["points"] = [
                    {"x": clamp(point["x"], 0, CANVAS_W), "y": clamp(point["y"], 0, CANVAS_H)}
                    for point in s.get("points", [])
                ]
                self.update_freehand_bounds(s)
                return
            right = clamp(s["x"] + s["w"], 0, CANVAS_W)
            bottom = clamp(s["y"] + s["h"], 0, CANVAS_H)
            s["x"] = clamp(s["x"], 0, CANVAS_W)
            s["y"] = clamp(s["y"], 0, CANVAS_H)
            s["w"] = max(8, right - s["x"])
            s["h"] = max(8, bottom - s["y"])

        self.apply_selected(clip)

    def copy_selected(self):
        shapes = self.selected_shapes()
        if shapes:
            self.clipboard = deepcopy(shapes)

    def paste_clipboard(self):
        if not self.clipboard:
            return
        source = self.clipboard if isinstance(self.clipboard, list) else [self.clipboard]
        pasted = []
        for item in source:
            shape = deepcopy(item)
            shape["id"] = uid()
            self.offset_shape(shape, 24, 24)
            self.shapes.append(shape)
            pasted.append(shape)
        self.set_selection([shape["id"] for shape in pasted])
        self.clipboard = deepcopy(pasted)
        self.push_history("paste")
        self.render()

    def offset_shape(self, shape, dx, dy):
        shape["x"] += dx
        shape["y"] += dy
        if shape["type"] == "curve" and "control" in shape:
            shape["control"]["x"] += dx
            shape["control"]["y"] += dy
        if shape["type"] == "freehand":
            shape["points"] = [{"x": point["x"] + dx, "y": point["y"] + dy} for point in shape.get("points", [])]
            self.update_freehand_bounds(shape)

    def delete_selected(self):
        ids = self.selected_ids or ({self.selected_id} if self.selected_id else set())
        if not ids:
            return
        self.shapes = [s for s in self.shapes if s["id"] not in ids]
        self.set_selection([])
        self.push_history("delete")
        self.render()

    def bring_to_front(self):
        selected = self.selected_shapes()
        if selected:
            ids = {shape["id"] for shape in selected}
            self.shapes = [shape for shape in self.shapes if shape["id"] not in ids] + selected
            self.push_history("front")
            self.render()

    def send_to_back(self):
        selected = self.selected_shapes()
        if selected:
            ids = {shape["id"] for shape in selected}
            self.shapes = selected + [shape for shape in self.shapes if shape["id"] not in ids]
            self.push_history("back")
            self.render()

    def select_all(self):
        self.set_selection([shape["id"] for shape in self.shapes])
        self.sync_panel()
        self.render()

    def center_selected(self):
        bounds = self.selection_bounds()
        if not bounds:
            messagebox.showinfo("提示", "请先选择对象")
            return
        x, y, w, h = bounds
        dx = CANVAS_W / 2 - (x + w / 2)
        dy = CANVAS_H / 2 - (y + h / 2)
        for shape in self.selected_shapes():
            self.offset_shape(shape, dx, dy)
        self.push_history("center")
        self.render()

    def align_selected(self, mode):
        shape = self.selected_shape()
        if not shape:
            messagebox.showinfo("提示", "请先选择对象")
            return
        candidates = [s for s in self.shapes if s["id"] != shape["id"] and s["type"] not in ("line", "curve", "freehand")]
        if not candidates:
            return
        ref = min(candidates, key=lambda s: abs(self.bounds(s)[0] - self.bounds(shape)[0]) + abs(self.bounds(s)[1] - self.bounds(shape)[1]))
        rx, ry, _, _ = self.bounds(ref)
        x, y, _, _ = self.bounds(shape)
        if mode == "left":
            self.offset_shape(shape, rx - x, 0)
        if mode == "top":
            self.offset_shape(shape, 0, ry - y)
        self.push_history("align")
        self.render()

    def auto_flow_layout(self):
        nodes = [s for s in self.shapes if s["type"] not in ("line", "curve", "freehand", "text")]
        if not nodes:
            return
        cols = max(1, math.ceil(math.sqrt(len(nodes))))
        cell_w = CANVAS_W / (cols + 1)
        cell_h = 120
        for index, shape in enumerate(nodes):
            row = index // cols
            col = index % cols
            shape["x"] = cell_w * (col + 1) - shape["w"] / 2
            shape["y"] = 80 + row * cell_h
        self.push_history("layout")
        self.render()

    def compile_dsl(self, source):
        shapes = []
        symbols = {}
        style = {"fill": self.fill.get(), "stroke": self.stroke.get(), "lineWidth": int(self.line_width.get()), "fontSize": int(self.font_size.get())}
        for line_no, raw in enumerate(source.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            tokens = re.findall(r'"[^"]*"|\S+', line)
            cmd = tokens[0].lower()
            args = [token[1:-1] if token.startswith('"') and token.endswith('"') else token for token in tokens[1:]]
            try:
                if cmd == "style":
                    for item in args:
                        key, value = item.split("=", 1)
                        if key in ("fill", "stroke"):
                            style[key] = value
                        elif key in ("lineWidth", "fontSize"):
                            style[key] = int(value)
                    continue
                if cmd in ("rect", "roundrect", "ellipse", "diamond", "terminator", "document", "star", "cloud", "resistor", "capacitor", "text"):
                    name, x, y, w, h = args[:5]
                    text = args[5] if len(args) > 5 else name
                    shape = self.shape_base(cmd, float(x), float(y), float(w), float(h))
                    shape.update(style)
                    if cmd in ("resistor", "capacitor", "text"):
                        shape["fill"] = "transparent"
                    shape["text"] = text if cmd != "text" else (args[5] if len(args) > 5 else name)
                    shapes.append(shape)
                    symbols[name] = shape
                    continue
                if cmd in ("line", "curve"):
                    a, b = args[:2]
                    start = symbols[a]
                    end = symbols[b]
                    x1, y1 = shape_center(start)
                    x2, y2 = shape_center(end)
                    shape = self.shape_base(cmd, x1, y1, x2 - x1, y2 - y1)
                    shape.update(style)
                    shape["fill"] = "transparent"
                    if cmd == "curve":
                        shape["control"] = {"x": (x1 + x2) / 2, "y": min(y1, y2) - 80}
                    shapes.append(shape)
                    continue
                raise ValueError(f"未知指令 {cmd}")
            except Exception as exc:
                raise ValueError(f"第 {line_no} 行编译失败：{raw}\n{exc}") from exc
        return shapes

    def open_dsl_compiler(self):
        win = tk.Toplevel(self.root)
        win.title("DSL 图形编译器")
        win.geometry("720x520")
        ttk.Label(win, text="输入简单脚本，点击编译即可生成矢量图。").pack(anchor=tk.W, padx=10, pady=(10, 4))
        text = tk.Text(win, height=22, wrap=tk.NONE, font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        text.insert("1.0", self.default_dsl())

        row = ttk.Frame(win, padding=10)
        row.pack(fill=tk.X)

        def compile_now(replace):
            try:
                shapes = self.compile_dsl(text.get("1.0", tk.END))
                if replace:
                    self.shapes = shapes
                else:
                    self.shapes.extend(shapes)
                self.set_selection([])
                self.push_history("dsl")
                self.render()
                messagebox.showinfo("编译完成", f"已生成 {len(shapes)} 个图元")
            except Exception as exc:
                messagebox.showerror("编译失败", str(exc))

        ttk.Button(row, text="替换画布", command=lambda: compile_now(True)).pack(side=tk.RIGHT, padx=3)
        ttk.Button(row, text="追加到画布", command=lambda: compile_now(False)).pack(side=tk.RIGHT, padx=3)

    def default_dsl(self):
        return """# 支持 style、图元、连线。格式：
# rect 名称 x y w h "显示文字"
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
style fill=#fff7ed stroke=#c2410c lineWidth=3 fontSize=18
star key 760 130 105 105 "重点"
cloud api 720 310 190 105 "云端服务"
curve key api
"""

    def analysis_metrics(self):
        count = len(self.shapes)
        if not count:
            return {"count": 0, "area": 0, "coverage": 0, "avg_line": 0, "types": {}}
        areas = []
        line_lengths = []
        types = {}
        for shape in self.shapes:
            types[shape["type"]] = types.get(shape["type"], 0) + 1
            x, y, w, h = self.bounds(shape)
            areas.append(max(0, w) * max(0, h))
            if shape["type"] in ("line", "curve"):
                line_lengths.append(math.hypot(shape["w"], shape["h"]))
            elif shape["type"] == "freehand":
                pts = [(p["x"], p["y"]) for p in shape.get("points", [])]
                line_lengths.extend(self.polyline_lengths(pts))
        if np is not None:
            area_sum = float(np.sum(np.array(areas, dtype=float)))
            avg_line = float(np.mean(np.array(line_lengths, dtype=float))) if line_lengths else 0.0
        else:
            area_sum = sum(areas)
            avg_line = sum(line_lengths) / len(line_lengths) if line_lengths else 0.0
        return {
            "count": count,
            "area": area_sum,
            "coverage": area_sum / (CANVAS_W * CANVAS_H) * 100,
            "avg_line": avg_line,
            "types": types,
        }

    def polyline_lengths(self, points):
        return [math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]) for i in range(len(points) - 1)]

    def show_analysis(self):
        metrics = self.analysis_metrics()
        type_text = ", ".join(f"{key}:{value}" for key, value in sorted(metrics["types"].items())) or "无"
        lib_text = "NumPy 加速统计" if np is not None else "纯 Python 统计"
        messagebox.showinfo(
            "图形分析",
            f"图元数量：{metrics['count']}\n"
            f"估算占用面积：{metrics['area']:.0f} px²\n"
            f"画布覆盖率：{metrics['coverage']:.2f}%\n"
            f"平均连线长度：{metrics['avg_line']:.1f} px\n"
            f"类型分布：{type_text}\n"
            f"计算方式：{lib_text}",
        )

    def save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON 文件", "*.json")])
        if not path:
            return
        data = {"app": "VectorGraphicsEditorPython", "version": APP_VERSION, "canvas": {"width": CANVAS_W, "height": CANVAS_H}, "shapes": self.shapes}
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON 文件", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            self.shapes = data["shapes"]
            self.set_selection([])
            self.push_history("load")
            self.render()
        except Exception as exc:
            messagebox.showerror("加载失败", f"文件格式不正确：{exc}")

    def save_svg(self):
        path = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG 矢量图", "*.svg")])
        if not path:
            return
        Path(path).write_text(self.to_svg(), encoding="utf-8")

    def to_svg(self):
        body = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">',
            "<defs>",
            '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">',
            '<path d="M0,0 L0,6 L9,3 z" fill="context-stroke"/>',
            "</marker>",
            "</defs>",
            '<rect width="100%" height="100%" fill="white"/>',
        ]
        for shape in self.shapes:
            body.append(self.shape_to_svg(shape))
        body.append("</svg>")
        return "\n".join(body)

    def shape_to_svg(self, s):
        stroke = escape(str(s.get("stroke", "#111827")))
        fill = "none" if s.get("fill") == "transparent" else escape(str(s.get("fill", "none")))
        lw = s.get("lineWidth", 2)
        transform = self.svg_transform(s)
        text = ""
        if s.get("text") and s["type"] != "text":
            cx, cy = shape_center(s)
            text = f'<text x="{cx:.2f}" y="{cy:.2f}" text-anchor="middle" dominant-baseline="middle" fill="{stroke}" font-size="{s.get("fontSize", 16)}" font-family="Microsoft YaHei, Arial">{escape(str(s["text"]))}</text>'
        prefix = self.extrusion_to_svg(s) if self.is_3d_shape(s) else ""
        if s["type"] in ("line", "curve"):
            if s["type"] == "curve":
                cx, cy = self.curve_control_point(s)
                d = f'M {s["x"]:.2f} {s["y"]:.2f} Q {cx:.2f} {cy:.2f} {s["x"] + s["w"]:.2f} {s["y"] + s["h"]:.2f}'
            else:
                d = f'M {s["x"]:.2f} {s["y"]:.2f} L {s["x"] + s["w"]:.2f} {s["y"] + s["h"]:.2f}'
            return f'{prefix}<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{lw}" marker-end="url(#arrow)"/>'
        if s["type"] == "freehand":
            pts = " ".join(f'{p["x"]:.2f},{p["y"]:.2f}' for p in s.get("points", []))
            return f'{prefix}<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="{lw}" stroke-linecap="round" stroke-linejoin="round"/>'
        if s["type"] == "resistor":
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in self.transformed(s, self.resistor_points(s)))
            return f'{prefix}<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="{lw}" stroke-linecap="round" stroke-linejoin="round"/>'
        if s["type"] == "capacitor":
            x, y, w, h = s["x"], s["y"], s["w"], s["h"]
            cy = y + h / 2
            gap = w * 0.08
            plate = h * 0.35
            parts = []
            for line in [
                [(x, cy), (x + w / 2 - gap, cy)],
                [(x + w / 2 + gap, cy), (x + w, cy)],
                [(x + w / 2 - gap, cy - plate), (x + w / 2 - gap, cy + plate)],
                [(x + w / 2 + gap, cy - plate), (x + w / 2 + gap, cy + plate)],
            ]:
                (x1, y1), (x2, y2) = self.transformed(s, line)
                parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{lw}" stroke-linecap="round"/>')
            return prefix + "\n".join(parts)
        if s["type"] == "text":
            return f'{prefix}<text x="{s["x"]:.2f}" y="{s["y"]:.2f}" fill="{stroke}" font-size="{s.get("fontSize", 16)}" font-family="Microsoft YaHei, Arial" transform="{transform}">{escape(str(s.get("text", "文本")))}</text>'
        points = self.points_for_svg(s)
        point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        return f'{prefix}<g transform="{transform}"><polygon points="{point_text}" fill="{fill}" stroke="{stroke}" stroke-width="{lw}"/>{text}</g>'

    def extrusion_to_svg(self, s):
        front = self.face_points(s)
        if len(front) < 3:
            return ""
        dx, dy = self.extrusion_offset(s)
        back = [(x + dx, y + dy) for x, y in front]
        fill = s.get("fill", "#f8fafc")
        stroke = escape(str(s.get("stroke", "#111827")))
        lw = max(1, int(s.get("lineWidth", 2) * 0.65))
        parts = []
        back_points = " ".join(f"{x:.2f},{y:.2f}" for x, y in back)
        parts.append(f'<polygon points="{back_points}" fill="{escape(shade_color(fill, 0.9))}" stroke="{stroke}" stroke-width="{lw}"/>')
        for i in range(len(front)):
            j = (i + 1) % len(front)
            shade = 1.08 if front[i][1] + front[j][1] > back[i][1] + back[j][1] else 0.78
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in [front[i], front[j], back[j], back[i]])
            parts.append(f'<polygon points="{pts}" fill="{escape(shade_color(fill, shade))}" stroke="{stroke}" stroke-width="{lw}"/>')
        return "\n".join(parts) + "\n"

    def svg_transform(self, s):
        cx, cy = shape_center(s)
        parts = []
        if s.get("rotation"):
            parts.append(f'rotate({s.get("rotation", 0):.2f} {cx:.2f} {cy:.2f})')
        if s.get("flipX") or s.get("flipY"):
            sx = -1 if s.get("flipX") else 1
            sy = -1 if s.get("flipY") else 1
            parts.append(f'translate({cx:.2f} {cy:.2f}) scale({sx} {sy}) translate({-cx:.2f} {-cy:.2f})')
        return " ".join(parts)

    def points_for_svg(self, s):
        table = {
            "rect": self.rect_points,
            "roundrect": self.roundrect_points,
            "ellipse": self.ellipse_points,
            "diamond": self.diamond_points,
            "terminator": self.terminator_points,
            "document": self.document_points,
            "star": self.star_points,
            "cloud": self.cloud_points,
            "resistor": self.resistor_points,
        }
        if s["type"] == "capacitor":
            return []
        return table.get(s["type"], self.rect_points)(s)

    def save_image(self):
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG 图片", "*.png")])
        if not path:
            return
        if Image is None:
            messagebox.showerror("导出失败", "未安装 Pillow，无法进行高清 PNG 渲染。请运行：pip install pillow")
            return
        try:
            scale = max(1, int(self.export_scale.get()))
            image = self.render_to_image(scale)
            image.save(path)
        except Exception as exc:
            messagebox.showerror("保存失败", f"图片保存失败：{exc}")

    def render_to_image(self, scale=2):
        image = Image.new("RGB", (CANVAS_W * scale, CANVAS_H * scale), "white")
        draw = ImageDraw.Draw(image)
        if self.show_grid.get():
            for x in range(0, CANVAS_W + 1, GRID):
                draw.line([(x * scale, 0), (x * scale, CANVAS_H * scale)], fill="#eef2f7")
            for y in range(0, CANVAS_H + 1, GRID):
                draw.line([(0, y * scale), (CANVAS_W * scale, y * scale)], fill="#eef2f7")
        for shape in self.shapes:
            self.draw_shape_pillow(draw, shape, scale)
        return image

    def draw_shape_pillow(self, draw, s, scale):
        stroke = color_or_none(s.get("stroke")) or "#111827"
        fill = color_or_none(s.get("fill"))
        width = max(1, int(s.get("lineWidth", 2) * scale))
        if self.is_3d_shape(s):
            self.draw_extrusion_pillow(draw, s, scale)
        if s["type"] in ("line", "curve"):
            if s["type"] == "curve":
                pts = self.curve_points(s, 32)
            else:
                pts = [(s["x"], s["y"]), (s["x"] + s["w"], s["y"] + s["h"])]
            draw.line([(x * scale, y * scale) for x, y in pts], fill=stroke, width=width)
            self.draw_arrow_pillow(draw, pts[-2], pts[-1], stroke, scale)
            return
        if s["type"] == "freehand":
            pts = [(p["x"], p["y"]) for p in s.get("points", [])]
            if len(pts) > 1:
                draw.line([(x * scale, y * scale) for x, y in pts], fill=stroke, width=width, joint="curve")
            return
        if s["type"] == "capacitor":
            x, y, w, h = s["x"], s["y"], s["w"], s["h"]
            cy = y + h / 2
            gap = w * 0.08
            plate = h * 0.35
            for pts in [
                [(x, cy), (x + w / 2 - gap, cy)],
                [(x + w / 2 + gap, cy), (x + w, cy)],
                [(x + w / 2 - gap, cy - plate), (x + w / 2 - gap, cy + plate)],
                [(x + w / 2 + gap, cy - plate), (x + w / 2 + gap, cy + plate)],
            ]:
                pts = self.transformed(s, pts)
                draw.line([(px * scale, py * scale) for px, py in pts], fill=stroke, width=width)
            return
        pts = self.transformed(s, self.points_for_svg(s))
        draw.polygon([(x * scale, y * scale) for x, y in pts], fill=fill, outline=stroke)
        if width > 1 and len(pts) > 1:
            closed = pts + [pts[0]]
            draw.line([(x * scale, y * scale) for x, y in closed], fill=stroke, width=width)
        self.draw_text_pillow(draw, s, scale)

    def draw_extrusion_pillow(self, draw, s, scale):
        front = self.face_points(s)
        if len(front) < 3:
            return
        dx, dy = self.extrusion_offset(s)
        back = [(x + dx, y + dy) for x, y in front]
        fill = s.get("fill", "#f8fafc")
        stroke = color_or_none(s.get("stroke")) or "#111827"
        width = max(1, int(s.get("lineWidth", 2) * scale * 0.65))

        draw.polygon([(x * scale, y * scale) for x, y in back], fill=shade_color(fill, 0.9), outline=stroke)
        for i in range(len(front)):
            j = (i + 1) % len(front)
            shade = 1.08 if front[i][1] + front[j][1] > back[i][1] + back[j][1] else 0.78
            face = [front[i], front[j], back[j], back[i]]
            scaled = [(x * scale, y * scale) for x, y in face]
            draw.polygon(scaled, fill=shade_color(fill, shade), outline=stroke)
            if width > 1:
                draw.line(scaled + [scaled[0]], fill=stroke, width=width)

    def draw_arrow_pillow(self, draw, start, end, color, scale):
        x1, y1 = start
        x2, y2 = end
        angle = math.atan2(y2 - y1, x2 - x1)
        size = 10 * scale
        p1 = (x2 * scale, y2 * scale)
        p2 = (x2 * scale - size * math.cos(angle - math.pi / 6), y2 * scale - size * math.sin(angle - math.pi / 6))
        p3 = (x2 * scale - size * math.cos(angle + math.pi / 6), y2 * scale - size * math.sin(angle + math.pi / 6))
        draw.polygon([p1, p2, p3], fill=color)

    def draw_text_pillow(self, draw, s, scale):
        text = s.get("text")
        if not text:
            return
        font = font_for(int(s.get("fontSize", 16)) * scale)
        stroke = color_or_none(s.get("stroke")) or "#111827"
        if s["type"] == "text":
            draw.text((s["x"] * scale, s["y"] * scale), text, fill=stroke, font=font)
            return
        cx, cy = shape_center(s)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx * scale - tw / 2, cy * scale - th / 2), text, fill=stroke, font=font)

    def new_file(self):
        if self.shapes and not messagebox.askyesno("确认", "清空当前画布？"):
            return
        self.shapes = []
        self.set_selection([])
        self.push_history("new")
        self.render()

    def load_sample(self, record=True):
        self.shapes = [
            {**self.shape_base("terminator", 90, 75, 135, 58), "text": "开始", "fill": "#e8f7f3", "stroke": "#0f766e"},
            {**self.shape_base("rect", 90, 175, 135, 72), "text": "读取数据", "fill": "#f8fafc", "stroke": "#334155"},
            {**self.shape_base("diamond", 82, 305, 150, 88), "text": "是否有效", "fill": "#fff7ed", "stroke": "#c2410c"},
            {**self.shape_base("document", 390, 185, 165, 92), "text": "生成报告", "fill": "#eff6ff", "stroke": "#1d4ed8", "depth3D": 24},
            {**self.shape_base("terminator", 405, 340, 135, 58), "text": "结束", "fill": "#f0fdf4", "stroke": "#15803d"},
            {**self.shape_base("line", 158, 133, 0, 42), "stroke": "#475569"},
            {**self.shape_base("line", 158, 247, 0, 58), "stroke": "#475569"},
            {**self.shape_base("curve", 232, 350, 158, -112), "stroke": "#475569", "control": {"x": 315, "y": 205}},
            {**self.shape_base("line", 472, 277, 0, 63), "stroke": "#475569"},
            {**self.shape_base("star", 712, 108, 104, 104), "text": "重点", "fill": "#fef3c7", "stroke": "#b45309", "depth3D": 34},
            {**self.shape_base("cloud", 680, 260, 190, 105), "text": "云端服务", "fill": "#ecfeff", "stroke": "#0891b2", "depth3D": 28},
            {**self.shape_base("resistor", 710, 430, 170, 60), "stroke": "#7c2d12"},
            {**self.shape_base("capacitor", 720, 545, 140, 72), "stroke": "#7c2d12"},
            {**self.shape_base("text", 675, 70, 260, 32), "text": "新增图元与编译示例", "stroke": "#172033"},
            {
                **self.shape_base("freehand", 910, 430, 80, 70),
                "stroke": "#0f766e",
                "lineWidth": 3,
                "points": [
                    {"x": 910, "y": 470},
                    {"x": 932, "y": 436},
                    {"x": 960, "y": 455},
                    {"x": 982, "y": 420},
                    {"x": 1005, "y": 468},
                ],
            },
        ]
        self.set_selection([])
        if record:
            self.push_history("sample")
        self.render()

    def sync_panel(self):
        shape = self.selected_shape()
        if not shape:
            return
        if shape.get("fill") != "transparent":
            self.fill.set(shape.get("fill", self.fill.get()))
        self.stroke.set(shape.get("stroke", self.stroke.get()))
        self.line_width.set(int(shape.get("lineWidth", self.line_width.get())))
        self.font_size.set(int(shape.get("fontSize", self.font_size.get())))
        self.depth_3d.set(int(shape.get("depth3D", self.depth_3d.get())))
        self.text_value.set(shape.get("text", ""))

    def update_layers(self):
        if not hasattr(self, "layers"):
            return
        self.layers.delete(0, tk.END)
        for index, shape in enumerate(reversed(self.shapes), 1):
            name = shape.get("text") or shape["type"]
            mark = "● " if shape["id"] in self.selected_ids else "  "
            self.layers.insert(tk.END, f"{mark}{index}. {shape['type']}  {name}")

    def on_layer_select(self, _event):
        if not self.layers.curselection():
            return
        visual_index = self.layers.curselection()[0]
        actual_index = len(self.shapes) - 1 - visual_index
        if 0 <= actual_index < len(self.shapes):
            self.set_selection([self.shapes[actual_index]["id"]])
            self.sync_panel()
            self.render()

    def update_status(self):
        metrics = self.analysis_metrics()
        shape = self.selected_shape()
        if len(self.selected_ids) > 1:
            bounds = self.selection_bounds()
            if bounds:
                x, y, w, h = bounds
                self.status.config(
                    text=f"已选 {len(self.selected_ids)} 个图元  "
                    f"x:{int(x)} y:{int(y)} w:{int(w)} h:{int(h)}"
                )
                return
        if not shape:
            self.status.config(text=f"未选择对象｜图元 {metrics['count']}｜覆盖率 {metrics['coverage']:.1f}%")
            return
        self.status.config(
            text=f"{shape['type']}  x:{int(shape['x'])} y:{int(shape['y'])} "
            f"w:{int(shape['w'])} h:{int(shape['h'])} 旋转:{shape.get('rotation', 0)}° "
            f"3D:{int(shape.get('depth3D', 0))}"
        )


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1380x780")
    app = VectorEditor(root)
    root.mainloop()
