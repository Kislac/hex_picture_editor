import math
import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk
from PIL import ImageDraw


ASPECT_W = 15
ASPECT_H = 10
ASPECT = ASPECT_W / ASPECT_H  # 1.5


@dataclass
class CropRect:
	left: float
	top: float
	right: float
	bottom: float

	@property
	def width(self) -> float:
		return self.right - self.left

	@property
	def height(self) -> float:
		return self.bottom - self.top

	@property
	def center(self) -> tuple[float, float]:
		return (self.left + self.right) / 2.0, (self.top + self.bottom) / 2.0

	def clamp_within(self, w: int, h: int) -> None:
		dx = 0.0
		dy = 0.0
		if self.left < 0:
			dx = -self.left
		elif self.right > w:
			dx = w - self.right
		if self.top < 0:
			dy = -self.top
		elif self.bottom > h:
			dy = h - self.bottom
		self.left += dx
		self.right += dx
		self.top += dy
		self.bottom += dy

	def move_by(self, dx: float, dy: float, w: int, h: int) -> None:
		self.left += dx
		self.right += dx
		self.top += dy
		self.bottom += dy
		self.clamp_within(w, h)

	def resize_about_center(self, new_width: float, new_height: float, w: int, h: int) -> None:
		cx, cy = self.center
		half_w = new_width / 2.0
		half_h = new_height / 2.0
		self.left = cx - half_w
		self.right = cx + half_w
		self.top = cy - half_h
		self.bottom = cy + half_h
		self.clamp_within(w, h)


