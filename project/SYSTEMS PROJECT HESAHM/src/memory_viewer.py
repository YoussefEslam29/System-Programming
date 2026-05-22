import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from tkinter import ttk
from typing import Any, Optional, Protocol

MEM_SIZE:   int = 0x100000
COLS:       int = 16
TOTAL_ROWS: int = MEM_SIZE // COLS

BG_ROOT:    str = "#F5F5F5"
BG_PANEL:   str = "white"
BG_HDR:     str = "#F0F0F0"
BG_TOOL:    str = "#EAEAEA"
BG_STATUS:  str = "#1A6FAB"

FG_HDR:      str = "#555555"
FG_ADDR:     str = "#1A6FAB"
FG_LOADED:   str = "#111111"
FG_RELOC:    str = "#B85C00"
FG_ZERO:     str = "#BBBBBB"
FG_ASCII:    str = "#1A6FAB"
FG_ASCII_NP: str = "#CCCCCC"
FG_STATUS:   str = "white"

SEP: str = "#DDDDDD"


class _HTMEDataLike(Protocol):
    program_name:         str
    start_address:        int
    program_length:       int
    exec_address:         int
    text_entries:         list[tuple[int, str]]
    modification_records: list[tuple[int, int]]


def _apply_m_record(
    mem: bytearray, addr: int, halfbytes: int, delta: int
) -> None:
    n    = (halfbytes + 1) // 2
    v    = int.from_bytes(mem[addr : addr + n], "big")
    mask = (1 << (halfbytes * 4)) - 1
    new  = (v & ~mask) | (((v & mask) + delta) & mask)
    mem[addr : addr + n] = new.to_bytes(n, "big")


class MemoryModel:
    def __init__(self) -> None:
        self.memory: bytearray = bytearray(MEM_SIZE)
        self.loaded: bytearray = bytearray(MEM_SIZE)
        self.reloc:  bytearray = bytearray(MEM_SIZE)
        self.program_name:   str = ""
        self.start_address:  int = 0
        self.program_length: int = 0
        self.exec_address:   int = 0

    def reset(self) -> None:
        for b in (self.memory, self.loaded, self.reloc):
            b[:] = bytes(MEM_SIZE)
        self.program_name   = ""
        self.start_address  = 0
        self.program_length = 0
        self.exec_address   = 0

    def load_from_htme_data(
        self, data: _HTMEDataLike, load_offset: int = 0
    ) -> None:
        self.reset()
        self.program_name   = data.program_name
        self.start_address  = data.start_address  + load_offset
        self.program_length = data.program_length
        self.exec_address   = data.exec_address   + load_offset

        for addr, hex_str in data.text_entries:
            dest = addr + load_offset
            for i in range(0, len(hex_str), 2):
                if 0 <= dest < MEM_SIZE:
                    self.memory[dest] = int(hex_str[i : i + 2], 16)
                    self.loaded[dest] = 1
                dest += 1

        for addr, halfbytes in data.modification_records:
            dest = addr + load_offset
            n = (halfbytes + 1) // 2
            for j in range(n):
                if 0 <= dest + j < MEM_SIZE:
                    self.reloc[dest + j] = 1
            if load_offset and 0 <= dest and dest + n <= MEM_SIZE:
                _apply_m_record(self.memory, dest, halfbytes, load_offset)