class HexCropApp:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("15:10 Crop + Hex Guide")

		self.image_paths: list[Path] = []
		self.image_index = 0
		self.ignored_paths: set[Path] = set()
		self.saved_crops: dict[Path, CropRect] = {}

		self.original_image: Image.Image | None = None
		self.display_image: Image.Image | None = None
		self.photo: ImageTk.PhotoImage | None = None
		self.scale = 1.0
		self.img_offset_x = 0
		self.img_offset_y = 0
		self.crop_rect: CropRect | None = None

		self.dragging = False
		self.drag_last_x = 0
		self.drag_last_y = 0

		self.output_dir: Path | None = None
		# Default: rotated 30° (flat-bottom / flat-top style)
		self.hex_rotate_var = tk.BooleanVar(value=True)
		self.export_hex_var = tk.BooleanVar(value=False)
		self._updating_slider = False

		self._build_ui()
		self._bind_events()

	def _build_ui(self) -> None:
		self.root.rowconfigure(1, weight=1)
		self.root.columnconfigure(0, weight=1)

		toolbar = ttk.Frame(self.root, padding=8)
		toolbar.grid(row=0, column=0, sticky="ew")
		# Make the crop-size slider expand.
		toolbar.columnconfigure(6, weight=1)

		ttk.Button(toolbar, text="Open images…", command=self.open_images).grid(row=0, column=0, padx=(0, 8))
		ttk.Button(toolbar, text="Previous", command=self.prev_image).grid(row=0, column=1, padx=(0, 4))
		ttk.Button(toolbar, text="Next", command=self.next_image).grid(row=0, column=2, padx=(0, 8))
		ttk.Button(toolbar, text="Export crop…", command=self.export_crop).grid(row=0, column=3, padx=(0, 12))
		ttk.Button(toolbar, text="Ignore / Skip", command=self.ignore_current).grid(row=0, column=4, padx=(0, 12))

		ttk.Checkbutton(toolbar, text="Hex rotate 30°", variable=self.hex_rotate_var, command=self._on_hex_rotate_toggle).grid(
			row=0, column=5, padx=(0, 12)
		)
		ttk.Checkbutton(toolbar, text="Draw hex on export", variable=self.export_hex_var).grid(row=0, column=6, padx=(0, 12))

		ttk.Label(toolbar, text="Crop size:").grid(row=0, column=7, sticky="w")
		self.size_var = tk.IntVar(value=85)
		self.size_scale = ttk.Scale(toolbar, from_=30, to=200, orient="horizontal", command=self._on_size_change)
		self.size_scale.set(self.size_var.get())
		self.size_scale.grid(row=0, column=8, sticky="ew", padx=(6, 12))

		self.info_var = tk.StringVar(value="No image loaded")
		ttk.Label(toolbar, textvariable=self.info_var).grid(row=0, column=9, sticky="w")

		self.canvas = tk.Canvas(self.root, bg="#1e1e1e", highlightthickness=0)
		self.canvas.grid(row=1, column=0, sticky="nsew")

		status = ttk.Frame(self.root, padding=(8, 4))
		status.grid(row=2, column=0, sticky="ew")
		status.columnconfigure(0, weight=1)
		self.status_var = tk.StringVar(
			value="Drag the 15:10 frame. Use the slider to change its size (can exceed image). Toggle hex rotation with the checkbox."
		)
		ttk.Label(status, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

	def _bind_events(self) -> None:
		self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
		self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
		self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
		self.root.bind("<Left>", lambda e: self._nudge(-10, 0))
		self.root.bind("<Right>", lambda e: self._nudge(10, 0))
		self.root.bind("<Up>", lambda e: self._nudge(0, -10))
		self.root.bind("<Down>", lambda e: self._nudge(0, 10))
		self.root.bind("<Configure>", lambda e: self._redraw())

	def _on_hex_rotate_toggle(self) -> None:
		if self.original_image and self.crop_rect:
			self._clamp_crop_to_keep_hex_inside()
			self._sync_slider_to_crop()
		self._redraw()
		self._update_info()
	def _max_crop_wh_for_image(self, img_w: int, img_h: int) -> tuple[float, float]:
		# Max 15:10 crop that fits inside image (used as baseline for the size slider).
		if (img_w / img_h) >= ASPECT:
			max_h = float(img_h)
			max_w = max_h * ASPECT
		else:
			max_w = float(img_w)
			max_h = max_w / ASPECT
		return max_w, max_h

	def _sync_slider_to_crop(self) -> None:
		if not (self.original_image and self.crop_rect):
			return
		img_w, img_h = self.original_image.size
		max_w, _max_h = self._max_crop_wh_for_image(img_w, img_h)
		if max_w <= 0:
			return
		pct = (self.crop_rect.width / max_w) * 100.0
		pct = max(float(self.size_scale.cget("from")), min(float(self.size_scale.cget("to")), pct))
		self._updating_slider = True
		try:
			self.size_scale.set(pct)
		finally:
			self._updating_slider = False

	def _save_current_state(self) -> None:
		if not (self.image_paths and self.crop_rect):
			return
		path = self.image_paths[self.image_index]
		self.saved_crops[path] = CropRect(
			left=self.crop_rect.left,
			top=self.crop_rect.top,
			right=self.crop_rect.right,
			bottom=self.crop_rect.bottom,
		)


	def _hex_rotation_degrees(self) -> float:
		return 30.0 if self.hex_rotate_var.get() else 0.0

	def _hex_unit_vectors(self) -> list[tuple[float, float]]:
		rot = self._hex_rotation_degrees()
		vecs: list[tuple[float, float]] = []
		for k in range(6):
			angle = math.radians(-90 + rot + k * 60)
			vecs.append((math.cos(angle), math.sin(angle)))
		return vecs

	def _hex_r_from_rect(self, rect_w: float, rect_h: float) -> float:
		"""Radius (center -> vertex) of the largest regular hex that fits in a W×H box.
		For rot=0 (pointy-top): width=sqrt(3)r, height=2r.
		For rot=30 (flat-top): width=2r, height=sqrt(3)r.
		"""
		rot = self._hex_rotation_degrees()
		if abs(rot - 30.0) < 1e-6:
			return min(rect_w / 2.0, rect_h / math.sqrt(3))
		return min(rect_h / 2.0, rect_w / math.sqrt(3))

	def _hex_r_max_at_center(self, cx: float, cy: float, img_w: int, img_h: int) -> float:
		"""Max r so that all hex vertices stay inside image bounds at center (cx,cy)."""
		r_max = float("inf")
		for ux, uy in self._hex_unit_vectors():
			# X constraints
			if ux > 1e-12:
				r_max = min(r_max, (img_w - cx) / ux)
			elif ux < -1e-12:
				r_max = min(r_max, (0 - cx) / ux)  # ux is negative
			# Y constraints
			if uy > 1e-12:
				r_max = min(r_max, (img_h - cy) / uy)
			elif uy < -1e-12:
				r_max = min(r_max, (0 - cy) / uy)  # uy is negative
		return max(0.0, r_max)

	def _hex_r_global_max(self, img_w: int, img_h: int) -> float:
		rot = self._hex_rotation_degrees()
		if abs(rot - 30.0) < 1e-6:
			return min(img_w / 2.0, img_h / math.sqrt(3))
		return min(img_h / 2.0, img_w / math.sqrt(3))

	def _set_crop_from_center(self, cx: float, cy: float, rect_w: float, rect_h: float) -> None:
		if not self.crop_rect:
			self.crop_rect = CropRect(0, 0, 0, 0)
		self.crop_rect.left = cx - rect_w / 2.0
		self.crop_rect.right = cx + rect_w / 2.0
		self.crop_rect.top = cy - rect_h / 2.0
		self.crop_rect.bottom = cy + rect_h / 2.0

	def _clamp_center_for_hex(self, cx: float, cy: float, r: float, img_w: int, img_h: int) -> tuple[float, float]:
		min_cx = 0.0
		max_cx = float(img_w)
		min_cy = 0.0
		max_cy = float(img_h)
		for ux, uy in self._hex_unit_vectors():
			if ux > 1e-12:
				min_cx = max(min_cx, r * ux)
				max_cx = min(max_cx, img_w - r * ux)
			elif ux < -1e-12:
				min_cx = max(min_cx, -r * ux)
				max_cx = min(max_cx, img_w + r * ux)
			if uy > 1e-12:
				min_cy = max(min_cy, r * uy)
				max_cy = min(max_cy, img_h - r * uy)
			elif uy < -1e-12:
				min_cy = max(min_cy, -r * uy)
				max_cy = min(max_cy, img_h + r * uy)

		if min_cx > max_cx:
			# Image too small for this r; fall back to center.
			min_cx = max_cx = img_w / 2.0
		if min_cy > max_cy:
			min_cy = max_cy = img_h / 2.0

		cx = min(max(cx, min_cx), max_cx)
		cy = min(max(cy, min_cy), max_cy)
		return cx, cy

	def _clamp_crop_to_keep_hex_inside(self) -> None:
		if not (self.original_image and self.crop_rect):
			return
		img_w, img_h = self.original_image.size
		cx, cy = self.crop_rect.center
		rect_w = self.crop_rect.width
		rect_h = self.crop_rect.height
		r = self._hex_r_from_rect(rect_w, rect_h)
		r_global_max = self._hex_r_global_max(img_w, img_h)
		if r > r_global_max and r > 0:
			factor = r_global_max / r
			rect_w *= factor
			rect_h *= factor
			r = self._hex_r_from_rect(rect_w, rect_h)
		cx, cy = self._clamp_center_for_hex(cx, cy, r, img_w, img_h)
		self._set_crop_from_center(cx, cy, rect_w, rect_h)

	def open_images(self) -> None:
		paths = filedialog.askopenfilenames(
			title="Select images",
			initialdir=os.getcwd(),
			filetypes=[
				("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff;*.webp"),
				("All files", "*.*"),
			],
		)
		if not paths:
			return

		self.image_paths = [Path(p) for p in paths]
		self.image_index = 0
		self.ignored_paths = set()
		self.saved_crops = {}
		self._load_current_image()

	def _find_next_index(self, start_index: int, step: int) -> int | None:
		if not self.image_paths:
			return None
		n = len(self.image_paths)
		idx = start_index
		for _ in range(n):
			idx = (idx + step) % n
			if self.image_paths[idx] not in self.ignored_paths:
				return idx
		return None

	def ignore_current(self) -> None:
		if not self.image_paths:
			return
		self._save_current_state()
		current = self.image_paths[self.image_index]
		self.ignored_paths.add(current)
		self.status_var.set(f"Ignored: {current.name}")
		next_idx = self._find_next_index(self.image_index, 1)
		if next_idx is None:
			messagebox.showinfo("Ignore", "All images are ignored.")
			return
		self.image_index = next_idx
		self._load_current_image()

	def _load_current_image(self) -> None:
		if not self.image_paths:
			return
		# If current is ignored, jump to the next non-ignored.
		if self.image_paths[self.image_index] in self.ignored_paths:
			next_idx = self._find_next_index(self.image_index, 1)
			if next_idx is None:
				self.original_image = None
				self._redraw()
				self._update_info()
				return
			self.image_index = next_idx
		path = self.image_paths[self.image_index]
		try:
			img = Image.open(path)
			img = ImageOps.exif_transpose(img)
		except Exception as ex:
			messagebox.showerror("Open image", f"Failed to open image:\n{path}\n\n{ex}")
			return

		self.original_image = img
		if path in self.saved_crops:
			saved = self.saved_crops[path]
			self.crop_rect = CropRect(saved.left, saved.top, saved.right, saved.bottom)
		else:
			self._reset_crop_to_max_center()
		self._clamp_crop_to_keep_hex_inside()
		self._sync_slider_to_crop()
		self._redraw()
		self._update_info()

	def prev_image(self) -> None:
		if not self.image_paths:
			return
		self._save_current_state()
		idx = self._find_next_index(self.image_index, -1)
		if idx is None:
			return
		self.image_index = idx
		self._load_current_image()

	def next_image(self) -> None:
		if not self.image_paths:
			return
		self._save_current_state()
		idx = self._find_next_index(self.image_index, 1)
		if idx is None:
			return
		self.image_index = idx
		self._load_current_image()

	def _reset_crop_to_max_center(self) -> None:
		if not self.original_image:
			return
		w, h = self.original_image.size

		crop_w, crop_h = self._max_crop_wh_for_image(w, h)

		cx = w / 2.0
		cy = h / 2.0
		# Apply initial size scale (slider percent)
		scale_pct = float(self.size_scale.get()) / 100.0
		rect_w = crop_w * scale_pct
		rect_h = crop_h * scale_pct
		self._set_crop_from_center(cx, cy, rect_w, rect_h)

	def _on_size_change(self, _value: str) -> None:
		if not self.original_image or not self.crop_rect:
			return
		if self._updating_slider:
			return
		w, h = self.original_image.size

		# Max crop that fits (15:10) in the current image (baseline for slider)
		max_w, max_h = self._max_crop_wh_for_image(w, h)

		pct = float(self.size_scale.get()) / 100.0
		new_w = max_w * pct
		new_h = max_h * pct

		# Keep center stable, but ensure the HEX guide stays inside the image.
		cx, cy = self.crop_rect.center
		r_desired = self._hex_r_from_rect(new_w, new_h)
		r_global_max = self._hex_r_global_max(w, h)
		if r_desired > r_global_max and r_desired > 0:
			factor = r_global_max / r_desired
			new_w *= factor
			new_h *= factor
			r_desired = self._hex_r_from_rect(new_w, new_h)
		cx, cy = self._clamp_center_for_hex(cx, cy, r_desired, w, h)
		self._set_crop_from_center(cx, cy, new_w, new_h)
		self._redraw()
		self._update_info()

	def _canvas_to_image(self, cx: float, cy: float) -> tuple[float, float] | None:
		if not self.original_image:
			return None
		x = (cx - self.img_offset_x) / self.scale
		y = (cy - self.img_offset_y) / self.scale
		return x, y

	def _on_mouse_down(self, event: tk.Event) -> None:
		if not self.crop_rect:
			return
		img_xy = self._canvas_to_image(event.x, event.y)
		if not img_xy:
			return
		x, y = img_xy
		if self.crop_rect.left <= x <= self.crop_rect.right and self.crop_rect.top <= y <= self.crop_rect.bottom:
			self.dragging = True
			self.drag_last_x = event.x
			self.drag_last_y = event.y

	def _on_mouse_drag(self, event: tk.Event) -> None:
		if not (self.dragging and self.crop_rect and self.original_image):
			return
		dx_canvas = event.x - self.drag_last_x
		dy_canvas = event.y - self.drag_last_y
		self.drag_last_x = event.x
		self.drag_last_y = event.y

		dx_img = dx_canvas / self.scale
		dy_img = dy_canvas / self.scale
		self.crop_rect.left += dx_img
		self.crop_rect.right += dx_img
		self.crop_rect.top += dy_img
		self.crop_rect.bottom += dy_img
		# Clamp so the hex guide stays inside the image.
		img_w, img_h = self.original_image.size
		r = self._hex_r_from_rect(self.crop_rect.width, self.crop_rect.height)
		cx, cy = self.crop_rect.center
		cx, cy = self._clamp_center_for_hex(cx, cy, r, img_w, img_h)
		self._set_crop_from_center(cx, cy, self.crop_rect.width, self.crop_rect.height)
		self._redraw()
		self._update_info()

	def _on_mouse_up(self, _event: tk.Event) -> None:
		self.dragging = False

	def _nudge(self, dx_canvas: float, dy_canvas: float) -> None:
		if not (self.crop_rect and self.original_image):
			return
		dx_img = dx_canvas / self.scale
		dy_img = dy_canvas / self.scale
		self.crop_rect.left += dx_img
		self.crop_rect.right += dx_img
		self.crop_rect.top += dy_img
		self.crop_rect.bottom += dy_img
		img_w, img_h = self.original_image.size
		r = self._hex_r_from_rect(self.crop_rect.width, self.crop_rect.height)
		cx, cy = self.crop_rect.center
		cx, cy = self._clamp_center_for_hex(cx, cy, r, img_w, img_h)
		self._set_crop_from_center(cx, cy, self.crop_rect.width, self.crop_rect.height)
		self._redraw()
		self._update_info()

	def _compute_display_transform(self) -> None:
		if not self.original_image:
			return
		canvas_w = max(1, self.canvas.winfo_width())
		canvas_h = max(1, self.canvas.winfo_height())
		img_w, img_h = self.original_image.size

		scale = min(canvas_w / img_w, canvas_h / img_h)
		scale = max(0.05, min(scale, 1.0))

		disp_w = int(img_w * scale)
		disp_h = int(img_h * scale)
		self.display_image = self.original_image.resize((disp_w, disp_h), Image.LANCZOS)
		self.photo = ImageTk.PhotoImage(self.display_image)

		self.scale = scale
		self.img_offset_x = (canvas_w - disp_w) // 2
		self.img_offset_y = (canvas_h - disp_h) // 2

	def _update_info(self) -> None:
		if not (self.original_image and self.crop_rect and self.image_paths):
			self.info_var.set("No image loaded")
			return
		path = self.image_paths[self.image_index]
		w, h = self.original_image.size
		cw = int(round(self.crop_rect.width))
		ch = int(round(self.crop_rect.height))
		self.info_var.set(f"{path.name}  ({self.image_index + 1}/{len(self.image_paths)})   image: {w}×{h}   crop: {cw}×{ch}")

	def _draw_hex_guide(self, x0: float, y0: float, x1: float, y1: float) -> None:
		# draw a regular hexagon centered in the crop rect
		cx = (x0 + x1) / 2.0
		cy = (y0 + y1) / 2.0
		w = (x1 - x0)
		h = (y1 - y0)

		# Largest hex that fits the crop rect (touches it).
		r = self._hex_r_from_rect(w, h)
		points: list[float] = []
		rot = self._hex_rotation_degrees()
		for k in range(6):
			angle = math.radians(-90 + rot + k * 60)
			points.extend([cx + r * math.cos(angle), cy + r * math.sin(angle)])

		self.canvas.create_polygon(
			*points,
			fill="",
			outline="#d0d0d0",
			width=2,
			dash=(6, 4),
		)

	def _redraw(self) -> None:
		self.canvas.delete("all")
		if not self.original_image:
			self.canvas.create_text(
				20,
				20,
				anchor="nw",
				fill="#cccccc",
				text="Open images to start…",
				font=("Segoe UI", 12),
			)
			return

		self._compute_display_transform()
		if not self.photo:
			return

		self.canvas.create_image(self.img_offset_x, self.img_offset_y, anchor="nw", image=self.photo)

		if not self.crop_rect:
			return

		# crop rect in canvas coords
		x0 = self.img_offset_x + self.crop_rect.left * self.scale
		y0 = self.img_offset_y + self.crop_rect.top * self.scale
		x1 = self.img_offset_x + self.crop_rect.right * self.scale
		y1 = self.img_offset_y + self.crop_rect.bottom * self.scale

		# dim everything outside crop (canvas-wide, so crop can exceed image)
		canvas_w = max(1, self.canvas.winfo_width())
		canvas_h = max(1, self.canvas.winfo_height())
		cx0, cy0, cx1, cy1 = 0, 0, canvas_w, canvas_h
		self.canvas.create_rectangle(cx0, cy0, cx1, y0, fill="black", stipple="gray50", width=0)
		self.canvas.create_rectangle(cx0, y1, cx1, cy1, fill="black", stipple="gray50", width=0)
		self.canvas.create_rectangle(cx0, y0, x0, y1, fill="black", stipple="gray50", width=0)
		self.canvas.create_rectangle(x1, y0, cx1, y1, fill="black", stipple="gray50", width=0)

		# crop border
		self.canvas.create_rectangle(x0, y0, x1, y1, outline="#ffffff", width=2)
		self.canvas.create_rectangle(x0, y0, x1, y1, outline="#bbbbbb", width=1, dash=(4, 4))

		# hex guide inside crop
		self._draw_hex_guide(x0, y0, x1, y1)

	def export_crop(self) -> None:
		if not (self.original_image and self.crop_rect and self.image_paths):
			return

		if self.output_dir is None:
			out = filedialog.askdirectory(title="Select output folder", initialdir=os.getcwd())
			if not out:
				return
			self.output_dir = Path(out)

		path = self.image_paths[self.image_index]
		left = int(round(self.crop_rect.left))
		top = int(round(self.crop_rect.top))
		right = int(round(self.crop_rect.right))
		bottom = int(round(self.crop_rect.bottom))

		if right <= left or bottom <= top:
			messagebox.showerror("Export", "Invalid crop rectangle.")
			return

		out_w = right - left
		out_h = bottom - top

		# Build a white canvas and paste the intersection of image & crop.
		out_img = Image.new("RGB", (out_w, out_h), (255, 255, 255))
		img_w, img_h = self.original_image.size
		src_l = max(0, left)
		src_t = max(0, top)
		src_r = min(img_w, right)
		src_b = min(img_h, bottom)
		if src_r > src_l and src_b > src_t:
			piece = self.original_image.crop((src_l, src_t, src_r, src_b))
			dst_x = src_l - left
			dst_y = src_t - top
			out_img.paste(piece.convert("RGB"), (dst_x, dst_y))

		if self.export_hex_var.get():
			draw = ImageDraw.Draw(out_img)
			cx = out_w / 2.0
			cy = out_h / 2.0
			r = self._hex_r_from_rect(out_w, out_h)
			rot = self._hex_rotation_degrees()
			pts: list[tuple[float, float]] = []
			for k in range(6):
				angle = math.radians(-90 + rot + k * 60)
				pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
			line_w = max(2, int(round(min(out_w, out_h) / 400)))
			# close the loop
			draw.line(pts + [pts[0]], fill=(200, 200, 200), width=line_w)

		# Save as PNG to avoid generation loss; keeps pixel dimensions (no resize).
		out_name = f"{path.stem}_15x10.png"
		out_path = self.output_dir / out_name
		try:
			out_img.save(out_path, format="PNG")
		except Exception as ex:
			messagebox.showerror("Export", f"Failed to save:\n{out_path}\n\n{ex}")
			return

		self.status_var.set(f"Exported: {out_path}")


def main() -> None:
	root = tk.Tk()

	# Better DPI handling on Windows where available
	try:
		from ctypes import windll  # type: ignore

		windll.shcore.SetProcessDpiAwareness(1)
	except Exception:
		pass

	style = ttk.Style(root)
	try:
		style.theme_use("vista")
	except Exception:
		pass

	app = HexCropApp(root)
	root.minsize(900, 650)
	root.mainloop()


if __name__ == "__main__":
	main()