class MemoryViewer:
    def __init__(self) -> None:
        self.model: MemoryModel = MemoryModel()

        self._htme_data:  Optional[_HTMEDataLike] = None
        self._root:       Optional[tk.Tk]         = None
        self._canvas:     Optional[tk.Canvas]     = None
        self._hdr_canvas: Optional[tk.Canvas]     = None
        self._vsb:        Optional[ttk.Scrollbar] = None
        self._font:       Optional[tkfont.Font]   = None
        self._bfont:      Optional[tkfont.Font]   = None
        self._sfont:      Optional[tkfont.Font]   = None
        self._offset_var: Optional[tk.StringVar]  = None
        self._goto_var:   Optional[tk.StringVar]  = None
        self._info_var:   Optional[tk.StringVar]  = None
        self._status_var: Optional[tk.StringVar]  = None

        self._row_h:  int = 0
        self._char_w: int = 0
        self._x_addr: int = 0
        self._x_hex0: int = 0
        self._hex_cw: int = 0
        self._x_asc:  int = 0

    def load(self, data: _HTMEDataLike, load_offset: int = 0) -> None:
        self._htme_data = data
        self.model.load_from_htme_data(data, load_offset)

    def show(self) -> None:
        self._root = tk.Tk()
        self._root.title("SIC/XE Memory Viewer")
        self._root.configure(bg=BG_ROOT)
        self._root.minsize(820, 500)

        self._setup_font()
        self._build_toolbar()
        self._build_panel()
        self._build_status()

        self._draw_header()
        self._root.after(30, self._after_show)
        self._root.mainloop()

    def _setup_font(self) -> None:
        assert self._root is not None
        self._font  = tkfont.Font(root=self._root, family="Courier New", size=11)
        self._bfont = tkfont.Font(root=self._root, family="Courier New", size=11, weight="bold")
        self._sfont = tkfont.Font(root=self._root, family="Segoe UI",    size=9)
        self._char_w = self._font.measure("M")
        linespace    = self._font.metrics("linespace")
        self._row_h  = (linespace if isinstance(linespace, int) else 16) + 4

        # "000000:  " and "Address: " are both 9 chars, so column labels line up
        self._x_addr = 10
        self._x_hex0 = self._x_addr + self._char_w * 9
        self._hex_cw = self._char_w * 3
        self._x_asc  = self._x_hex0 + COLS * self._hex_cw + self._char_w * 2

    def _build_toolbar(self) -> None:
        assert self._root is not None
        assert self._font is not None and self._sfont is not None
        font  = self._font
        sfont = self._sfont

        bar = tk.Frame(self._root, bg=BG_TOOL, padx=10, pady=7)
        bar.pack(side="top", fill="x")

        def _btn(text: str, cmd: Callable[[], None]) -> None:
            tk.Button(
                bar, text=text, command=cmd,
                bg=BG_PANEL, fg="#333333", relief="solid", bd=1,
                padx=10, pady=2, font=sfont,
                activebackground="#D8D8D8", cursor="hand2",
            ).pack(side="left", padx=(0, 6))

        tk.Label(bar, text="Load offset:", bg=BG_TOOL, fg=FG_HDR,
                 font=sfont).pack(side="left", padx=(0, 3))
        self._offset_var = tk.StringVar(value="000000")
        tk.Entry(bar, textvariable=self._offset_var, width=8,
                 font=font, relief="solid", bd=1).pack(side="left", padx=(0, 4))
        _btn("Apply", self._on_apply_offset)

        tk.Label(bar, text="Go to:", bg=BG_TOOL, fg=FG_HDR,
                 font=sfont).pack(side="left", padx=(14, 3))
        self._goto_var = tk.StringVar()
        tk.Entry(bar, textvariable=self._goto_var, width=8,
                 font=font, relief="solid", bd=1).pack(side="left", padx=(0, 4))
        _btn("Go", self._on_goto)

        self._info_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._info_var, bg=BG_TOOL,
                 fg="#777777", font=sfont).pack(side="right", padx=6)

    def _build_panel(self) -> None:
        assert self._root is not None

        outer = tk.Frame(self._root, bg=BG_ROOT, padx=14, pady=8)
        outer.pack(fill="both", expand=True)

        card = tk.Frame(outer, bg=BG_PANEL, relief="solid", bd=1)
        card.pack(fill="both", expand=True)

        self._hdr_canvas = tk.Canvas(
            card, height=self._row_h + 8, bg=BG_HDR, highlightthickness=0
        )
        self._hdr_canvas.pack(fill="x")
        tk.Frame(card, height=1, bg=SEP).pack(fill="x")

        body = tk.Frame(card, bg=BG_PANEL)
        body.pack(fill="both", expand=True)

        self._vsb = ttk.Scrollbar(body, orient="vertical")
        self._vsb.pack(side="right", fill="y")

        self._canvas = tk.Canvas(
            body, bg=BG_PANEL, highlightthickness=0,
            yscrollcommand=self._vsb.set,
        )
        self._canvas.pack(side="left", fill="both", expand=True)
        self._vsb.config(command=self._yview)

        self._canvas.bind("<Configure>",  self._on_configure)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-4>",   self._on_wheel)
        self._canvas.bind("<Button-5>",   self._on_wheel)
        self._canvas.bind("<Motion>",     self._on_motion)

    def _build_status(self) -> None:
        assert self._root is not None and self._sfont is not None
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(
            self._root, textvariable=self._status_var,
            bg=BG_STATUS, fg=FG_STATUS, font=self._sfont,
            anchor="w", padx=10, pady=4,
        ).pack(side="bottom", fill="x")

    def _after_show(self) -> None:
        self._configure_scrollregion()
        self._redraw()

    def _draw_header(self) -> None:
        hdr = self._hdr_canvas
        if hdr is None:
            return
        assert self._bfont is not None

        hdr.delete("all")
        y = (self._row_h + 8) // 2

        hdr.create_text(self._x_addr, y, text="Address:",
                        font=self._bfont, fill=FG_HDR, anchor="w")

        for col in range(COLS):
            hdr.create_text(
                self._x_hex0 + col * self._hex_cw, y,
                text=f"{col:X}", font=self._bfont, fill=FG_HDR, anchor="w",
            )

        sep_x = self._x_asc - self._char_w
        h = self._row_h + 8
        hdr.create_line(sep_x, 2, sep_x, h - 2, fill=SEP)

        hdr.create_text(self._x_asc, y, text="ASCII",
                        font=self._bfont, fill=FG_HDR, anchor="w")

    def _configure_scrollregion(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        w = max(canvas.winfo_width(), 820)
        canvas.config(scrollregion=(0, 0, w, TOTAL_ROWS * self._row_h))
        self._update_info()

    def _redraw(self, *_: object) -> None:
        canvas = self._canvas
        if canvas is None or self._row_h == 0:
            return

        canvas.delete("content")
        y1, y2 = canvas.yview()
        first = max(0, int(y1 * TOTAL_ROWS) - 1)
        last  = min(int(y2 * TOTAL_ROWS) + 2, TOTAL_ROWS)

        for row in range(first, last):
            self._draw_row(canvas, row)

    def _draw_row(self, canvas: tk.Canvas, row: int) -> None:
        assert self._font is not None

        addr = row * COLS
        y    = row * self._row_h + self._row_h // 2

        canvas.create_text(
            self._x_addr, y, text=f"{addr:06X}:",
            font=self._font, fill=FG_ADDR, anchor="w", tags=("content",),
        )

        row_loaded = self.model.loaded[addr : addr + COLS]
        row_reloc  = self.model.reloc[addr  : addr + COLS]
        has_data   = any(row_loaded) or any(row_reloc)

        if has_data:
            for col in range(COLS):
                ba    = addr + col
                val   = self.model.memory[ba]
                color = (
                    FG_RELOC  if row_reloc[col]  else
                    FG_LOADED if row_loaded[col] else FG_ZERO
                )
                canvas.create_text(
                    self._x_hex0 + col * self._hex_cw, y,
                    text=f"{val:02X}",
                    font=self._font, fill=color, anchor="w", tags=("content",),
                )
        else:
            canvas.create_text(
                self._x_hex0, y,
                text=" ".join("00" for _ in range(COLS)),
                font=self._font, fill=FG_ZERO, anchor="w", tags=("content",),
            )

        if has_data:
            for col in range(COLS):
                ba        = addr + col
                val       = self.model.memory[ba]
                printable = 0x20 <= val <= 0x7E
                ch        = chr(val) if printable else "."
                color     = FG_ASCII if (printable and row_loaded[col]) else FG_ASCII_NP
                canvas.create_text(
                    self._x_asc + col * self._char_w, y,
                    text=ch,
                    font=self._font, fill=color, anchor="w", tags=("content",),
                )
        else:
            canvas.create_text(
                self._x_asc, y, text="." * COLS,
                font=self._font, fill=FG_ASCII_NP, anchor="w", tags=("content",),
            )

    def _yview(self, *args: Any) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        canvas.yview(*args)
        self._redraw()

    def _on_configure(self, event: "tk.Event[tk.Canvas]") -> None:
        canvas = self._canvas
        if canvas is None:
            return
        canvas.config(scrollregion=(0, 0, event.width, TOTAL_ROWS * self._row_h))
        self._redraw()

    def _on_wheel(self, event: "tk.Event[tk.Canvas]") -> None:
        canvas = self._canvas
        if canvas is None:
            return
        if event.num == 4:
            canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            canvas.yview_scroll(3, "units")
        else:
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        self._redraw()

    def _on_motion(self, event: "tk.Event[tk.Canvas]") -> None:
        canvas     = self._canvas
        status_var = self._status_var
        if canvas is None or status_var is None:
            return

        cy  = canvas.canvasy(event.y)
        row = int(cy // self._row_h)
        col = (event.x - self._x_hex0) // self._hex_cw

        if 0 <= row < TOTAL_ROWS and 0 <= col < COLS:
            ba  = row * COLS + col
            val = self.model.memory[ba]
            ch  = chr(val) if 0x20 <= val <= 0x7E else "."
            tag = ""
            if self.model.reloc[ba]:
                tag = "  [relocatable]"
            elif not self.model.loaded[ba]:
                tag = "  [unloaded]"
            status_var.set(
                f"Address: {ba:06X}h   Value: {val:02X}h  ({val:3d})  '{ch}'{tag}"
            )
        else:
            status_var.set("Ready")

    def _on_apply_offset(self) -> None:
        assert self._offset_var is not None and self._status_var is not None

        offset = self._parse_hex(self._offset_var.get(), None)
        if offset is None:
            self._status_var.set("Invalid hex offset")
            return
        if self._htme_data is None:
            return
        self.model.load_from_htme_data(self._htme_data, offset)
        self._configure_scrollregion()
        self._goto_address(self.model.start_address)
        self._redraw()

    def _on_goto(self) -> None:
        assert self._goto_var is not None and self._status_var is not None

        addr = self._parse_hex(self._goto_var.get(), None)
        if addr is None:
            self._status_var.set("Invalid hex address")
            return
        self._goto_address(addr)

    def _goto_address(self, addr: int) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        row  = max(0, min(addr // COLS, TOTAL_ROWS - 1))
        frac = row / TOTAL_ROWS
        canvas.yview_moveto(frac)
        self._redraw()

    def _parse_hex(self, s: str, default: Optional[int]) -> Optional[int]:
        try:
            return int(s.strip(), 16)
        except ValueError:
            return default

    def _update_info(self) -> None:
        info_var = self._info_var
        if info_var is None:
            return
        m = self.model
        if m.program_name:
            info_var.set(
                f"{m.program_name}   "
                f"start:{m.start_address:06X}  "
                f"len:{m.program_length:04X}  "
                f"exec:{m.exec_address:06X}"
            )
