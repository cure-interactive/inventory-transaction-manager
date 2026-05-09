#!/usr/bin/env python3
# =============================================================================
# [📦 Inventory] [🧮 Weighted Average Cost] [🖥️ CustomTkinter App]
# =============================================================================
"""
@fileoverview
  Inventory transaction manager (PURCHASE/SALE) using weighted-average costing,
  implemented as a CustomTkinter desktop app to replace spreadsheet formulas.

  NEW: Project selection (like png_to_ico GUI):
  - Select a "Project Directory" (folder)
  - Transactions persist to: <ProjectDir>/inventory_data.json
  - Recent project folders persist to: <ScriptDir>/config.json

  NEW: SKU Aliases:
  - Aliases persist to: <ProjectDir>/inventory_data.json (alongside transactions)
  - Transactions + Overview tables show an Alias column (after SKU)
  - Transactions form has an Alias dropdown that sets the SKU field

  Sorting:
  - Transactions are sorted by Date ascending, then by stable insertion order.

  Date format accepted:
  - YYYY-MM-DD or M/D/YYYY (normalized to YYYY-MM-DD)
"""

from __future__ import annotations

import json
import math
import os
import sys
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# =============================================================================
# Optional dependency: tkcalendar (nice date picker)
#   pip install tkcalendar
# =============================================================================
try:
  from tkcalendar import Calendar  # type: ignore
except Exception:
  Calendar = None  # type: ignore

def apply_entry_shortcuts(entry_widget) -> None:
  """
  Normalize common text shortcuts across OS for Tk/CustomTkinter entries:
    - Ctrl+A selects all
    - Ctrl+V replaces selection (if any), otherwise inserts at caret
  """
  # CTkEntry often wraps the real tk.Entry as `_entry`
  inner = getattr(entry_widget, "_entry", entry_widget)

  def _select_all(_e=None):
    try:
      inner.selection_range(0, tk.END)
      inner.icursor(tk.END)
    except Exception:
      pass
    return "break"

  def _paste_replace(_e=None):
    try:
      # If there's a selection, delete it first (Windows-style replace).
      try:
        sel_first = inner.index("sel.first")
        sel_last  = inner.index("sel.last")
        inner.delete(sel_first, sel_last)
      except Exception:
        pass

      clip = inner.clipboard_get()
      inner.insert(tk.INSERT, clip)
    except Exception:
      pass
    return "break"

  # Windows/Linux
  inner.bind("<Control-a>", _select_all, add="+")
  inner.bind("<Control-A>", _select_all, add="+")
  inner.bind("<Control-v>", _paste_replace, add="+")
  inner.bind("<Control-V>", _paste_replace, add="+")
  inner.bind("<Shift-Insert>", _paste_replace, add="+")

  # macOS (optional)
  if sys.platform == "darwin":
    inner.bind("<Command-a>", _select_all, add="+")
    inner.bind("<Command-v>", _paste_replace, add="+")


def bind_enter_shortcut(widget, callback) -> None:
  """Bind Enter and keypad Enter to a callback for a specific widget."""
  target = getattr(widget, "_entry", widget)

  def _on_enter(_e=None):
    try:
      callback()
    except Exception:
      return None
    return "break"

  target.bind("<Return>", _on_enter, add="+")
  target.bind("<KP_Enter>", _on_enter, add="+")

# =============================================================================
# Windows Taskbar Identity (AppUserModelID)
# =============================================================================

def set_windows_app_user_model_id(app_id: str) -> None:
  """
  Set an explicit Windows AppUserModelID for this process (best-effort).

  Notes:
  - No-op on non-Windows.
  - Call BEFORE creating the Tk/CTk window (i.e., early in main()).
  """
  try:
    if os.name != "nt":
      return

    import ctypes  # stdlib, Windows-only usage

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
  except Exception:
    return

APP_USER_MODEL_ID = "CureInteractive.InventoryTransactionManager"

# =============================================================================
# Tooltips (best-effort; optional dependency)
# =============================================================================

try:
  from CTkToolTip import CTkToolTip  # type: ignore
except Exception:
  CTkToolTip = None  # type: ignore


def tooltip(*widgets: Any, text: str) -> None:
  """Attach (or update) the same tooltip on one or more Tk/CTk widgets.

  Behavior:
  - If CTkToolTip is not installed, this is a no-op.
  - Tooltips are cached on each widget as `_cure_tooltip`.
  - If a widget already has a tooltip, we best-effort close/destroy it first.

  Args:
    *widgets: One or more tkinter/customtkinter widgets.
    text: Tooltip text to show.
  """
  if CTkToolTip is None:
    return

  for w in widgets:
    if w is None:
      continue

    # Best-effort: remove old tooltip instance if we've attached one before.
    old = getattr(w, "_cure_tooltip", None)
    if old is not None:
      try:
        if hasattr(old, "hide"):
          old.hide()
      except Exception:
        pass
      try:
        if hasattr(old, "destroy"):
          old.destroy()
      except Exception:
        pass

    try:
      w._cure_tooltip = CTkToolTip(w, message=str(text))  # type: ignore[attr-defined]
    except Exception:
      # Last resort: never let tooltips break the UI.
      try:
        w._cure_tooltip = None  # type: ignore[attr-defined]
      except Exception:
        pass

def clear_tooltip(*widgets: Any) -> None:
  for w in widgets:
    if w is None:
      continue
    old = getattr(w, "_cure_tooltip", None)
    if old is not None:
      try:
        if hasattr(old, "hide"):
          old.hide()
      except Exception:
        pass
      try:
        if hasattr(old, "destroy"):
          old.destroy()
      except Exception:
        pass
    try:
      w._cure_tooltip = None  # type: ignore[attr-defined]
    except Exception:
      pass


# =============================================================================
# Window Icon (title bar / taskbar best-effort)
# =============================================================================

def set_window_icon(root, ico_path: str, png_path: str) -> None:
  """
  Set a title-bar icon with best-effort cross-platform behavior.

  Windows:
    - iconbitmap(.ico) works for title bar + taskbar in most cases.
  Linux/macOS:
    - iconphoto(.png) is the common path.

  Notes:
  - We try both; failures are ignored (best effort).
  - Paths should be absolute for reliability.
  """
  ico_abs = os.path.abspath(ico_path) if ico_path else ""
  png_abs = os.path.abspath(png_path) if png_path else ""

  try:
    if ico_abs and os.path.isfile(ico_abs):
      root.iconbitmap(ico_abs)
  except Exception:
    pass

  try:
    if png_abs and os.path.isfile(png_abs):
      img = tk.PhotoImage(file=png_abs)
      root.iconphoto(True, img)
      root._iconphoto_ref = img  # type: ignore[attr-defined]
  except Exception:
    pass


# =============================================================================
# TTK Theme Parity (Treeview + Scrollbar) — dark mode matching CustomTkinter
# =============================================================================

def _ttk_font(size: int, *, weight: str = "normal"):
  return ("Segoe UI", size, weight)

def _ctk_color(c):
  """
  Resolve a CustomTkinter theme color (single or (light,dark) tuple) to a color string.
  """
  if isinstance(c, (tuple, list)):
    return c[1]  # dark mode index
  return c

def apply_dark_ttk_treeview_style(root):
  """
  Force ttk.Treeview styling to match CustomTkinter dark mode.
  Safe to call multiple times.
  """
  style = ttk.Style(master=root)

  try:
    style.theme_use("default")
  except Exception:
    pass

  bg     = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
  bg_alt = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
  fg     = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
  sel_bg = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["hover_color"])
  sel_fg = fg

  style.configure(
    "Treeview",
    background=bg,
    fieldbackground=bg,
    foreground=fg,
    rowheight=28,
    borderwidth=0,
    relief="flat",
    font=_ttk_font(12),
  )

  style.map(
    "Treeview",
    background=[("selected", sel_bg)],
    foreground=[("selected", sel_fg)],
  )

  style.configure(
    "Treeview.Heading",
    background=bg_alt,
    foreground=fg,
    relief="flat",
    borderwidth=0,
    font=_ttk_font(13, weight="bold"),
  )

  style.map(
    "Treeview.Heading",
    background=[("active", bg_alt)],
    foreground=[("active", fg)],
  )

def apply_dark_ttk_scrollbar_style(root):
  """
  Dark-mode ttk.Scrollbar styling to match CustomTkinter theme.

  Styles:
    - Dark.Vertical.TScrollbar
    - Dark.Horizontal.TScrollbar
  """
  style = ttk.Style(master=root)

  try:
    style.theme_use("default")
  except Exception:
    pass

  bg       = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
  accent   = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["fg_color"])
  accent_h = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["hover_color"])

  def _configure_scrollbar_style(style_name: str) -> None:
    style.configure(
      style_name,
      background=accent,        # thumb
      troughcolor=bg,           # track
      bordercolor=bg,
      lightcolor=accent,
      darkcolor=accent,
      arrowcolor="#9aa4af",
      relief="flat",
      borderwidth=0,
      arrowsize=18,
      width=16,
    )

    style.map(
      style_name,
      background=[
        ("active", accent_h),
        ("!active", accent),
      ],
      arrowcolor=[
        ("active", "#9aa4af"),
        ("pressed", "#9aa4af"),
        ("!active", "#9aa4af"),
        ("disabled", "#666666"),
      ],
    )

  _configure_scrollbar_style("Dark.Vertical.TScrollbar")
  _configure_scrollbar_style("Dark.Horizontal.TScrollbar")


# =============================================================================
# [🧾 Constants]
# =============================================================================

TX_PURCHASE = "PURCHASE"
TX_SALE = "SALE"

SCRIPT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

APP_ICON_ICO_PATH = os.path.join(SCRIPT_ROOT_DIR, "icon.ico")
APP_ICON_PNG_PATH = os.path.join(SCRIPT_ROOT_DIR, "icon.png")
APP_SPLASH_ICON_PNG_PATH = os.path.join(SCRIPT_ROOT_DIR, "icon_512x512.png")

APP_CONFIG_FILENAME = "config.json"
APP_CONFIG_PATH = os.path.join(SCRIPT_ROOT_DIR, APP_CONFIG_FILENAME)

PROJECT_DATA_FILENAME = "inventory_data.json"

CUSTOM_TYPE_STRING = "string"
CUSTOM_TYPE_NUMBER = "number"
CUSTOM_TYPE_BOOLEAN = "boolean"
CUSTOM_TYPE_ENUM = "enum"
CUSTOM_FIELD_TYPES = [
  CUSTOM_TYPE_STRING,
  CUSTOM_TYPE_NUMBER,
  CUSTOM_TYPE_BOOLEAN,
  CUSTOM_TYPE_ENUM,
]
CUSTOM_TARGET_TRANSACTION = "transaction"
CUSTOM_TARGET_ALIAS = "alias"
CUSTOM_FIELD_TARGETS = [
  CUSTOM_TARGET_TRANSACTION,
  CUSTOM_TARGET_ALIAS,
]

FIELD_SCOPE_TX_TABLE = "tx_table"
FIELD_SCOPE_ALIAS_TABLE = "alias_table"
FIELD_SCOPE_OVERVIEW_INVENTORY = "overview_inventory"

BUILTIN_FIELD_DEFS = [
  {"id": "builtin:tx_table:id", "key": "id", "label": "ID", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Transaction identity number.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:date", "key": "date", "label": "Date", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_STRING, "description": "Transaction date.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:sku", "key": "sku", "label": "SKU", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_STRING, "description": "Stock keeping unit identifier.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:alias", "key": "alias", "label": "Alias", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_STRING, "description": "Alias name resolved from the SKU.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:type", "key": "type", "label": "Type", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_ENUM, "description": "Transaction kind.", "enum": [TX_PURCHASE, TX_SALE], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:qty", "key": "qty", "label": "Qty", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Transaction quantity.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:purchase_unit_cost", "key": "purchase_unit_cost", "label": "Purchase Unit Cost", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Per-unit purchase cost for PURCHASE rows.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:sale_unit_price", "key": "sale_unit_price", "label": "Sale Unit Price", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Per-unit sale price for SALE rows.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:purchase_total_cost", "key": "purchase_total_cost", "label": "Purchase Total Cost", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Computed Qty x Purchase Unit Cost.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:prev_avg_cost", "key": "prev_avg_cost", "label": "Prev Avg Cost", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Weighted average cost before this transaction.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:onhand_qty", "key": "onhand_qty", "label": "OnHand Qty", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Computed on-hand quantity after this transaction.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:avg_cost_after", "key": "avg_cost_after", "label": "Avg Cost", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Weighted average cost after this transaction.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:cogs", "key": "cogs", "label": "COGS", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Computed cost of goods sold for SALE rows.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:onhand_cost", "key": "onhand_cost", "label": "OnHand Cost", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Computed on-hand inventory value after this transaction.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:sales_rev", "key": "sales_rev", "label": "Sales Rev", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Computed Qty x Sale Unit Price for SALE rows.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:gross_profit", "key": "gross_profit", "label": "Gross Profit", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_NUMBER, "description": "Computed Sales Rev minus COGS for SALE rows.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:tx_table:note", "key": "note", "label": "Note", "scope": FIELD_SCOPE_TX_TABLE, "target": CUSTOM_TARGET_TRANSACTION, "type": CUSTOM_TYPE_STRING, "description": "Free-form transaction note.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:alias_table:sku", "key": "sku", "label": "SKU", "scope": FIELD_SCOPE_ALIAS_TABLE, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_STRING, "description": "Alias SKU key.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:alias_table:name", "key": "name", "label": "Name", "scope": FIELD_SCOPE_ALIAS_TABLE, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_STRING, "description": "Alias display name.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:sku", "key": "sku", "label": "SKU", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_STRING, "description": "Inventory overview SKU.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:alias", "key": "alias", "label": "Alias", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_STRING, "description": "Inventory overview alias name.", "enum": [], "enabled": True, "removable": False, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:onhand_qty", "key": "onhand_qty", "label": "OnHand Qty", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_NUMBER, "description": "Computed on-hand quantity.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:avg_cost", "key": "avg_cost", "label": "Avg Cost", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_NUMBER, "description": "Computed weighted average cost.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:onhand_cost", "key": "onhand_cost", "label": "OnHand Cost", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_NUMBER, "description": "Computed on-hand inventory value.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:last_tx_date", "key": "last_tx_date", "label": "Last Tx Date", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_STRING, "description": "Date of the latest transaction for the SKU.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:last_sale_price", "key": "last_sale_price", "label": "Last Sale Price", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_NUMBER, "description": "Latest sale price seen for the SKU.", "enum": [], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
  {"id": "builtin:overview_inventory:status", "key": "status", "label": "Status", "scope": FIELD_SCOPE_OVERVIEW_INVENTORY, "target": CUSTOM_TARGET_ALIAS, "type": CUSTOM_TYPE_ENUM, "description": "Derived stock status.", "enum": ["IN STOCK", "OUT", "NEGATIVE (OVERSOLD)"], "enabled": True, "removable": True, "enum_editable": False, "source": "system"},
]


# =============================================================================
# [🧰 Logging] cure-log-ish minimal console logger
# =============================================================================

class Log:
  ANSI = {
    "reset": "\x1b[0m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "cyan": "\x1b[36m",
  }

  @staticmethod
  def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  @staticmethod
  def info(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("ℹ️", Log.ANSI["cyan"], tag, msg, data)

  @staticmethod
  def warn(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("⚠️", Log.ANSI["yellow"], tag, msg, data)

  @staticmethod
  def error(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("🛑", Log.ANSI["red"], tag, msg, data)

  @staticmethod
  def ok(tag: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
    Log._print("✅", Log.ANSI["green"], tag, msg, data)

  @staticmethod
  def _print(icon: str, color: str, tag: str, msg: str, data: Optional[Dict[str, Any]]) -> None:
    base = f"[{Log._ts()}] {icon} {tag} {msg}"
    if data:
      base += f" {data}"
    line = f"{color}{base}{Log.ANSI['reset']}"
    try:
      print(line)
    except UnicodeEncodeError:
      safe_base = base.encode("ascii", errors="replace").decode("ascii")
      print(f"{color}{safe_base}{Log.ANSI['reset']}")


# =============================================================================
# [🧾 Data Model]
# =============================================================================

@dataclass
class Transaction:
  id: int
  date: str
  sku: str
  type: str
  qty: int
  purchase_unit_cost: float = 0.0
  sale_unit_price: float = 0.0
  note: str = ""
  created_order: int = 0
  custom_fields: Dict[str, Any] = None  # type: ignore[assignment]

  def __post_init__(self) -> None:
    if not isinstance(self.custom_fields, dict):
      self.custom_fields = {}


# =============================================================================
# [🧮 Inventory Engine]
# =============================================================================

class InventoryEngine:
  def compute(self, transactions: List[Transaction]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    txs = sorted(transactions, key=lambda t: (t.date, t.created_order, t.id))

    state: Dict[str, Dict[str, Any]] = {}
    computed_rows: List[Dict[str, Any]] = []

    for t in txs:
      sku = t.sku.strip()
      if sku not in state:
        state[sku] = {
          "onhand_qty": 0,
          "onhand_cost": 0.0,
          "avg_cost": 0.0,
          "last_tx_date": "",
          "last_sale_price": 0.0,
          "last_sale_date": "",
        }

      s = state[sku]
      prev_avg = float(s["avg_cost"])
      prev_qty = int(s["onhand_qty"])
      prev_cost = float(s["onhand_cost"])

      purchase_total_cost = 0.0
      cogs = 0.0
      sales_rev = 0.0
      gross_profit = 0.0

      if t.type == TX_PURCHASE:
        purchase_total_cost = float(t.qty) * float(t.purchase_unit_cost)
        s["onhand_qty"] = prev_qty + int(t.qty)
        s["onhand_cost"] = prev_cost + purchase_total_cost

      elif t.type == TX_SALE:
        cogs = float(t.qty) * prev_avg
        sales_rev = float(t.qty) * float(t.sale_unit_price)
        gross_profit = sales_rev - cogs

        s["onhand_qty"] = prev_qty - int(t.qty)
        s["onhand_cost"] = prev_cost - cogs

        s["last_sale_price"] = float(t.sale_unit_price)
        s["last_sale_date"] = t.date

      else:
        raise ValueError(f"Unknown type: {t.type}")

      if s["onhand_qty"] == 0:
        s["avg_cost"] = 0.0
        s["onhand_cost"] = 0.0
      else:
        s["avg_cost"] = float(s["onhand_cost"]) / float(s["onhand_qty"])

      s["last_tx_date"] = t.date

      computed_rows.append({
        "id": t.id,
        "date": t.date,
        "sku": sku,
        "type": t.type,
        "qty": t.qty,
        "purchase_unit_cost": float(t.purchase_unit_cost),
        "sale_unit_price": float(t.sale_unit_price),
        "purchase_total_cost": purchase_total_cost,
        "prev_avg_cost": prev_avg,
        "onhand_qty": int(s["onhand_qty"]),
        "avg_cost_after": float(s["avg_cost"]),
        "cogs": cogs,
        "onhand_cost": float(s["onhand_cost"]),
        "sales_rev": sales_rev,
        "gross_profit": gross_profit,
        "note": t.note,
        "custom_fields": dict(t.custom_fields or {}),
      })

    overview: Dict[str, Dict[str, Any]] = {}
    for sku, s in state.items():
      qty = int(s["onhand_qty"])
      status = "IN STOCK"
      if qty < 0:
        status = "NEGATIVE (OVERSOLD)"
      elif qty == 0:
        status = "OUT"

      overview[sku] = {
        "sku": sku,
        "onhand_qty": qty,
        "avg_cost": float(s["avg_cost"]),
        "onhand_cost": float(s["onhand_cost"]),
        "last_tx_date": s["last_tx_date"],
        "last_sale_price": float(s["last_sale_price"]) if s["last_sale_date"] else 0.0,
        "status": status,
      }

    return computed_rows, overview


# =============================================================================
# [💾 JSON Helpers] (app config + project data)
# =============================================================================

def _read_json(path: str) -> dict:
  try:
    if not os.path.isfile(path):
      return {}
    with open(path, "r", encoding="utf-8") as f:
      data = json.load(f)
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}

def _write_json_atomic(path: str, data: dict) -> None:
  try:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(data, f, indent=2)
    os.replace(tmp, path)
  except Exception:
    return

def _norm_dir(p: str) -> str:
  return os.path.normpath(os.path.abspath(p))

def _dedupe_keep_order(items: List[str]) -> List[str]:
  seen = set()
  out: List[str] = []
  for x in items:
    if x in seen:
      continue
    seen.add(x)
    out.append(x)
  return out

def _filter_existing_dirs(items: List[str]) -> List[str]:
  out: List[str] = []
  for p in items:
    try:
      if os.path.isdir(p):
        out.append(p)
    except Exception:
      pass
  return out


# =============================================================================
# [🧠 Helpers]
# =============================================================================

def parse_date(raw: str) -> str:
  s = (raw or "").strip()
  if not s:
    raise ValueError("Date is required")

  if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
    datetime.strptime(s, "%Y-%m-%d")
    return s

  if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", s):
    dt = datetime.strptime(s, "%m/%d/%Y")
    return dt.strftime("%Y-%m-%d")

  raise ValueError("Date must be YYYY-MM-DD or M/D/YYYY")

def money(x: float) -> str:
  return f"${x:,.2f}"

def _load_splash_icon_tk_image(png_path: str, *, max_size_px: int = 180) -> Optional[tk.PhotoImage]:
  """
  Best-effort load + downscale a splash icon image without Pillow.
  """
  abs_png = os.path.abspath(png_path) if png_path else ""
  if not abs_png or not os.path.isfile(abs_png):
    return None

  try:
    img = tk.PhotoImage(file=abs_png)
  except Exception:
    return None

  try:
    w = max(int(img.width()), 1)
    h = max(int(img.height()), 1)
    factor = max(1, int(math.ceil(max(w, h) / float(max_size_px))))
    if factor > 1:
      img = img.subsample(factor, factor)
  except Exception:
    pass

  return img


# =============================================================================
# [🖥️ UI App]
# =============================================================================

APP_TITLE = "Inventory Transaction Manager - Cure Interactive"

class InventoryApp(ctk.CTk):
  def __init__(self) -> None:
    super().__init__()

    set_window_icon(self, APP_ICON_ICO_PATH, APP_ICON_PNG_PATH)

    self.LOG_TAG = "[🧮 Inventory]"
    Log.info(self.LOG_TAG, "Initializing UI app.")
    self.title(APP_TITLE)

    self.geometry("1480x820")
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    self._startup_splash_build()
    self._startup_splash_set("Applying UI theme...")

    # Apply ttk theming (Treeview + Scrollbar) to match CTk dark mode
    apply_dark_ttk_treeview_style(self)
    apply_dark_ttk_scrollbar_style(self)

    self.engine = InventoryEngine()

    # Project selection state
    self.project_dir: str = ""
    self.project_data_path: str = ""

    # Recent projects (stored beside this script)
    app_cfg = _read_json(APP_CONFIG_PATH)
    self.recent_project_dirs_max = int(app_cfg.get("recent_project_dirs_max", 10) or 10)
    if self.recent_project_dirs_max <= 0:
      self.recent_project_dirs_max = 10

    raw = app_cfg.get("recent_project_dirs", [])
    if not isinstance(raw, list):
      raw = []
    self.recent_project_dirs: List[str] = []
    for p in raw:
      if isinstance(p, str) and p.strip():
        self.recent_project_dirs.append(_norm_dir(p.strip()))
    self.recent_project_dirs = _dedupe_keep_order(self.recent_project_dirs)
    self.recent_project_dirs = _filter_existing_dirs(self.recent_project_dirs)
    self.recent_project_dirs = self.recent_project_dirs[: self.recent_project_dirs_max]
    self._persist_app_config()
    Log.info(self.LOG_TAG, "Loaded app config.", {
      "config_path": APP_CONFIG_PATH,
      "recent_projects": len(self.recent_project_dirs),
      "recent_projects_max": self.recent_project_dirs_max,
    })

    # Data
    self.transactions: List[Transaction] = []
    self.next_id = 1
    self.next_created_order = 1

    # Aliases
    # Stored as list of dicts: [{"sku": "...", "name": "..."}, ...]
    self.aliases_list: List[Dict[str, str]] = []
    self._alias_map: Dict[str, str] = {}  # normalized lookup (sku -> name)

    # Custom per-SKU fields
    self.custom_fields_schema: List[Dict[str, Any]] = []
    self._custom_field_schema_map: Dict[str, Dict[str, Any]] = {}
    self.field_overrides: Dict[str, Dict[str, Any]] = {}
    self._field_registry_map: Dict[str, Dict[str, Any]] = {}

    # Guard flags for SKU/Alias UI syncing
    self._alias_sync_guard = False

    self._startup_splash_set("Building layout...")
    self._build_ui()

    # Auto-load first recent project if available
    self._startup_splash_set("Loading project data...")
    if self.recent_project_dirs:
      self.project_dir_var.set(self.recent_project_dirs[0])
      Log.info(self.LOG_TAG, "Auto-loading most recent project.", {"project_dir": self.recent_project_dirs[0]})
      self._load_project_dir(self.recent_project_dirs[0])
    else:
      Log.info(self.LOG_TAG, "No recent projects found; starting with empty state.")
      self._refresh_all()
      self._refresh_aliases_ui()
      self._set_tx_controls_enabled(False)

    self._startup_splash_set("Ready.")
    self._startup_splash_done()
    Log.ok(self.LOG_TAG, "Ready.", {"recent_projects": len(self.recent_project_dirs)})

  def _startup_splash_build(self) -> None:
    overlay_bg = "#1f1f1f"
    self._startup_splash_active = True
    self._startup_splash_raise_job = None
    self._startup_splash_w = 620
    self._startup_splash_h = 380

    self._startup_splash_window = tk.Toplevel(self)
    try:
      self._startup_splash_window.withdraw()
    except Exception:
      pass
    try:
      self._startup_splash_window.overrideredirect(True)
    except Exception:
      pass
    try:
      self._startup_splash_window.attributes("-topmost", True)
    except Exception:
      pass
    try:
      self._startup_splash_window.configure(bg=overlay_bg)
    except Exception:
      pass
    try:
      self._startup_splash_window.resizable(False, False)
    except Exception:
      pass

    self._startup_splash_recenter()

    self._startup_splash_frame = ctk.CTkFrame(self._startup_splash_window, fg_color=overlay_bg, corner_radius=0)
    self._startup_splash_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

    self._startup_splash_center = ctk.CTkFrame(self._startup_splash_frame, fg_color="transparent", corner_radius=0)
    self._startup_splash_center.place(relx=0.5, rely=0.5, anchor="center")

    self._startup_splash_logo = None
    self._startup_splash_logo_ref = (
      _load_splash_icon_tk_image(APP_SPLASH_ICON_PNG_PATH, max_size_px=180)
      or _load_splash_icon_tk_image(APP_ICON_PNG_PATH, max_size_px=180)
    )

    if self._startup_splash_logo_ref is not None:
      self._startup_splash_logo = tk.Label(
        self._startup_splash_center,
        image=self._startup_splash_logo_ref,
        bd=0,
        highlightthickness=0,
      )
      try:
        self._startup_splash_logo.configure(bg=overlay_bg)
      except Exception:
        pass
      self._startup_splash_logo.pack(pady=(0, 10))

    self._startup_splash_title = ctk.CTkLabel(
      self._startup_splash_center,
      text=APP_TITLE,
      font=("Segoe UI", 20, "bold"),
    )
    self._startup_splash_title.pack(pady=(0, 6))

    self._startup_splash_status = ctk.CTkLabel(
      self._startup_splash_center,
      text="Starting...",
      font=("Segoe UI", 12),
    )
    self._startup_splash_status.pack(pady=(0, 14))

    self._startup_splash_bar = ctk.CTkProgressBar(
      self._startup_splash_center,
      mode="indeterminate",
    )
    self._startup_splash_bar.pack(padx=30, fill="x")
    self._startup_splash_bar.start()

    try:
      self._startup_splash_window.deiconify()
      self._startup_splash_window.lift()
      self.update_idletasks()
      self.update()
    except Exception:
      pass

    self._startup_splash_raise_start()

  def _startup_splash_recenter(self) -> None:
    try:
      wnd = getattr(self, "_startup_splash_window", None)
      if wnd is None:
        return

      w = int(getattr(self, "_startup_splash_w", 620) or 620)
      h = int(getattr(self, "_startup_splash_h", 380) or 380)

      self.update_idletasks()
      x = int(self.winfo_rootx()) + max((int(self.winfo_width()) - w) // 2, 0)
      y = int(self.winfo_rooty()) + max((int(self.winfo_height()) - h) // 2, 0)

      if int(self.winfo_width()) <= 1 or int(self.winfo_height()) <= 1:
        x = max((self.winfo_screenwidth() - w) // 2, 0)
        y = max((self.winfo_screenheight() - h) // 2, 0)

      wnd.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
      pass

  def _startup_splash_raise_start(self) -> None:
    try:
      self._startup_splash_raise_stop()
      self._startup_splash_raise_job = self.after(33, self._startup_splash_raise_tick)
    except Exception:
      self._startup_splash_raise_job = None

  def _startup_splash_raise_stop(self) -> None:
    try:
      job = getattr(self, "_startup_splash_raise_job", None)
      if job is not None:
        self.after_cancel(job)
    except Exception:
      pass
    self._startup_splash_raise_job = None

  def _startup_splash_raise_tick(self) -> None:
    try:
      if not bool(getattr(self, "_startup_splash_active", False)):
        self._startup_splash_raise_job = None
        return
      frame = getattr(self, "_startup_splash_frame", None)
      wnd = getattr(self, "_startup_splash_window", None)
      if frame is None or wnd is None:
        self._startup_splash_raise_job = None
        return
      self._startup_splash_recenter()
      wnd.lift()
      try:
        wnd.attributes("-topmost", True)
      except Exception:
        pass
      self._startup_splash_raise_job = self.after(33, self._startup_splash_raise_tick)
    except Exception:
      self._startup_splash_raise_job = None

  def _startup_splash_set(self, text: str) -> None:
    try:
      if getattr(self, "_startup_splash_status", None) is not None:
        self._startup_splash_status.configure(text=str(text or "Loading..."))
      wnd = getattr(self, "_startup_splash_window", None)
      if wnd is not None:
        self._startup_splash_recenter()
        wnd.lift()
        try:
          wnd.attributes("-topmost", True)
        except Exception:
          pass
      self.update_idletasks()
      self.update()
    except Exception:
      pass

  def _startup_splash_done(self) -> None:
    self._startup_splash_active = False
    self._startup_splash_raise_stop()

    try:
      if getattr(self, "_startup_splash_bar", None) is not None:
        self._startup_splash_bar.stop()
    except Exception:
      pass

    try:
      frame = getattr(self, "_startup_splash_frame", None)
      if frame is not None:
        frame.place_forget()
        frame.destroy()
    except Exception:
      pass

    try:
      wnd = getattr(self, "_startup_splash_window", None)
      if wnd is not None:
        wnd.destroy()
    except Exception:
      pass

    self._startup_splash_window = None
    self._startup_splash_frame = None
    self._startup_splash_center = None
    self._startup_splash_logo = None
    self._startup_splash_logo_ref = None
    self._startup_splash_title = None
    self._startup_splash_status = None
    self._startup_splash_bar = None

  # -----------------------------------------------------------------------------
  # App config persistence (recent projects)
  # -----------------------------------------------------------------------------

  def _persist_app_config(self) -> None:
    Log.info(self.LOG_TAG, "Persisting app config.", {
      "config_path": APP_CONFIG_PATH,
      "recent_projects": len(self.recent_project_dirs),
    })
    _write_json_atomic(APP_CONFIG_PATH, {
      "recent_project_dirs_max": int(self.recent_project_dirs_max),
      "recent_project_dirs": list(self.recent_project_dirs),
    })

  def _refresh_project_dropdown(self) -> None:
    self.project_combo.configure(values=list(self.recent_project_dirs))

  def _remember_project_dir(self, p: str) -> None:
    if not p:
      Log.warn(self.LOG_TAG, "Skip remember project directory: empty input.")
      return
    p_norm = _norm_dir(p)
    if not os.path.isdir(p_norm):
      Log.warn(self.LOG_TAG, "Skip remember project directory: path is not a directory.", {"project_dir": p_norm})
      return

    items = [p_norm] + [x for x in self.recent_project_dirs if x != p_norm]
    items = _dedupe_keep_order(items)
    items = _filter_existing_dirs(items)
    items = items[: self.recent_project_dirs_max]
    self.recent_project_dirs = items

    self._persist_app_config()
    self._refresh_project_dropdown()
    Log.info(self.LOG_TAG, "Updated recent project directories.", {
      "selected": p_norm,
      "recent_projects": len(self.recent_project_dirs),
    })

  def _clear_project_history(self) -> None:
    Log.warn(self.LOG_TAG, "Clearing recent project directory history.", {"before": len(self.recent_project_dirs)})
    self.recent_project_dirs = []
    self._persist_app_config()
    self._refresh_project_dropdown()

  # -----------------------------------------------------------------------------
  # Project data IO
  # -----------------------------------------------------------------------------

  def _project_data_file_for_dir(self, project_dir: str) -> str:
    return os.path.join(os.path.abspath(project_dir), PROJECT_DATA_FILENAME)

  def _rebuild_alias_map(self) -> None:
    """
    Rebuild the fast lookup map (sku -> alias name) from self.aliases_list.
    """
    m: Dict[str, str] = {}
    for item in (self.aliases_list or []):
      if not isinstance(item, dict):
        continue
      sku = str(item.get("sku") or "").strip()
      name = str(item.get("name") or "").strip()
      if not sku or not name:
        continue
      m[sku] = name
    self._alias_map = m

  def _get_alias_for_sku(self, sku: str) -> str:
    s = (sku or "").strip()
    if not s:
      return ""
    return str(self._alias_map.get(s) or "").strip()

  def _normalize_custom_type(self, raw: Any) -> str:
    t = str(raw or "").strip().lower()
    if t in CUSTOM_FIELD_TYPES:
      return t
    return CUSTOM_TYPE_STRING

  def _normalize_custom_target(self, raw: Any) -> str:
    t = str(raw or "").strip().lower()
    if t in CUSTOM_FIELD_TARGETS:
      return t
    return CUSTOM_TARGET_ALIAS

  def _normalize_enum_values(self, raw: Any) -> List[str]:
    seq = raw if isinstance(raw, list) else [raw]
    out: List[str] = []
    seen = set()
    for item in seq:
      val = str(item or "").strip()
      if not val or val in seen:
        continue
      seen.add(val)
      out.append(val)
    return out

  def _normalize_custom_schema_entries(self, raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
      return []
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in raw:
      if not isinstance(item, dict):
        continue
      key = str(item.get("key") or "").strip()
      if not key:
        continue
      key_norm = key.lower()
      if key_norm in seen:
        continue
      seen.add(key_norm)
      dtype = self._normalize_custom_type(item.get("type"))
      entry = {
        "key": key,
        "target": self._normalize_custom_target(item.get("target")),
        "type": dtype,
        "description": str(item.get("description") or "").strip(),
        "enum": self._normalize_enum_values(item.get("enum", [])) if dtype == CUSTOM_TYPE_ENUM else [],
      }
      out.append(entry)
    return out

  def _normalize_entity_custom_values(self, raw: Any, schema: List[Dict[str, Any]], *, target: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
      return {}
    schema_map = {
      str(x.get("key") or "").strip(): x
      for x in (schema or [])
      if str(x.get("key") or "").strip() and self._normalize_custom_target(x.get("target")) == target
    }
    out: Dict[str, Any] = {}
    for key, val in raw.items():
      key_s = str(key or "").strip()
      if not key_s or key_s not in schema_map:
        continue
      coerced = self._coerce_custom_field_value(schema_map[key_s], val, raise_on_error=False)
      if coerced is not None:
        out[key_s] = coerced
    return out

  def _normalize_field_overrides(self, raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
      return {}
    builtin_map = {str(x.get("id") or ""): dict(x) for x in BUILTIN_FIELD_DEFS if str(x.get("id") or "")}
    out: Dict[str, Dict[str, Any]] = {}
    for field_id, item in raw.items():
      field_id_s = str(field_id or "").strip()
      if not field_id_s or field_id_s not in builtin_map or not isinstance(item, dict):
        continue
      base = builtin_map[field_id_s]
      enabled = bool(item.get("enabled", base.get("enabled", True)))
      if not bool(base.get("removable")):
        enabled = True
      out[field_id_s] = {"enabled": enabled}
    return out

  def _load_project_data_from_file(self, path: str) -> Tuple[List[Transaction], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    if not os.path.exists(path):
      Log.info(self.LOG_TAG, "Project data file does not exist yet; using empty defaults.", {"path": path})
      return [], [], [], {}
    Log.info(self.LOG_TAG, "Loading project data file.", {"path": path})
    with open(path, "r", encoding="utf-8") as f:
      raw = json.load(f)

    schema = self._normalize_custom_schema_entries(raw.get("custom_fields_schema", []))
    field_overrides = self._normalize_field_overrides(raw.get("field_overrides", {}))
    legacy_alias_values_by_sku = raw.get("custom_field_values", {})

    txs: List[Transaction] = []
    for item in raw.get("transactions", []):
      if not isinstance(item, dict):
        continue
      item2 = dict(item)
      item2["custom_fields"] = self._normalize_entity_custom_values(item2.get("custom_fields", {}), schema, target=CUSTOM_TARGET_TRANSACTION)
      txs.append(Transaction(**item2))

    aliases: List[Dict[str, Any]] = []
    raw_aliases = raw.get("aliases", [])
    if isinstance(raw_aliases, dict):
      # Legacy-ish fallback: {"SKU":"Name", ...}
      for k, v in raw_aliases.items():
        sku = str(k or "").strip()
        name = str(v or "").strip()
        if sku and name:
          aliases.append({"sku": sku, "name": name, "custom_fields": {}})
    elif isinstance(raw_aliases, list):
      for a in raw_aliases:
        if not isinstance(a, dict):
          continue
        sku = str(a.get("sku") or "").strip()
        name = str(a.get("name") or "").strip()
        if sku and name:
          custom_fields = self._normalize_entity_custom_values(a.get("custom_fields", {}), schema, target=CUSTOM_TARGET_ALIAS)
          if not custom_fields and isinstance(legacy_alias_values_by_sku, dict):
            custom_fields = self._normalize_entity_custom_values(legacy_alias_values_by_sku.get(sku, {}), schema, target=CUSTOM_TARGET_ALIAS)
          aliases.append({"sku": sku, "name": name, "custom_fields": custom_fields})

    aliases.sort(key=lambda x: (str(x.get("name", "")).lower(), str(x.get("sku", "")).lower()))
    Log.info(self.LOG_TAG, "Loaded project data file.", {
      "path": path,
      "tx_count": len(txs),
      "alias_count": len(aliases),
      "custom_field_count": len(schema),
      "field_override_count": len(field_overrides),
    })
    return txs, aliases, schema, field_overrides

  def _save_project_data_to_file(
    self,
    path: str,
    txs: List[Transaction],
    aliases: List[Dict[str, Any]],
    custom_schema: List[Dict[str, Any]],
    field_overrides: Dict[str, Dict[str, Any]],
  ) -> None:
    Log.info(self.LOG_TAG, "Saving project data file.", {
      "path": path,
      "tx_count": len(txs or []),
      "alias_count": len(aliases or []),
      "custom_field_count": len(custom_schema or []),
      "field_override_count": len(field_overrides or {}),
    })
    payload = {
      "transactions": [asdict(t) for t in txs],
      "aliases": list(aliases or []),
      "custom_fields_schema": list(custom_schema or []),
      "field_overrides": dict(field_overrides or {}),
    }
    _write_json_atomic(path, payload)

  def _load_project_dir(self, project_dir: str) -> None:
    p = os.path.abspath(project_dir)
    Log.info(self.LOG_TAG, "Loading project directory.", {"project_dir": p})
    if not os.path.isdir(p):
      Log.error(self.LOG_TAG, "Project directory is missing or invalid.", {"project_dir": p})
      messagebox.showerror("Project", "Project directory is missing or invalid.")
      return

    self.project_dir = p
    self.project_data_path = self._project_data_file_for_dir(p)
    try:
      txs, aliases, custom_schema, field_overrides = self._load_project_data_from_file(self.project_data_path)
    except Exception as e:
      Log.error(self.LOG_TAG, "Failed to load project data.", {"project_dir": p, "data_path": self.project_data_path, "error": str(e)})
      messagebox.showerror("Project Load Failed", str(e))
      self._set_tx_controls_enabled(False)
      return

    self.transactions = txs
    self._normalize_sort()

    self.aliases_list = aliases
    self._rebuild_alias_map()
    self.custom_fields_schema = custom_schema
    self.field_overrides = field_overrides
    self._rebuild_custom_field_schema_map()

    self.next_id = (max([t.id for t in self.transactions], default=0) + 1)
    self.next_created_order = (max([t.created_order for t in self.transactions], default=0) + 1)

    self._remember_project_dir(p)
    self._set_tx_controls_enabled(True)

    self._refresh_aliases_ui()
    self._refresh_custom_schema_ui()
    self._configure_overview_tree_for_view()
    self._refresh_all()

    Log.ok(self.LOG_TAG, "Loaded project.", {
      "project_dir": p,
      "tx_count": len(self.transactions),
      "alias_count": len(self.aliases_list),
      "custom_field_count": len(self.custom_fields_schema),
    })

  def _save_and_refresh(self, *, schema_changed: bool = False) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Cannot save: no project data path selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    Log.info(self.LOG_TAG, "Saving and refreshing UI state.", {
      "project_data_path": self.project_data_path,
      "schema_changed": bool(schema_changed),
      "tx_count": len(self.transactions),
      "alias_count": len(self.aliases_list),
      "custom_field_count": len(self.custom_fields_schema),
    })
    self._normalize_sort()
    self._save_project_data_to_file(
      self.project_data_path,
      self.transactions,
      self.aliases_list,
      self.custom_fields_schema,
      self.field_overrides,
    )
    self._refresh_aliases_ui()
    if schema_changed:
      self._refresh_custom_schema_ui()
      self._configure_overview_tree_for_view()
    else:
      self._update_tx_custom_fields_editor_values(next((t for t in self.transactions if t.id == self._get_selected_tx_id()), None))
      self._update_alias_custom_fields_editor_values(
        next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == str(self._get_selected_alias_sku() or "").strip()), None)
      )
    self._refresh_all()
    Log.ok(self.LOG_TAG, "Save + refresh complete.", {"schema_changed": bool(schema_changed)})

  # -----------------------------------------------------------------------------
  # UI Construction
  # -----------------------------------------------------------------------------

  # =============================================================================
  # Tooltips
  # =============================================================================


  def _install_tab_button_tooltips(self) -> None:
    """Attach tooltips to CTkTabview tab buttons (segmented button)."""
    try:
      tabview = getattr(self, "tabs", None)
      if tabview is None:
        return

      seg = getattr(tabview, "_segmented_button", None)
      if seg is None:
        return

      btn_map = None
      for attr in ("_buttons_dict", "_buttons", "buttons"):
        v = getattr(seg, attr, None)
        if isinstance(v, dict):
          btn_map = v
          break

      if not isinstance(btn_map, dict):
        return

      tip_by_tab = {
        "Transactions": "Transactions: add/update/delete purchases & sales. This drives costing and the overview.",
        "Overview": "Overview: current inventory state (on-hand qty, WAC, totals) and optional summaries.",
        "Aliases": "Aliases: map friendly names to SKUs. Used in dropdowns and tables.",
        "Custom Fields": "Custom Fields: manage project custom fields plus built-in column visibility rules.",
      }

      for tab_name, tip in tip_by_tab.items():
        btn = btn_map.get(tab_name)
        if btn is not None:
          tooltip(btn, text=tip)
    except Exception:
      pass


  def _install_tooltips_explicit(self) -> None:
    """Attach curated tooltips to key UI widgets we store on `self`.

    Also ensures labels get the same tooltip as their associated value widgets.
    """
    def _attach(w: Any, msg: str) -> None:
      if w is None:
        return
      try:
        tooltip(w, text=msg)
      except Exception:
        pass

      # If this widget has an associated label, apply the SAME tooltip to the label too.
      try:
        lbl = self._tooltip_associated_label_widget(w)
        if lbl is not None:
          tooltip(lbl, text=msg)
      except Exception:
        pass

    try:
      _attach(self.tabs, "Tabs: switch between Transactions, Overview, Aliases, and Custom Fields.")
    except Exception:
      pass

    try:
      self._install_tab_button_tooltips()
    except Exception:
      pass

    # Project bar (label + combo + buttons)
    _attach(getattr(self, "project_combo", None),
            "Project Directory: choose or type a project folder. Data saves to <ProjectDir>/inventory_data.json.")

    _attach(getattr(self, "btn_browse_project", None),
            "Browse: pick a project folder. Data file is created/used at <ProjectDir>/inventory_data.json.")

    _attach(getattr(self, "btn_load_project", None),
            "Load/Refresh: load the selected project folder and refresh all tables from <ProjectDir>/inventory_data.json.")

    _attach(getattr(self, "btn_clear_history", None),
            "Clear History: remove recent project folders from the dropdown (does NOT delete any project data files).")

    # Transactions form (labels will inherit via _attach)
    for w, msg in [
      (getattr(self, "entry_date", None), "Date: transaction date (YYYY-MM-DD or M/D/YYYY)."),
      (getattr(self, "btn_date_pick", None), "Pick Date: open a calendar selector to set the Date field."),
      (getattr(self, "entry_sku", None), "SKU: item identifier used for costing/aggregation."),

      (getattr(self, "lbl_tx_alias", None), "Alias: type to filter by alias name OR SKU; selecting an alias sets the SKU field."),
      (getattr(self, "entry_alias", None), "Alias: type to filter by alias name OR SKU; selecting an alias sets the SKU field."),
      (getattr(self, "btn_alias_drop", None), "Alias dropdown: show all aliases; typing filters by alias name OR SKU."),

      (getattr(self, "opt_type", None), "Type: Purchase increases inventory; Sale reduces inventory."),
      (getattr(self, "entry_qty", None), "Qty: number of units bought/sold."),
      (getattr(self, "entry_unit_price", None), "Unit Price: purchase cost per unit (for Purchase) or sale price per unit (for Sale)."),
      (getattr(self, "entry_note", None), "Note: optional text for receipts, customer, order, etc."),
      (getattr(self, "btn_add", None), "Add: append a new transaction row. (Enter)"),
      (getattr(self, "btn_update", None), "Update Selected: edit the selected transaction row. Enabled only when exactly one row is selected."),

      (getattr(self, "btn_delete", None), "Delete: remove the selected transaction row."),
      (getattr(self, "btn_export", None), "Export: write transactions to a CSV file for sharing/backup."),
      (getattr(self, "tx_tree", None), "Transactions table: hover cells for exact values; click rows to select."),
    ]:
      _attach(w, msg)

    # Overview tab
    for w, msg in [
      (getattr(self, "opt_ov_view", None), "Overview mode: choose summary view/grouping."),
      (getattr(self, "ov_tree", None), "Overview table: current on-hand, WAC, and totals per SKU/alias."),
      (getattr(self, "btn_ov_export", None), "Export Overview: save the current overview table."),
    ]:
      _attach(w, msg)

    # Aliases tab
    for w, msg in [
      (getattr(self, "entry_alias_name", None), "Alias Name: friendly display name (e.g., 'NES Controller')."),
      (getattr(self, "entry_alias_sku", None), "Alias SKU: the SKU value this alias maps to."),
      (getattr(self, "btn_alias_add", None), "Add Alias: create a new alias mapping. (Enter)"),
      (getattr(self, "btn_alias_update", None), "Update Selected: edit the selected alias mapping. Enabled only when exactly one row is selected."),

      (getattr(self, "btn_alias_delete", None), "Delete Alias: remove the selected alias mapping."),
      (getattr(self, "alias_tree", None), "Aliases table: select an alias to edit or delete."),
    ]:
      _attach(w, msg)

    # Custom Fields tab
    for w, msg in [
      (getattr(self, "entry_custom_schema_key", None), "Field Name: the custom column name used on the selected target."),
      (getattr(self, "opt_custom_schema_target", None), "Target: choose whether this field belongs to transactions or aliases."),
      (getattr(self, "opt_custom_schema_type", None), "Field Type: choose string, number, boolean, or enum."),
      (getattr(self, "btn_custom_enum_edit", None), "Edit Enum Values: open a popup to add, remove, confirm, or reject allowed enum values."),
      (getattr(self, "lbl_custom_enum_summary", None), "Enum Summary: preview of the currently configured allowed enum values."),
      (getattr(self, "entry_custom_schema_description", None), "Description: optional tooltip text shown on the generated custom field label and input."),
      (getattr(self, "btn_custom_schema_add", None), "Add Field: create a new custom field definition."),
      (getattr(self, "btn_custom_schema_update", None), "Update Selected: edit the selected custom field definition."),
      (getattr(self, "btn_custom_schema_delete", None), "Delete Selected: remove the selected custom field definition and its saved values."),
      (getattr(self, "btn_custom_schema_up", None), "Move Up: shift the selected custom field earlier in display order."),
      (getattr(self, "btn_custom_schema_down", None), "Move Down: shift the selected custom field later in display order."),
      (getattr(self, "custom_schema_tree", None), "Custom Fields table: built-in field visibility plus target-specific custom schema definitions."),
    ]:
      _attach(w, msg)


  def _tooltip_associated_label_widget(self, w: Any) -> Any:
    """Find the likely label widget associated with a widget by examining grid siblings.

    This targets the common pattern:
      Label @ (row=r, col=0) + Widget @ (row=r, col=1)

    Returns:
      The label widget if found; otherwise None.
    """
    try:
      info = w.grid_info() or {}
    except Exception:
      return None

    try:
      row = int(info.get("row"))
      col = int(info.get("column"))
    except Exception:
      return None

    parent = getattr(w, "master", None)
    if parent is None:
      return None

    candidate_cols = [max(col - 1, 0), 0]

    try:
      siblings = parent.winfo_children()
    except Exception:
      return None

    for ccol in candidate_cols:
      for sib in siblings:
        if sib is w:
          continue
        try:
          sinfo = sib.grid_info() or {}
          srow = int(sinfo.get("row"))
          scol = int(sinfo.get("column"))
        except Exception:
          continue
        if srow != row or scol != ccol:
          continue

        try:
          cls = sib.__class__.__name__
        except Exception:
          cls = ""
        if "Label" not in cls:
          continue

        try:
          t = str(sib.cget("text") or "").strip()
        except Exception:
          t = ""
        if t:
          return sib

    return None


  def _tooltip_associated_label_text(self, w: Any) -> str:
    """Try to infer a label text for a widget by examining its grid siblings."""
    lbl = self._tooltip_associated_label_widget(w)
    if lbl is None:
      return ""
    try:
      return str(lbl.cget("text") or "").strip()
    except Exception:
      return ""


  def _tooltip_text_for_widget(self, w: Any) -> str:
    """Infer a human-friendly tooltip string for a widget.

    Rules:
    - Only attach tooltips to interactive or informative widgets.
    - NEVER attach tooltips to container widgets (frames), or fall back to class names.
    - Labels do not get auto-tooltips; they inherit tooltips from their paired value widgets.
    """
    if w is None:
      return ""

    try:
      cls = w.__class__.__name__
    except Exception:
      cls = ""

    # -------------------------------------------------------------------------
    # Skip non-interactive containers / structural widgets
    # -------------------------------------------------------------------------
    # NOTE: This prevents "CTkFrame" and similar nonsense tooltips.
    skip_class_fragments = (
      "Frame",
      "Canvas",
      "Separator",
      "Scrollbar",
      "Toplevel",
    )
    if any(frag in cls for frag in skip_class_fragments):
      return ""

    # Labels: only get tooltips when mirrored from their value widgets.
    if "Label" in cls:
      return ""

    # -------------------------------------------------------------------------
    # Explicit widget text (buttons, tab buttons, etc.)
    # -------------------------------------------------------------------------
    for key in ("text", "placeholder_text"):
      try:
        t = str(w.cget(key) or "").strip()
      except Exception:
        t = ""
      if t:
        return t

    # -------------------------------------------------------------------------
    # Special-case: ttk.Treeview
    # -------------------------------------------------------------------------
    try:
      import tkinter.ttk as _ttk  # local import to avoid global cycles
      if isinstance(w, _ttk.Treeview):
        return "Table: hover headers for help; hover cells for exact values."
    except Exception:
      pass

    # -------------------------------------------------------------------------
    # Infer from sibling label (entries, comboboxes, option menus, etc.)
    # -------------------------------------------------------------------------
    label = self._tooltip_associated_label_text(w)
    if label:
      if "Entry" in cls:
        return f"Set {label}"
      if "ComboBox" in cls or "OptionMenu" in cls:
        return f"Select {label}"
      if "Slider" in cls:
        return f"Adjust {label}"
      if "Switch" in cls or "CheckBox" in cls or "RadioButton" in cls:
        return f"Toggle {label}"
      return label

    # No fallback. If we can’t infer something useful, skip tooltip entirely.
    return ""


  def _install_tooltips_recursive(self, root: Any) -> None:
    """Attach tooltips to every widget in the subtree rooted at `root`.

    Notes:
    - Best-effort and never throws.
    - Tooltips are only attached once per widget (`_cure_tooltip` guard).
    - IMPORTANT: never attach a tooltip to the app root window (`self`) because CTkToolTip can
      surface that tooltip while hovering child widgets (shows as "InventoryApp" over everything).
    """
    if CTkToolTip is None:
      return

    stack = [root]
    while stack:
      w = stack.pop()

      # Never tooltip the app/root window.
      if w is self:
        # If an old root tooltip exists (from a previous run), remove it.
        old = getattr(w, "_cure_tooltip", None)
        if old is not None:
          try:
            if hasattr(old, "hide"):
              old.hide()
          except Exception:
            pass
          try:
            if hasattr(old, "destroy"):
              old.destroy()
          except Exception:
            pass
          try:
            w._cure_tooltip = None  # type: ignore[attr-defined]
          except Exception:
            pass

        # Still recurse into children.
        try:
          stack.extend(list(w.winfo_children()))
        except Exception:
          pass
        continue

      # Skip if we've already attached a tooltip here.
      if getattr(w, "_cure_tooltip", None) is None:
        try:
          msg = self._tooltip_text_for_widget(w)
          if msg:
            tooltip(w, text=msg)

            # Mirror value widget tooltip to its label (labels do not get auto-tooltips)
            try:
              cls = w.__class__.__name__
            except Exception:
              cls = ""

            if any(k in cls for k in ("Entry", "ComboBox", "OptionMenu", "Slider", "Switch", "CheckBox", "RadioButton")):
              lbl = self._tooltip_associated_label_widget(w)
              if lbl is not None:
                tooltip(lbl, text=msg)
        except Exception:
          pass

      try:
        stack.extend(list(w.winfo_children()))
      except Exception:
        pass


  def _build_ui(self) -> None:

    self.grid_rowconfigure(1, weight=1)
    self.grid_columnconfigure(0, weight=1)

    # Top project bar (like your attached script)
    project_bar = ctk.CTkFrame(self)
    project_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
    project_bar.grid_columnconfigure(1, weight=1)

    self.lbl_project_dir = ctk.CTkLabel(project_bar, text="Project Directory:")
    self.lbl_project_dir.grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")

    self.project_dir_var = tk.StringVar(value=(self.recent_project_dirs[0] if self.recent_project_dirs else ""))
    self.project_combo = ctk.CTkComboBox(
      project_bar,
      variable=self.project_dir_var,
      values=list(self.recent_project_dirs),
      state="normal",
      command=lambda _choice: self._on_project_combo_selected(),
    )
    self.project_combo.grid(row=0, column=1, padx=6, pady=10, sticky="ew")

    self.btn_browse_project = ctk.CTkButton(project_bar, text="Browse…", width=110, command=self._on_browse_project)
    self.btn_browse_project.grid(row=0, column=2, padx=6, pady=10)

    self.btn_load_project = ctk.CTkButton(project_bar, text="Load/Refresh", width=130, command=self._on_load_project)
    self.btn_load_project.grid(row=0, column=3, padx=6, pady=10)

    self.btn_clear_history = ctk.CTkButton(project_bar, text="Clear History", width=120, command=self._on_clear_history)
    self.btn_clear_history.grid(row=0, column=4, padx=(6, 10), pady=10)

    # Tabs
    self.tabs = ctk.CTkTabview(self)
    self.tabs.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))

    self.tab_tx = self.tabs.add("Transactions")
    self.tab_ov = self.tabs.add("Overview")
    self.tab_alias = self.tabs.add("Aliases")
    self.tab_custom = self.tabs.add("Custom Fields")

    self._build_transactions_tab()
    self._build_overview_tab()
    self._build_aliases_tab()
    self._build_custom_fields_tab()
    # Tooltips (best-effort): attach curated tips first, then fill in the rest.
    self._install_tooltips_explicit()
    # IMPORTANT: Do NOT recurse from the app root; it creates a root-level tooltip ("InventoryApp")
    # that can appear over child widgets. Recurse from the tab container instead.
    self._install_tooltips_recursive(self.tabs)

  def _build_transactions_tab(self) -> None:
    # Row 0: inputs. Row 1: note + action buttons + custom fields. Row 2: table.
    self.tab_tx.grid_rowconfigure(0, weight=0)
    self.tab_tx.grid_rowconfigure(1, weight=0)
    self.tab_tx.grid_rowconfigure(2, weight=1)
    self.tab_tx.grid_columnconfigure(0, weight=1)

    # Split into two independent grids so the dynamic unit label never reflows the buttons.
    form_row = ctk.CTkFrame(self.tab_tx)
    form_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

    action_row = ctk.CTkFrame(self.tab_tx)
    action_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
    action_row.grid_columnconfigure(1, weight=1)

    self.var_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
    self.var_sku = tk.StringVar(value="")
    self.var_type = tk.StringVar(value=TX_PURCHASE)
    self.var_qty = tk.StringVar(value="1")
    self.var_purchase_unit = tk.StringVar(value="1.00")
    self.var_sale_unit = tk.StringVar(value="3.00")

    # Alias chooser (display-only selection; selecting sets SKU)
    self.var_alias_choice = tk.StringVar(value="")

    # Single "unit" field that swaps meaning based on Type.
    self.var_unit_price = tk.StringVar(value=self.var_purchase_unit.get())
    self._last_type_for_unit = self.var_type.get()

    self.var_note = tk.StringVar(value="")

    # Keep Alias dropdown synced when SKU typed
    try:
      self.var_sku.trace_add("write", lambda *_: self._sync_alias_choice_from_sku())
    except Exception:
      pass

    ctk.CTkLabel(form_row, text="Date").grid(row=0, column=0, padx=(10, 6), pady=10)

    # Date picker (entry + calendar button)
    self.date_picker = ctk.CTkFrame(form_row, fg_color="transparent")
    self.date_picker.grid(row=0, column=1, padx=6, pady=10, sticky="w")

    self.entry_date = ctk.CTkEntry(self.date_picker, textvariable=self.var_date, width=120)
    self.entry_date.grid(row=0, column=0)
    apply_entry_shortcuts(self.entry_date)

    self.btn_date_pick = ctk.CTkButton(self.date_picker, text="📅", width=32, command=self._on_pick_date)
    self.btn_date_pick.grid(row=0, column=1, padx=(6, 0))

    # -------------------------------------------------------------------------
    # In-window Date dropdown (themed overlay; no separate popup window)
    # -------------------------------------------------------------------------

    # Overlay dropdown (parent is Transactions tab so it can overlay tab contents)
    self._date_dropdown = ctk.CTkFrame(self.tab_tx, corner_radius=10, border_width=1)
    self._date_dropdown.place_forget()
    self._date_dropdown_visible = False

    # Theme colors (match CTk dark mode)
    _date_bg       = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
    _date_bg_alt   = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
    _date_fg       = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])
    _date_accent   = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["fg_color"])
    _date_accent_h = _ctk_color(ctk.ThemeManager.theme["CTkButton"]["hover_color"])

    # Calendar is a Tk widget; we host it inside a Tk frame so bg matches cleanly.
    self._date_cal_host = tk.Frame(self._date_dropdown, bg=_date_bg)
    self._date_cal_host.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))

    # Buttons row (CTk)
    self._date_btn_row = ctk.CTkFrame(self._date_dropdown, fg_color="transparent")
    self._date_btn_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
    self._date_btn_row.grid_columnconfigure(0, weight=1)
    self._date_btn_row.grid_columnconfigure(1, weight=1)
    self._date_btn_row.grid_columnconfigure(2, weight=1)

    self._date_btn_today  = ctk.CTkButton(self._date_btn_row, text="Today",  width=90)
    self._date_btn_ok     = ctk.CTkButton(self._date_btn_row, text="OK",     width=90)
    self._date_btn_cancel = ctk.CTkButton(self._date_btn_row, text="Cancel", width=90)

    self._date_btn_today.grid(row=0, column=0, padx=(0, 8), sticky="ew")
    self._date_btn_ok.grid(row=0, column=1, padx=8, sticky="ew")
    self._date_btn_cancel.grid(row=0, column=2, padx=(8, 0), sticky="ew")

    # We create/destroy Calendar instance as needed (tkcalendar can be optional).
    self._date_cal = None

    _date_state = {"after_id": None}

    def _date_is_descendant(widget: Any, parent: Any) -> bool:
      try:
        w = widget
        while w is not None:
          if w == parent:
            return True
          w = getattr(w, "master", None)
      except Exception:
        pass
      return False

    def _date_dropdown_hide() -> None:
      if not getattr(self, "_date_dropdown_visible", False):
        return
      try:
        self._date_dropdown.place_forget()
      except Exception:
        pass
      self._date_dropdown_visible = False

    def _date_dropdown_place_near_entry(*, prefer_below: bool = True) -> None:
      """
      Place dropdown near the date picker, clamped inside the Transactions tab.
      Tries below first; if not enough space, flips above.
      """
      try:
        self.update_idletasks()

        # Entry screen coords
        ex = int(self.entry_date.winfo_rootx())
        ey = int(self.entry_date.winfo_rooty())
        eh = int(self.entry_date.winfo_height())

        # Tab screen coords
        tx = int(self.tab_tx.winfo_rootx())
        ty = int(self.tab_tx.winfo_rooty())
        tw = int(self.tab_tx.winfo_width() or 0)
        th = int(self.tab_tx.winfo_height() or 0)

        # Convert to coords relative to tab
        x = ex - tx
        y_below = (ey - ty) + eh
        y_above = (ey - ty)

        # Width matches the picker (entry+button)
        w_drop = int(self.date_picker.winfo_width() or 0)
        if w_drop <= 10:
          w_drop = 320

        try:
          self._date_dropdown.configure(width=w_drop)
        except Exception:
          pass

        # Measure content height
        self._date_dropdown.update_idletasks()
        try:
          content_h = int(self._date_dropdown.winfo_reqheight() or 280)
        except Exception:
          content_h = 280

        # Available space
        below_space = max(th - y_below - 6, 0)
        above_space = max(y_above - 6, 0)

        use_below = prefer_below
        if use_below and below_space < content_h and above_space > below_space:
          use_below = False
        elif (not use_below) and above_space < content_h and below_space > above_space:
          use_below = True

        if use_below:
          y = max(0, y_below - 1)
        else:
          y = max(0, y_above - content_h - 1)

        # Clamp X inside tab
        if tw > 40:
          x = max(0, min(x, max(tw - w_drop - 6, 0)))

        self._date_dropdown.place(x=x, y=y)
        self._date_dropdown.lift()
        self._date_dropdown_visible = True
      except Exception:
        _date_dropdown_hide()

    def _date_calendar_rebuild(year: int, month: int, day: int) -> None:
      """
      (Re)create the tkcalendar Calendar inside the host, themed to CTk colors.
      """
      try:
        for child in self._date_cal_host.winfo_children():
          child.destroy()
      except Exception:
        pass

      from tkinter import font as tkfont

      # Match your table font sizes (Treeview uses 12/13 in apply_dark_ttk_treeview_style()).
      _cal_font = tkfont.nametofont("TkDefaultFont").copy()
      _cal_font.configure(size=13)

      _cal_headers_font = _cal_font.copy()
      _cal_headers_font.configure(size=14, weight="bold")

      self._date_cal = Calendar(
        self._date_cal_host,
        selectmode="day",
        year=int(year),
        month=int(month),
        day=int(day),
        date_pattern="yyyy-mm-dd",

        # ✅ Font sizing
        font=_cal_font,
        headersfont=_cal_headers_font,

        # Theme colors
        background=_date_bg,
        foreground=_date_fg,
        bordercolor=_date_bg,
        headersbackground=_date_bg_alt,
        headersforeground=_date_fg,
        selectbackground=_date_accent,
        selectforeground=_date_fg,
        normalbackground=_date_bg,
        normalforeground=_date_fg,
        weekendbackground=_date_bg,
        weekendforeground=_date_fg,
        othermonthbackground=_date_bg,
        othermonthforeground="#707070",
        othermonthwebackground=_date_bg,
        othermonthweforeground="#707070",
      )

      self._date_cal.pack(fill="both", expand=True)

    def _date_dropdown_show_from_current_entry() -> None:
      if Calendar is None:
        messagebox.showinfo(
          "Date Picker",
          "Calendar picker requires optional dependency:\n\n"
          "  pip install tkcalendar\n\n"
          "You can still type the date as YYYY-MM-DD or M/D/YYYY."
        )
        try:
          self.entry_date.focus_set()
        except Exception:
          pass
        return

      # Parse current date (best-effort)
      try:
        cur = parse_date(self.var_date.get())
        y = int(cur[0:4]); m = int(cur[5:7]); d = int(cur[8:10])
      except Exception:
        now = datetime.now()
        y, m, d = now.year, now.month, now.day

      _date_calendar_rebuild(y, m, d)
      _date_dropdown_place_near_entry(prefer_below=True)

    def _date_ok() -> None:
      picked = ""
      try:
        if self._date_cal is not None:
          picked = str(self._date_cal.get_date() or "").strip()
      except Exception:
        picked = ""

      if picked:
        try:
          self.var_date.set(parse_date(picked))
        except Exception:
          self.var_date.set(picked)

      _date_dropdown_hide()

      try:
        self.entry_date.focus_set()
        self.entry_date.icursor(tk.END)
      except Exception:
        pass

    def _date_today() -> None:
      try:
        if self._date_cal is not None:
          self._date_cal.selection_set(datetime.now().strftime("%Y-%m-%d"))
      except Exception:
        pass

    def _date_cancel() -> None:
      _date_dropdown_hide()
      try:
        self.entry_date.focus_set()
      except Exception:
        pass

    self._date_btn_today.configure(command=_date_today)
    self._date_btn_ok.configure(command=_date_ok)
    self._date_btn_cancel.configure(command=_date_cancel)

    def _date_toggle_dropdown() -> None:
      if getattr(self, "_date_dropdown_visible", False):
        _date_dropdown_hide()
      else:
        _date_dropdown_show_from_current_entry()

    # Store helpers for use elsewhere (like disable/enable)
    self._date_dropdown_hide = _date_dropdown_hide
    self._date_dropdown_toggle = _date_toggle_dropdown
    self._date_dropdown_show = _date_dropdown_show_from_current_entry

    # Esc closes date dropdown (when date entry focused)
    self.entry_date.bind("<Escape>", lambda _e: _date_dropdown_hide())

    # Clicking outside closes dropdown
    if not getattr(self, "_date_outside_click_bound", False):
      self._date_outside_click_bound = True

      def _on_any_click_close_date(e) -> None:
        try:
          w = e.widget

          # Inside date picker (entry + button) = keep open
          if _date_is_descendant(w, self.date_picker):
            return

          # Inside dropdown = keep open
          if _date_is_descendant(w, self._date_dropdown):
            return

          _date_dropdown_hide()
        except Exception:
          pass

      self.bind_all("<Button-1>", _on_any_click_close_date, add="+")

    ctk.CTkLabel(form_row, text="SKU").grid(row=0, column=2, padx=(14, 6), pady=10)
    self.entry_sku = ctk.CTkEntry(form_row, textvariable=self.var_sku, width=200)
    self.entry_sku.grid(row=0, column=3, padx=6, pady=10)
    apply_entry_shortcuts(self.entry_sku)

    self.lbl_tx_alias = ctk.CTkLabel(form_row, text="Alias")
    self.lbl_tx_alias.grid(row=0, column=4, padx=(14, 6), pady=10)

    # Alias picker (Entry + non-focus-stealing suggestion overlay)
    self.alias_picker = ctk.CTkFrame(form_row, fg_color="transparent")
    self.alias_picker.grid(row=0, column=5, padx=6, pady=10, sticky="w")
    self.alias_picker.grid_columnconfigure(0, weight=1)

    self.entry_alias = ctk.CTkEntry(self.alias_picker, textvariable=self.var_alias_choice, width=226)
    self.entry_alias.grid(row=0, column=0, sticky="ew")
    apply_entry_shortcuts(self.entry_alias)

    self.btn_alias_drop = ctk.CTkButton(self.alias_picker, text="▾", width=32)
    self.btn_alias_drop.grid(row=0, column=1, padx=(6, 0))

    # Cache of all alias display values (rebuilt by _refresh_alias_dropdown)
    self._alias_dropdown_values = [""] + self._build_alias_display_values()

    # Overlay dropdown (IMPORTANT: parent is the Transactions tab so it can overlay tab contents)
    self._alias_dropdown = ctk.CTkFrame(self.tab_tx, corner_radius=10, border_width=1)
    self._alias_dropdown.place_forget()
    self._alias_dropdown_visible = False

    # Height is set dynamically on each open/refresh based on available space + content size.
    self._alias_dropdown_scroll = ctk.CTkScrollableFrame(self._alias_dropdown, width=512, height=10)
    self._alias_dropdown_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

    # Runtime sizing cache
    self._alias_dropdown_content_px = 80

    _alias_filter_state = {"after_id": None}

    def _alias_is_descendant(widget: Any, parent: Any) -> bool:
      try:
        w = widget
        while w is not None:
          if w == parent:
            return True
          w = getattr(w, "master", None)
      except Exception:
        pass
      return False

    def _alias_dropdown_hide() -> None:
      if not getattr(self, "_alias_dropdown_visible", False):
        return
      try:
        self._alias_dropdown.place_forget()
      except Exception:
        pass
      self._alias_dropdown_visible = False

    def _alias_dropdown_place_below_entry() -> None:
      """
      Place dropdown directly under the alias entry, relative to the Transactions tab.
      This ensures the dropdown overlays tab contents (no "hidden under row" gap).
      """
      try:
        self.update_idletasks()

        # Screen coords (absolute)
        ex = int(self.entry_alias.winfo_rootx())
        ey = int(self.entry_alias.winfo_rooty())
        eh = int(self.entry_alias.winfo_height())

        # Convert to coords relative to the Transactions tab (self.tab_tx)
        tx = int(self.tab_tx.winfo_rootx())
        ty = int(self.tab_tx.winfo_rooty())

        x = ex - tx
        y = (ey - ty) + eh

        # Width matches the picker (entry + button)
        w_drop = int(self.alias_picker.winfo_width() or 0)
        if w_drop <= 10:
          w_drop = 512

        try:
          self._alias_dropdown.configure(width=w_drop)
        except Exception:
          pass

        # Tiny seam tweak (optional)
        y = max(0, y - 1)

        self._alias_dropdown.place(x=x, y=y)
        self._alias_dropdown.lift()  # now lifts above all tab content siblings
        self._alias_dropdown_visible = True
      except Exception:
        _alias_dropdown_hide()

    def _alias_dropdown_render(values: List[str]) -> None:
      try:
        for child in self._alias_dropdown_scroll.winfo_children():
          child.destroy()
      except Exception:
        pass

      shown = [v for v in values if v]  # ignore blank sentinel for UI
      if not shown:
        # Content wants to be small when empty.
        self._alias_dropdown_content_px = 64
        ctk.CTkLabel(self._alias_dropdown_scroll, text="No matches").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        return

      # Limit rendered rows for performance; scroll holds the rest if needed later.
      MAX_ROWS = 80
      shown = shown[:MAX_ROWS]

      def _pick(val: str) -> None:
        try:
          self.var_alias_choice.set(val)
        except Exception:
          pass

        _alias_dropdown_hide()

        # Commit selection behavior (sets SKU) but DO NOT move focus away.
        self._on_alias_selected_in_tx_form()

        # Put caret back in alias entry (move cursor to end)
        def _focus_alias_end() -> None:
          try:
            self.entry_alias.focus_set()
          except Exception:
            return

          # Best-effort: CTkEntry sometimes wraps the underlying tk.Entry as `_entry`
          try:
            self.entry_alias.icursor(tk.END)
            try:
              self.entry_alias.xview_moveto(1.0)  # ensure end is visible
            except Exception:
              pass
            return
          except Exception:
            pass

          try:
            inner = getattr(self.entry_alias, "_entry", None)
            if inner is not None:
              inner.icursor(tk.END)
              try:
                inner.xview_moveto(1.0)
              except Exception:
                pass
          except Exception:
            pass

        try:
          self.after(1, _focus_alias_end)
        except Exception:
          _focus_alias_end()

      for i, v in enumerate(shown):
        btn = ctk.CTkButton(
          self._alias_dropdown_scroll,
          text=v,
          anchor="w",
          height=26,
          fg_color="transparent",
          hover=True,
          command=lambda vv=v: _pick(vv),
        )
        btn.grid(row=i, column=0, sticky="ew", padx=2, pady=1)

      try:
        self._alias_dropdown_scroll.grid_columnconfigure(0, weight=1)
      except Exception:
        pass

    def _alias_apply_filter(show_if_any: bool = True) -> None:
      raw_in = (self.var_alias_choice.get() or "")
      q = raw_in.strip()

      all_values = list(getattr(self, "_alias_dropdown_values", None) or ([""] + self._build_alias_display_values()))
      only = [v for v in all_values if v]

      def _norm(s: str) -> str:
        # Lower, remove most punctuation, collapse whitespace.
        s2 = re.sub(r"[^a-zA-Z0-9]+", " ", str(s or "").lower())
        return re.sub(r"\s+", " ", s2).strip()

      qn = _norm(q)

      # EMPTY SEARCH => show ALL aliases
      if not qn:
        filtered = only
      else:
        q_tokens = [t for t in qn.split(" ") if t]

        filtered = []
        for disp in only:
          sku, name = self._parse_alias_display_value(disp)

          # Search space includes BOTH: alias name + sku
          hay = _norm(f"{name} {sku}")

          # All tokens must be present (order-independent)
          if all(t in hay for t in q_tokens):
            filtered.append(disp)

      _alias_dropdown_render(filtered)

      if show_if_any and (qn or filtered):
        _alias_dropdown_place_below_entry()
        # Do NOT touch focus/caret here — it breaks cursor position while typing/refocusing.
      else:
        _alias_dropdown_hide()

    def _alias_apply_filter_debounced(_event=None) -> None:
      if _alias_filter_state["after_id"] is not None:
        try:
          self.after_cancel(_alias_filter_state["after_id"])
        except Exception:
          pass
        _alias_filter_state["after_id"] = None

      _alias_filter_state["after_id"] = self.after(60, _alias_apply_filter)

    def _alias_toggle_dropdown() -> None:
      if getattr(self, "_alias_dropdown_visible", False):
        _alias_dropdown_hide()
      else:
        # show full list
        _alias_dropdown_render([v for v in (getattr(self, "_alias_dropdown_values", []) or []) if v])
        _alias_dropdown_place_below_entry()
        # Do NOT touch focus/caret here.

    self.btn_alias_drop.configure(command=_alias_toggle_dropdown)

    # Typing: filter and keep dropdown visible (without stealing focus)
    self.entry_alias.bind("<KeyRelease>", _alias_apply_filter_debounced)

    # Clicking into the Alias entry should open the dropdown (show all if empty, filtered if not).
    def _alias_open_on_click(_e=None) -> None:
      # Let the click set caret first, then place/render dropdown.
      try:
        self.after(1, lambda: _alias_apply_filter(show_if_any=True))
      except Exception:
        pass

    # Focus-in (tabbing into the field) should also open it.
    def _alias_open_on_focus(_e=None) -> None:
      try:
        if not getattr(self, "_alias_dropdown_visible", False):
          self.after(1, lambda: _alias_apply_filter(show_if_any=True))
      except Exception:
        pass

    self.entry_alias.bind("<Button-1>", _alias_open_on_click)
    self.entry_alias.bind("<FocusIn>", _alias_open_on_focus)

    # Esc closes dropdown
    self.entry_alias.bind("<Escape>", lambda _e: _alias_dropdown_hide())

    # Clicking outside closes dropdown (additive bind so we don’t break other handlers)
    if not getattr(self, "_alias_outside_click_bound", False):
      self._alias_outside_click_bound = True

      def _on_any_click_close_alias(e) -> None:
        try:
          w = e.widget

          # Treat clicks anywhere inside the alias picker (entry + button) as "inside".
          # CTk widgets often emit events from internal child widgets, not the outer widget.
          if _alias_is_descendant(w, self.alias_picker):
            return

          # Treat clicks inside the dropdown as "inside".
          if _alias_is_descendant(w, self._alias_dropdown):
            return

          _alias_dropdown_hide()
        except Exception:
          pass

      self.bind_all("<Button-1>", _on_any_click_close_alias, add="+")

    # Let _refresh_alias_dropdown update + hide if needed
    self._alias_dropdown_hide = _alias_dropdown_hide

    ctk.CTkLabel(form_row, text="Type").grid(row=0, column=6, padx=(14, 6), pady=10)
    self.opt_type = ctk.CTkOptionMenu(
      form_row,
      values=[TX_PURCHASE, TX_SALE],
      variable=self.var_type,
      width=140,
      command=lambda _: self._sync_type_fields(),
    )
    self.opt_type.grid(row=0, column=7, padx=6, pady=10)

    ctk.CTkLabel(form_row, text="Qty").grid(row=0, column=8, padx=(14, 6), pady=10)
    self.entry_qty = ctk.CTkEntry(form_row, textvariable=self.var_qty, width=80)
    self.entry_qty.grid(row=0, column=9, padx=6, pady=10)
    apply_entry_shortcuts(self.entry_qty)

    self.lbl_unit_price = ctk.CTkLabel(form_row, text="Purchase Unit Cost")
    self.lbl_unit_price.grid(row=0, column=10, padx=(14, 6), pady=10)

    self.entry_unit_price = ctk.CTkEntry(form_row, textvariable=self.var_unit_price, width=120)
    self.entry_unit_price.grid(row=0, column=11, padx=6, pady=10)
    apply_entry_shortcuts(self.entry_unit_price)

    ctk.CTkLabel(action_row, text="Note").grid(row=0, column=0, padx=(10, 6), pady=(0, 10))
    self.entry_note = ctk.CTkEntry(action_row, textvariable=self.var_note)
    self.entry_note.grid(row=0, column=1, sticky="ew", padx=6, pady=(0, 10))
    apply_entry_shortcuts(self.entry_note)

    buttons_frame = ctk.CTkFrame(action_row, fg_color="transparent")
    buttons_frame.grid(row=0, column=2, padx=(6, 10), pady=(0, 10), sticky="e")

    self.btn_add = ctk.CTkButton(buttons_frame, text="Add (Enter)", command=self._on_add)
    self.btn_add.grid(row=0, column=0, padx=6, sticky="ew")

    self.btn_update = ctk.CTkButton(buttons_frame, text="Update Selected", command=self._on_update_selected)
    self.btn_update.grid(row=0, column=1, padx=6, sticky="ew")

    self.btn_delete = ctk.CTkButton(
      buttons_frame,
      text="Delete Selected",
      fg_color="#8B2D2D",
      hover_color="#A53636",
      command=self._on_delete_selected,
    )
    self.btn_delete.grid(row=0, column=2, padx=6, sticky="ew")

    self.btn_export = ctk.CTkButton(buttons_frame, text="Export CSV", command=self._export_csv)
    self.btn_export.grid(row=0, column=3, padx=6, sticky="ew")

    for w in [
      self.entry_date,
      self.entry_sku,
      self.entry_alias,
      self.entry_qty,
      self.entry_unit_price,
      self.entry_note,
      self.btn_add,
    ]:
      bind_enter_shortcut(w, self._on_add)

    self.tx_custom_fields_frame = ctk.CTkFrame(action_row)
    self.tx_custom_fields_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 10))
    self.tx_custom_fields_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
    self._tx_custom_field_widgets = {}
    self._refresh_tx_custom_fields_editor()

    # ---------------------------------------------------------
    # Transactions Table (ttk.Treeview) — gitea-like behavior
    # - Zebra striping using CTk theme colors
    # - Hover tooltip shows ONLY the hovered cell value
    # - Both scrollbars (v/h)
    # ---------------------------------------------------------

    table_frame = ctk.CTkFrame(self.tab_tx)
    table_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(6, 10))

    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    table_frame.grid_rowconfigure(1, weight=0)

    all_custom_entries = self._get_all_custom_schema_in_display_order()
    tx_custom_columns = [str(x.get("key") or "").strip() for x in all_custom_entries if str(x.get("key") or "").strip()]
    tx_builtin_columns = self._get_visible_builtin_keys(FIELD_SCOPE_TX_TABLE)
    alias_idx = tx_builtin_columns.index("alias") if "alias" in tx_builtin_columns else min(len(tx_builtin_columns), 3)
    columns = tx_builtin_columns[:alias_idx + 1] + tx_custom_columns + tx_builtin_columns[alias_idx + 1:]

    self.tx_tree = ttk.Treeview(
      table_frame,
      columns=columns,
      show="headings",
      height=18,
      selectmode="extended",
      style="Treeview",
    )
    self.tx_tree.grid(row=0, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(
      table_frame,
      orient="vertical",
      command=self.tx_tree.yview,
      style="Dark.Vertical.TScrollbar",
    )
    hsb = ttk.Scrollbar(
      table_frame,
      orient="horizontal",
      command=self.tx_tree.xview,
      style="Dark.Horizontal.TScrollbar",
    )
    self.tx_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    # Zebra + error tint tags
    self.tx_tree.tag_configure("odd",  background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]))
    self.tx_tree.tag_configure("even", background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]))

    self.tx_tree.tag_configure("status_error_even", background="#3d1f1f")
    self.tx_tree.tag_configure("status_error_odd",  background="#462424")

    headings = {
      "id": "ID",
      "date": "Date",
      "sku": "SKU",
      "alias": "Alias",
      "type": "Type",
      "qty": "Qty",
      "purchase_unit_cost": "Purchase Unit Cost",
      "sale_unit_price": "Sale Unit Price",
      "purchase_total_cost": "Purchase Total Cost",
      "prev_avg_cost": "Prev Avg Cost",
      "onhand_qty": "OnHand Qty",
      "avg_cost_after": "Avg Cost",
      "cogs": "COGS",
      "onhand_cost": "OnHand Cost",
      "sales_rev": "Sales Rev",
      "gross_profit": "Gross Profit",
      "note": "Note",
    }
    for c in tx_custom_columns:
      headings[c] = c

    widths = {
      "id": 60, "date": 120, "sku": 200, "alias": 260, "type": 120, "qty": 80,
      "purchase_unit_cost": 165, "sale_unit_price": 145,
      "purchase_total_cost": 175, "prev_avg_cost": 145,
      "onhand_qty": 120, "avg_cost_after": 130,
      "cogs": 130, "onhand_cost": 155, "sales_rev": 140, "gross_profit": 180,
      "note": 380,
    }
    for c in tx_custom_columns:
      widths[c] = 150

    col_anchor = {
      "id": "center",
      "date": "w",
      "sku": "w",
      "alias": "w",
      "type": "center",
      "qty": "e",
      "purchase_unit_cost": "e",
      "sale_unit_price": "e",
      "purchase_total_cost": "e",
      "prev_avg_cost": "e",
      "onhand_qty": "e",
      "avg_cost_after": "e",
      "cogs": "e",
      "onhand_cost": "e",
      "sales_rev": "e",
      "gross_profit": "e",
      "note": "w",
    }
    for entry in self._get_all_custom_schema_in_display_order():
      key = str(entry.get("key") or "").strip()
      if key:
        col_anchor[key] = "center" if self._normalize_custom_type(entry.get("type")) == CUSTOM_TYPE_BOOLEAN else "w"

    head_anchor = {
      k: ("center" if v == "center" else ("e" if v == "e" else "w"))
      for k, v in col_anchor.items()
    }

    heading_gutter = "  "  # visual separation between adjacent headers

    for ci, c in enumerate(columns):
      base_text = headings.get(c, c)
      head_text = (f"{base_text}{heading_gutter}" if ci < (len(columns) - 1) else base_text)

      self.tx_tree.heading(
        c,
        text=head_text,
        anchor=head_anchor.get(c, "w"),
      )
      self.tx_tree.column(
        c,
        width=widths.get(c, 120),
        minwidth=32,
        anchor=col_anchor.get(c, "w"),
        stretch=False,
      )

    # ---------------------------------------------------------
    # Fit columns: let ONLY ["sku","alias","note"] stretch when possible.
    # If fixed columns exceed viewport, rely on h-scroll.
    # ---------------------------------------------------------

    _fit_after_id = {"id": None}

    def _fit_columns_now() -> None:
      try:
        frame_w = int(table_frame.winfo_width() or 0)
      except Exception:
        frame_w = 0
      if frame_w < 100:
        self.after(50, _fit_columns_now)
        return

      try:
        sb_w = int(vsb.winfo_width() or vsb.winfo_reqwidth() or 16)
      except Exception:
        sb_w = 16

      avail = max(frame_w - sb_w - 6, 64)

      cur_columns = tuple(self.tx_tree["columns"] or columns)
      dynamic_custom_cols = tuple(
        str(x.get("key") or "").strip()
        for x in self._get_all_custom_schema_in_display_order()
        if str(x.get("key") or "").strip() in cur_columns
      )
      stretch_cols = tuple([c for c in ("sku", "alias", *dynamic_custom_cols, "note") if c in cur_columns])
      fixed_cols = tuple(c for c in cur_columns if c not in stretch_cols)

      fixed_w = 0
      for c in fixed_cols:
        try:
          fixed_w += int(self.tx_tree.column(c, "width") or 0)
        except Exception:
          pass

      if fixed_w >= (avail - 64):
        return

      stretch_avail = max(avail - fixed_w, 64)

      # Proportional split across N stretch columns based on current widths.
      cur_w: Dict[str, int] = {}
      total = 0
      for c in stretch_cols:
        try:
          w = int(self.tx_tree.column(c, "width") or widths.get(c, 120) or 120)
        except Exception:
          w = int(widths.get(c, 120) or 120)
        w = max(w, 32)
        cur_w[c] = w
        total += w

      total = max(total, 1)

      used = 0
      for c in stretch_cols[:-1]:
        new_w = max(32, int(stretch_avail * (cur_w[c] / total)))
        used += new_w
        try:
          self.tx_tree.column(c, width=new_w)
        except Exception:
          pass

      last_c = stretch_cols[-1]
      last_w = max(32, int(stretch_avail - used))
      try:
        self.tx_tree.column(last_c, width=last_w)
      except Exception:
        pass

    def _fit_columns_debounced(_event=None) -> None:
      if _fit_after_id["id"] is not None:
        try:
          self.after_cancel(_fit_after_id["id"])
        except Exception:
          pass
      _fit_after_id["id"] = self.after(30, _fit_columns_now)

    table_frame.bind("<Configure>", _fit_columns_debounced)

    # ---------------------------------------------------------
    # Hover tooltip: ONLY hovered cell value (literal)
    # ---------------------------------------------------------

    _tree_tip_state = {"win": None, "lbl": None, "font": None, "last": None}

    def _tree_tip_hide() -> None:
      win = _tree_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _tree_tip_state["win"] = None
      _tree_tip_state["lbl"] = None
      _tree_tip_state["last"] = None

    def _tree_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _tree_tip_state["win"] is None:
        win = tk.Toplevel(self)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont
        if _tree_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _tree_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_tree_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()
        _tree_tip_state["win"] = win
        _tree_tip_state["lbl"] = lbl

      win = _tree_tip_state["win"]
      lbl = _tree_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)
      x = x_root + 14
      y = y_root + 16
      try:
        win.geometry(f"+{x}+{y}")
        win.deiconify()
      except Exception:
        pass

    header_tooltips = {
      "id": "ID: internal transaction row id.",
      "date": "Date: transaction date (sorted ascending for costing).",
      "sku": "SKU: item identifier used for costing/aggregation.",
      "alias": "Alias: friendly name for the SKU (from Aliases tab).",
      "type": "Type: PURCHASE adds inventory; SALE removes inventory.",
      "qty": "Qty: units bought/sold.",
      "purchase_unit_cost": "Purchase Unit Cost: per-unit cost on PURCHASE rows.",
      "sale_unit_price": "Sale Unit Price: per-unit sale price on SALE rows.",
      "purchase_total_cost": "Purchase Total Cost: Qty × Purchase Unit Cost.",
      "prev_avg_cost": "Prev Avg Cost: weighted average cost before this transaction.",
      "onhand_qty": "OnHand Qty: inventory quantity after this transaction.",
      "avg_cost_after": "Avg Cost: weighted average cost after this transaction.",
      "cogs": "COGS: Qty × Prev Avg Cost (for SALE rows).",
      "onhand_cost": "OnHand Cost: total cost value of inventory after this transaction.",
      "sales_rev": "Sales Rev: Qty × Sale Unit Price (for SALE rows).",
      "gross_profit": "Gross Profit: Sales Rev − COGS (for SALE rows).",
      "note": "Note: free text note for receipts/orders/etc.",
    }
    def _tree_on_hover(event) -> None:
      region = self.tx_tree.identify_region(event.x, event.y)

      # Header hover tooltip
      if region == "heading":
        col = self.tx_tree.identify_column(event.x)
        if not col or col == "#0":
          _tree_tip_hide()
          return

        cols = list(self.tx_tree["columns"])
        try:
          idx = int(col[1:]) - 1
        except Exception:
          _tree_tip_hide()
          return
        if idx < 0 or idx >= len(cols):
          _tree_tip_hide()
          return

        col_id = cols[idx]
        text = self._build_custom_column_tooltip(col_id, alias_only=False)
        if not text:
          text = str(header_tooltips.get(col_id) or headings.get(col_id) or col_id).strip()

        key = ("__heading__", col_id, text)
        if _tree_tip_state["last"] != key:
          _tree_tip_state["last"] = key
        _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
        return

      # Cell hover tooltip (existing behavior)
      if region != "cell":
        _tree_tip_hide()
        return

      iid = self.tx_tree.identify_row(event.y)
      col = self.tx_tree.identify_column(event.x)
      if not iid or not col or col == "#0":
        _tree_tip_hide()
        return

      cols = list(self.tx_tree["columns"])
      try:
        idx = int(col[1:]) - 1
      except Exception:
        _tree_tip_hide()
        return

      if idx < 0 or idx >= len(cols):
        _tree_tip_hide()
        return

      col_id = cols[idx]

      try:
        val = self.tx_tree.set(iid, col_id)
      except Exception:
        _tree_tip_hide()
        return

      text = str(val)
      key = (iid, col_id, text)
      if _tree_tip_state["last"] != key:
        _tree_tip_state["last"] = key
      _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    self.tx_tree.bind("<Motion>", _tree_on_hover)
    self.tx_tree.bind("<Leave>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<ButtonPress>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<MouseWheel>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<Button-4>", lambda _e: _tree_tip_hide())
    self.tx_tree.bind("<Button-5>", lambda _e: _tree_tip_hide())

    self._tx_tree_tip_hide = _tree_tip_hide

    def _on_tx_tree_select(_e=None) -> None:
      self._load_selected_into_form()
      self._sync_tx_update_selected_state()

    self.tx_tree.bind("<<TreeviewSelect>>", _on_tx_tree_select)

    self._sync_type_fields()

  def _build_overview_tab(self) -> None:
    # Layout: top controls + table frame
    self.tab_ov.grid_rowconfigure(1, weight=1)
    self.tab_ov.grid_columnconfigure(0, weight=1)

    # ---------------------------------------------------------
    # Controls
    # ---------------------------------------------------------

    controls = ctk.CTkFrame(self.tab_ov)
    controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
    # Column 2 holds the Export button; let it stretch so the button can sit on the far right.
    controls.grid_columnconfigure(2, weight=1)

    ctk.CTkLabel(controls, text="View").grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")

    self.ov_view_var = tk.StringVar(value="Inventory")
    self.opt_ov_view = ctk.CTkOptionMenu(
      controls,
      values=["Inventory", "Monthly"],
      variable=self.ov_view_var,
      width=160,
      command=lambda _v: self._on_overview_view_changed(),
    )
    self.opt_ov_view.grid(row=0, column=1, padx=6, pady=10, sticky="w")

    self.btn_ov_export = ctk.CTkButton(controls, text="Export CSV", command=self._export_overview_csv)
    self.btn_ov_export.grid(row=0, column=2, padx=(6, 10), pady=10, sticky="e")

    # ---------------------------------------------------------
    # Table
    # ---------------------------------------------------------

    frame = ctk.CTkFrame(self.tab_ov)
    frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(6, 10))
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(1, weight=0)

    # Keep refs for resize-fit logic
    self._ov_frame = frame

    self.ov_tree = ttk.Treeview(
      frame,
      columns=[],
      show="headings",
      height=18,
      selectmode="extended",
      style="Treeview",
    )
    self.ov_tree.grid(row=0, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(
      frame,
      orient="vertical",
      command=self.ov_tree.yview,
      style="Dark.Vertical.TScrollbar",
    )
    hsb = ttk.Scrollbar(
      frame,
      orient="horizontal",
      command=self.ov_tree.xview,
      style="Dark.Horizontal.TScrollbar",
    )
    self.ov_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    self._ov_vsb = vsb

    # Zebra + status tint tags (same naming as gitea_repository_backup)
    self.ov_tree.tag_configure(
      "odd",
      background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]),
    )
    self.ov_tree.tag_configure(
      "even",
      background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]),
    )

    self.ov_tree.tag_configure("status_done_even", background="#1f3d2b")   # dark green (even)
    self.ov_tree.tag_configure("status_done_odd",  background="#244632")   # dark green (odd)
    self.ov_tree.tag_configure("status_error_even", background="#3d1f1f")  # dark red (even)
    self.ov_tree.tag_configure("status_error_odd",  background="#462424")  # dark red (odd)

    # ---------------------------------------------------------
    # Auto-fit columns to viewport (robust across view modes)
    # ---------------------------------------------------------

    self._ov_fit_after_id = {"id": None}

    def _fit_columns_now() -> None:
      try:
        frame_w = int(self._ov_frame.winfo_width() or 0)
      except Exception:
        frame_w = 0

      if frame_w < 100:
        self.after(50, _fit_columns_now)
        return

      try:
        sb_w = int(self._ov_vsb.winfo_width() or self._ov_vsb.winfo_reqwidth() or 16)
      except Exception:
        sb_w = 16

      avail = max(frame_w - sb_w - 6, 64)

      cols = list(self.ov_tree["columns"] or [])
      if not cols:
        return

      mode = (self.ov_view_var.get() or "Inventory").strip()

      if mode == "Monthly":
        # Even-split ALL monthly columns across the viewport.
        stretch_cols = list(cols)
      else:
        stretch_cols = [c for c in ["sku", "alias", "status"] if c in cols]

      fixed_cols = [c for c in cols if c not in stretch_cols]

      fixed_w = 0
      for c in fixed_cols:
        try:
          fixed_w += int(self.ov_tree.column(c, "width") or 0)
        except Exception:
          pass

      if not stretch_cols:
        return

      if fixed_w >= (avail - 64):
        return

      stretch_avail = max(avail - fixed_w, 64)

      # Split evenly across stretch columns (simple + predictable)
      per = max(int(stretch_avail / max(len(stretch_cols), 1)), 32)
      for c in stretch_cols[:-1]:
        try:
          self.ov_tree.column(c, width=per)
        except Exception:
          pass

      # Last gets remainder to avoid rounding drift
      try:
        used = 0
        for c in stretch_cols[:-1]:
          used += int(self.ov_tree.column(c, "width") or per)
        last_w = max(int(stretch_avail - used), 32)
        self.ov_tree.column(stretch_cols[-1], width=last_w)
      except Exception:
        pass

    def _fit_columns_debounced(_event=None) -> None:
      if self._ov_fit_after_id["id"] is not None:
        try:
          self.after_cancel(self._ov_fit_after_id["id"])
        except Exception:
          pass
      self._ov_fit_after_id["id"] = self.after(30, _fit_columns_now)

    frame.bind("<Configure>", _fit_columns_debounced)
    self._ov_fit_columns_now = _fit_columns_now

    # ---------------------------------------------------------
    # Treeview hover tooltip: show ONLY hovered cell value (literal)
    # ---------------------------------------------------------

    _tree_tip_state = {
      "win": None,
      "lbl": None,
      "font": None,  # cached tk Font for tooltip
      "last": None,  # (iid, col_id, value)
    }

    def _tree_tip_hide() -> None:
      win = _tree_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _tree_tip_state["win"] = None
      _tree_tip_state["lbl"] = None
      _tree_tip_state["last"] = None

    def _tree_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _tree_tip_state["win"] is None:
        win = tk.Toplevel(self)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont

        if _tree_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _tree_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_tree_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()

        _tree_tip_state["win"] = win
        _tree_tip_state["lbl"] = lbl

      win = _tree_tip_state["win"]
      lbl = _tree_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)

      x = x_root + 14
      y = y_root + 16

      try:
        win.geometry(f"+{x}+{y}")
        win.deiconify()
      except Exception:
        pass

    header_tooltips = {
      # Inventory mode
      "sku": "SKU: item identifier.",
      "alias": "Alias: friendly name for SKU (from Aliases tab).",
      "onhand_qty": "OnHand Qty: current inventory quantity.",
      "avg_cost": "Avg Cost: weighted average cost per unit (current).",
      "onhand_cost": "OnHand Cost: total inventory value (Qty × Avg Cost).",
      "last_tx_date": "Last Tx Date: most recent transaction date for this SKU.",
      "last_sale_price": "Last Sale Price: most recent sale unit price for this SKU.",
      "status": "Status: IN STOCK / OUT / NEGATIVE (OVERSOLD).",

      # Monthly mode
      "month": "Month bucket (YYYY-MM).",
      "month_date": "Month Date (YYYY-MM-01).",
      "purchase_cost": "Purchase Cost: sum of purchase totals in the month.",
      "sales_amount": "Sales Amount: sum of sales revenue in the month.",
      "cogs": "COGS: sum of cost-of-goods-sold in the month.",
    }
    def _tree_on_hover(event) -> None:
      region = self.ov_tree.identify_region(event.x, event.y)

      # Header hover tooltip
      if region == "heading":
        col = self.ov_tree.identify_column(event.x)
        if not col or col == "#0":
          _tree_tip_hide()
          return

        cols = list(self.ov_tree["columns"])
        try:
          idx = int(col[1:]) - 1
        except Exception:
          _tree_tip_hide()
          return

        if idx < 0 or idx >= len(cols):
          _tree_tip_hide()
          return

        col_id = cols[idx]

        # Prefer our map, else fall back to the displayed heading text (strip gutter).
        text = self._build_custom_column_tooltip(col_id, alias_only=True)
        if not text:
          text = header_tooltips.get(col_id)
        if not text:
          try:
            text = str(self.ov_tree.heading(col_id, "text") or "").strip()
          except Exception:
            text = col_id
          text = text.strip()

        key = ("__heading__", col_id, text)
        if _tree_tip_state["last"] != key:
          _tree_tip_state["last"] = key
        _tree_tip_show(text=str(text), x_root=event.x_root, y_root=event.y_root)
        return

      # Cell hover tooltip (existing behavior)
      if region != "cell":
        _tree_tip_hide()
        return

      iid = self.ov_tree.identify_row(event.y)
      col = self.ov_tree.identify_column(event.x)
      if not iid or not col or col == "#0":
        _tree_tip_hide()
        return

      cols = list(self.ov_tree["columns"])
      try:
        idx = int(col[1:]) - 1
      except Exception:
        _tree_tip_hide()
        return

      if idx < 0 or idx >= len(cols):
        _tree_tip_hide()
        return

      col_id = cols[idx]

      try:
        val = self.ov_tree.set(iid, col_id)
      except Exception:
        _tree_tip_hide()
        return

      text = str(val)

      key = (iid, col_id, text)
      if _tree_tip_state["last"] != key:
        _tree_tip_state["last"] = key
        _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
      else:
        _tree_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    self.ov_tree.bind("<Motion>", _tree_on_hover)
    self.ov_tree.bind("<Leave>", lambda _e: _tree_tip_hide())
    self.ov_tree.bind("<ButtonPress>", lambda _e: _tree_tip_hide())
    self.ov_tree.bind("<MouseWheel>", lambda _e: _tree_tip_hide())  # Windows
    self.ov_tree.bind("<Button-4>", lambda _e: _tree_tip_hide())    # Linux scroll up
    self.ov_tree.bind("<Button-5>", lambda _e: _tree_tip_hide())    # Linux scroll down

    self._ov_tree_tip_hide = _tree_tip_hide

    # Configure initial view columns
    self._configure_overview_tree_for_view()

  def _build_aliases_tab(self) -> None:
    self.tab_alias.grid_rowconfigure(2, weight=1)
    self.tab_alias.grid_columnconfigure(0, weight=1)

    form = ctk.CTkFrame(self.tab_alias)
    form.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

    ctk.CTkLabel(form, text="SKU").grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")
    self.var_alias_sku = tk.StringVar(value="")
    self.entry_alias_sku = ctk.CTkEntry(form, textvariable=self.var_alias_sku, width=220)
    self.entry_alias_sku.grid(row=0, column=1, padx=6, pady=10, sticky="w")
    apply_entry_shortcuts(self.entry_alias_sku)

    ctk.CTkLabel(form, text="Name").grid(row=0, column=2, padx=(14, 6), pady=10, sticky="w")
    self.var_alias_name = tk.StringVar(value="")
    self.entry_alias_name = ctk.CTkEntry(form, textvariable=self.var_alias_name, width=360)
    self.entry_alias_name.grid(row=0, column=3, padx=6, pady=10, sticky="w")
    apply_entry_shortcuts(self.entry_alias_name)

    btns = ctk.CTkFrame(form, fg_color="transparent")
    btns.grid(row=0, column=4, padx=(12, 10), pady=10, sticky="e")

    self.btn_alias_add = ctk.CTkButton(btns, text="Add (Enter)", width=110, command=self._on_alias_add)
    self.btn_alias_add.grid(row=0, column=0, padx=6)

    self.btn_alias_update = ctk.CTkButton(btns, text="Update Selected", width=160, command=self._on_alias_update_selected)
    self.btn_alias_update.grid(row=0, column=1, padx=6)

    self.btn_alias_delete = ctk.CTkButton(
      btns,
      text="Delete Selected",
      width=150,
      fg_color="#8B2D2D",
      hover_color="#A53636",
      command=self._on_alias_delete_selected,
    )
    self.btn_alias_delete.grid(row=0, column=2, padx=6)

    for w in [
      self.entry_alias_sku,
      self.entry_alias_name,
      self.btn_alias_add,
    ]:
      bind_enter_shortcut(w, self._on_alias_add)

    self.alias_custom_fields_wrapper = ctk.CTkFrame(self.tab_alias)
    self.alias_custom_fields_wrapper.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
    self.alias_custom_fields_wrapper.grid_columnconfigure(0, weight=1)
    self.alias_custom_fields_frame = ctk.CTkFrame(self.alias_custom_fields_wrapper)
    self.alias_custom_fields_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 10))
    self.alias_custom_fields_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

    # Table
    table_frame = ctk.CTkFrame(self.tab_alias)
    table_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(6, 10))
    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    table_frame.grid_rowconfigure(1, weight=0)

    self.alias_tree = ttk.Treeview(
      table_frame,
      columns=self._get_visible_builtin_keys(FIELD_SCOPE_ALIAS_TABLE),
      show="headings",
      height=18,
      selectmode="extended",
      style="Treeview",
    )
    self.alias_tree.grid(row=0, column=0, sticky="nsew")

    vsb = ttk.Scrollbar(
      table_frame,
      orient="vertical",
      command=self.alias_tree.yview,
      style="Dark.Vertical.TScrollbar",
    )
    hsb = ttk.Scrollbar(
      table_frame,
      orient="horizontal",
      command=self.alias_tree.xview,
      style="Dark.Horizontal.TScrollbar",
    )
    self.alias_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    self.alias_tree.tag_configure("odd",  background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]))
    self.alias_tree.tag_configure("even", background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]))

    heading_gutter = "  "
    for col in self._get_visible_builtin_keys(FIELD_SCOPE_ALIAS_TABLE):
      text = "SKU" if col == "sku" else "Name"
      self.alias_tree.heading(col, text=(f"{text}{heading_gutter}" if col != "name" else text), anchor="w")
      self.alias_tree.column(col, width=(240 if col == "sku" else 520), minwidth=(80 if col == "sku" else 120), anchor="w", stretch=(col != "sku"))

    # ---------------------------------------------------------
    # Header hover tooltip (Aliases table)
    # ---------------------------------------------------------

    _alias_tip_state = {"win": None, "lbl": None, "font": None, "last": None}

    def _alias_tip_hide() -> None:
      win = _alias_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _alias_tip_state["win"] = None
      _alias_tip_state["lbl"] = None
      _alias_tip_state["last"] = None

    def _alias_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _alias_tip_state["win"] is None:
        win = tk.Toplevel(self)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont
        if _alias_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _alias_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_alias_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()
        _alias_tip_state["win"] = win
        _alias_tip_state["lbl"] = lbl

      win = _alias_tip_state["win"]
      lbl = _alias_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)
      x = x_root + 14
      y = y_root + 16
      try:
        win.geometry(f"+{x}+{y}")
        win.deiconify()
      except Exception:
        pass

    _alias_header_tooltips = {
      "sku": "SKU: the inventory identifier this alias maps to.",
      "name": "Name: friendly display name shown in tables and dropdowns.",
    }
    def _alias_on_hover(event) -> None:
      region = self.alias_tree.identify_region(event.x, event.y)

      # Header hover tooltip
      if region == "heading":
        col = self.alias_tree.identify_column(event.x)
        if not col or col == "#0":
          _alias_tip_hide()
          return

        cols = list(self.alias_tree["columns"])
        try:
          idx = int(col[1:]) - 1
        except Exception:
          _alias_tip_hide()
          return

        if idx < 0 or idx >= len(cols):
          _alias_tip_hide()
          return

        col_id = cols[idx]
        text = self._build_custom_column_tooltip(col_id, alias_only=False)
        if not text:
          text = str(_alias_header_tooltips.get(col_id) or col_id)

        key = ("__heading__", col_id, text)
        if _alias_tip_state["last"] != key:
          _alias_tip_state["last"] = key
        _alias_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
        return

      # Cell hover tooltip: show ONLY hovered cell value (literal)
      if region != "cell":
        _alias_tip_hide()
        return

      iid = self.alias_tree.identify_row(event.y)
      col = self.alias_tree.identify_column(event.x)
      if not iid or not col or col == "#0":
        _alias_tip_hide()
        return

      cols = list(self.alias_tree["columns"])
      try:
        idx = int(col[1:]) - 1
      except Exception:
        _alias_tip_hide()
        return

      if idx < 0 or idx >= len(cols):
        _alias_tip_hide()
        return

      col_id = cols[idx]

      try:
        val = self.alias_tree.set(iid, col_id)
      except Exception:
        _alias_tip_hide()
        return

      text = str(val)
      key = (iid, col_id, text)

      if _alias_tip_state["last"] != key:
        _alias_tip_state["last"] = key
        _alias_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
      else:
        _alias_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    self.alias_tree.bind("<Motion>", _alias_on_hover)
    self.alias_tree.bind("<Leave>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<ButtonPress>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<MouseWheel>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<Button-4>", lambda _e: _alias_tip_hide())
    self.alias_tree.bind("<Button-5>", lambda _e: _alias_tip_hide())

    def _on_alias_tree_select(_e=None) -> None:
      self._load_selected_alias_into_form()
      self._sync_alias_update_selected_state()

    self.alias_tree.bind("<<TreeviewSelect>>", _on_alias_tree_select)
    self._alias_custom_field_widgets = {}
    self._refresh_alias_custom_fields_editor()

  def _build_custom_fields_tab(self) -> None:
    self.tab_custom.grid_rowconfigure(1, weight=1)
    self.tab_custom.grid_columnconfigure(0, weight=1)

    schema_frame = ctk.CTkFrame(self.tab_custom)
    schema_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
    schema_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(schema_frame, text="Field Name").grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")
    self.var_custom_schema_key = tk.StringVar(value="")
    self.entry_custom_schema_key = ctk.CTkEntry(schema_frame, textvariable=self.var_custom_schema_key, width=220)
    self.entry_custom_schema_key.grid(row=0, column=1, padx=6, pady=10, sticky="ew")
    apply_entry_shortcuts(self.entry_custom_schema_key)

    ctk.CTkLabel(schema_frame, text="Target").grid(row=0, column=2, padx=(14, 6), pady=10, sticky="w")
    self.var_custom_schema_target = tk.StringVar(value=CUSTOM_TARGET_ALIAS)
    self.opt_custom_schema_target = ctk.CTkOptionMenu(
      schema_frame,
      values=list(CUSTOM_FIELD_TARGETS),
      variable=self.var_custom_schema_target,
      width=130,
    )
    self.opt_custom_schema_target.grid(row=0, column=3, padx=6, pady=10, sticky="w")

    ctk.CTkLabel(schema_frame, text="Type").grid(row=0, column=4, padx=(14, 6), pady=10, sticky="w")
    self.var_custom_schema_type = tk.StringVar(value=CUSTOM_TYPE_STRING)
    self.opt_custom_schema_type = ctk.CTkOptionMenu(
      schema_frame,
      values=list(CUSTOM_FIELD_TYPES),
      variable=self.var_custom_schema_type,
      width=120,
    )
    self.opt_custom_schema_type.grid(row=0, column=5, padx=6, pady=10, sticky="w")

    self.lbl_custom_schema_enum = ctk.CTkLabel(schema_frame, text="Enum Values")
    self.lbl_custom_schema_enum.grid(row=0, column=6, padx=(14, 6), pady=10, sticky="w")
    self.enum_summary_frame = ctk.CTkFrame(schema_frame, fg_color="transparent")
    self.enum_summary_frame.grid(row=0, column=7, columnspan=2, padx=6, pady=10, sticky="ew")
    self.enum_summary_frame.grid_columnconfigure(1, weight=1)
    self.btn_custom_enum_edit = ctk.CTkButton(self.enum_summary_frame, text="Edit Enum Values...", width=150, command=self._open_custom_schema_enum_popup)
    self.btn_custom_enum_edit.grid(row=0, column=0, padx=(0, 8), sticky="w")
    self.lbl_custom_enum_summary = ctk.CTkLabel(self.enum_summary_frame, text="No enum values")
    self.lbl_custom_enum_summary.grid(row=0, column=1, sticky="w")
    self._custom_schema_enum_values: List[str] = []
    self._custom_schema_enum_popup = None
    self._custom_schema_enum_popup_values: List[str] = []
    self._refresh_custom_schema_enum_summary()

    ctk.CTkLabel(schema_frame, text="Description (Tooltip)").grid(row=1, column=0, padx=(10, 6), pady=(0, 10), sticky="w")
    self.var_custom_schema_description = tk.StringVar(value="")
    self.entry_custom_schema_description = ctk.CTkEntry(schema_frame, textvariable=self.var_custom_schema_description)
    self.entry_custom_schema_description.grid(row=1, column=1, columnspan=5, padx=6, pady=(0, 10), sticky="ew")
    apply_entry_shortcuts(self.entry_custom_schema_description)

    self.var_field_enabled = tk.BooleanVar(value=True)
    self.chk_field_enabled = ctk.CTkCheckBox(schema_frame, text="Enabled", variable=self.var_field_enabled, onvalue=True, offvalue=False)
    self.chk_field_enabled.grid(row=1, column=6, columnspan=2, padx=6, pady=(0, 10), sticky="w")
    try:
      self.chk_field_enabled.configure(state="disabled")
    except Exception:
      pass

    btns = ctk.CTkFrame(schema_frame, fg_color="transparent")
    btns.grid(row=3, column=0, columnspan=9, padx=(12, 10), pady=(0, 10), sticky="e")

    self.btn_custom_schema_add = ctk.CTkButton(btns, text="Add Field (Enter)", width=140, command=self._on_custom_schema_add)
    self.btn_custom_schema_add.grid(row=0, column=0, padx=6)
    self.btn_custom_schema_update = ctk.CTkButton(btns, text="Update Selected", width=150, command=self._on_custom_schema_update_selected)
    self.btn_custom_schema_update.grid(row=0, column=1, padx=6)
    self.btn_custom_schema_delete = ctk.CTkButton(
      btns,
      text="Delete Selected",
      width=140,
      fg_color="#8B2D2D",
      hover_color="#A53636",
      command=self._on_custom_schema_delete_selected,
    )
    self.btn_custom_schema_delete.grid(row=0, column=2, padx=6)
    self.btn_custom_schema_up = ctk.CTkButton(btns, text="Move Up", width=100, command=lambda: self._move_selected_custom_schema(-1))
    self.btn_custom_schema_up.grid(row=0, column=3, padx=6)
    self.btn_custom_schema_down = ctk.CTkButton(btns, text="Move Down", width=110, command=lambda: self._move_selected_custom_schema(1))
    self.btn_custom_schema_down.grid(row=0, column=4, padx=6)

    def _sync_custom_schema_enum_state(*_args) -> None:
      show = (self.var_custom_schema_type.get() or "").strip().lower() == CUSTOM_TYPE_ENUM
      if show:
        self.lbl_custom_schema_enum.grid()
        self.enum_summary_frame.grid()
      else:
        self.lbl_custom_schema_enum.grid_remove()
        self.enum_summary_frame.grid_remove()

    self._sync_custom_schema_enum_state = _sync_custom_schema_enum_state
    self.opt_custom_schema_type.configure(command=lambda _v: _sync_custom_schema_enum_state())
    _sync_custom_schema_enum_state()

    for w in [self.entry_custom_schema_key, self.entry_custom_schema_description, self.btn_custom_schema_add]:
      bind_enter_shortcut(w, self._on_custom_schema_add)

    schema_table_frame = ctk.CTkFrame(self.tab_custom)
    schema_table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
    schema_table_frame.grid_rowconfigure(0, weight=1)
    schema_table_frame.grid_columnconfigure(0, weight=1)

    self.custom_schema_tree = ttk.Treeview(
      schema_table_frame,
      columns=["key", "scope", "kind", "type", "enabled", "capabilities", "enum", "description"],
      show="headings",
      height=16,
      selectmode="extended",
      style="Treeview",
    )
    self.custom_schema_tree.grid(row=0, column=0, sticky="nsew")
    schema_vsb = ttk.Scrollbar(schema_table_frame, orient="vertical", command=self.custom_schema_tree.yview, style="Dark.Vertical.TScrollbar")
    schema_hsb = ttk.Scrollbar(schema_table_frame, orient="horizontal", command=self.custom_schema_tree.xview, style="Dark.Horizontal.TScrollbar")
    self.custom_schema_tree.configure(yscrollcommand=schema_vsb.set, xscrollcommand=schema_hsb.set)
    schema_vsb.grid(row=0, column=1, sticky="ns")
    schema_hsb.grid(row=1, column=0, sticky="ew")
    self.custom_schema_tree.tag_configure("odd",  background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]))
    self.custom_schema_tree.tag_configure("even", background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]))
    self.custom_schema_tree.heading("key", text="Field Name  ", anchor="w")
    self.custom_schema_tree.heading("scope", text="Scope  ", anchor="w")
    self.custom_schema_tree.heading("kind", text="Source  ", anchor="w")
    self.custom_schema_tree.heading("type", text="Type  ", anchor="w")
    self.custom_schema_tree.heading("enabled", text="Enabled  ", anchor="center")
    self.custom_schema_tree.heading("capabilities", text="Capabilities  ", anchor="w")
    self.custom_schema_tree.heading("enum", text="Enum Values  ", anchor="w")
    self.custom_schema_tree.heading("description", text="Description", anchor="w")
    self.custom_schema_tree.column("key", width=280, minwidth=120, anchor="w", stretch=True)
    self.custom_schema_tree.column("scope", width=140, minwidth=100, anchor="w", stretch=False)
    self.custom_schema_tree.column("kind", width=100, minwidth=80, anchor="w", stretch=False)
    self.custom_schema_tree.column("type", width=120, minwidth=80, anchor="w", stretch=False)
    self.custom_schema_tree.column("enabled", width=95, minwidth=75, anchor="center", stretch=False)
    self.custom_schema_tree.column("capabilities", width=180, minwidth=120, anchor="w", stretch=False)
    self.custom_schema_tree.column("enum", width=260, minwidth=140, anchor="w", stretch=True)
    self.custom_schema_tree.column("description", width=420, minwidth=180, anchor="w", stretch=True)

    _schema_tip_state = {"win": None, "lbl": None, "font": None, "last": None}

    def _schema_tip_hide() -> None:
      win = _schema_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _schema_tip_state["win"] = None
      _schema_tip_state["lbl"] = None
      _schema_tip_state["last"] = None

    def _schema_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _schema_tip_state["win"] is None:
        win = tk.Toplevel(self)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont
        if _schema_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _schema_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_schema_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()
        _schema_tip_state["win"] = win
        _schema_tip_state["lbl"] = lbl

      win = _schema_tip_state["win"]
      lbl = _schema_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)
      try:
        win.geometry(f"+{x_root + 14}+{y_root + 16}")
        win.deiconify()
      except Exception:
        pass

    _schema_header_tooltips = {
      "key": "Field Name: system or custom field identifier shown in generated editors and columns.",
      "scope": "Scope: where the field appears.",
      "kind": "Source: system fields are built in, custom fields are project-defined.",
      "type": "Type: string, number, boolean, or enum.",
      "enabled": "Enabled: whether a removable built-in field is currently shown.",
      "capabilities": "Capabilities: what this field definition can currently do safely.",
      "enum": "Enum Values: allowed choices for enum fields.",
      "description": "Description: tooltip text shown on generated custom field labels and inputs.",
    }

    def _on_schema_tree_hover(event) -> None:
      region = self.custom_schema_tree.identify_region(event.x, event.y)

      if region == "heading":
        col = self.custom_schema_tree.identify_column(event.x)
        if not col or col == "#0":
          _schema_tip_hide()
          return
        cols = list(self.custom_schema_tree["columns"])
        try:
          idx = int(col[1:]) - 1
        except Exception:
          _schema_tip_hide()
          return
        if idx < 0 or idx >= len(cols):
          _schema_tip_hide()
          return
        col_id = cols[idx]
        text = str(_schema_header_tooltips.get(col_id) or col_id)
        key = ("__heading__", col_id, text)
        if _schema_tip_state["last"] != key:
          _schema_tip_state["last"] = key
        _schema_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
        return

      if region != "cell":
        _schema_tip_hide()
        return

      iid = self.custom_schema_tree.identify_row(event.y)
      col = self.custom_schema_tree.identify_column(event.x)
      if not iid or not col or col == "#0":
        _schema_tip_hide()
        return
      cols = list(self.custom_schema_tree["columns"])
      try:
        idx = int(col[1:]) - 1
      except Exception:
        _schema_tip_hide()
        return
      if idx < 0 or idx >= len(cols):
        _schema_tip_hide()
        return
      col_id = cols[idx]
      try:
        text = str(self.custom_schema_tree.set(iid, col_id))
      except Exception:
        _schema_tip_hide()
        return
      key = (iid, col_id, text)
      if _schema_tip_state["last"] != key:
        _schema_tip_state["last"] = key
      _schema_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    def _on_schema_select(_e=None) -> None:
      self._load_selected_custom_schema_into_form()
      self._sync_custom_schema_update_selected_state()

    self.custom_schema_tree.bind("<Motion>", _on_schema_tree_hover)
    self.custom_schema_tree.bind("<Leave>", lambda _e: _schema_tip_hide())
    self.custom_schema_tree.bind("<ButtonPress>", lambda _e: _schema_tip_hide())
    self.custom_schema_tree.bind("<MouseWheel>", lambda _e: _schema_tip_hide())
    self.custom_schema_tree.bind("<Button-4>", lambda _e: _schema_tip_hide())
    self.custom_schema_tree.bind("<Button-5>", lambda _e: _schema_tip_hide())
    self.custom_schema_tree.bind("<<TreeviewSelect>>", _on_schema_select)
    self._refresh_custom_schema_ui()



  def _on_pick_date(self) -> None:
    """
    Toggle the in-window calendar dropdown and set the Transactions form Date field.

    Behavior:
      - If tkcalendar is available: show a themed overlay calendar (inside the main window).
      - If not available: show a short info message (keeps app dependency-light).
    """
    try:
      # Overlay helpers are created during _build_transactions_tab()
      toggle = getattr(self, "_date_dropdown_toggle", None)
      if callable(toggle):
        toggle()
        return
    except Exception:
      pass

    # Fallback (shouldn't happen unless UI not built yet)
    if Calendar is None:
      messagebox.showinfo(
        "Date Picker",
        "Calendar picker requires optional dependency:\n\n"
        "  pip install tkcalendar\n\n"
        "You can still type the date as YYYY-MM-DD or M/D/YYYY."
      )
      try:
        self.entry_date.focus_set()
      except Exception:
        pass

  # -----------------------------------------------------------------------------
  # Project bar callbacks
  # -----------------------------------------------------------------------------

  def _on_project_combo_selected(self) -> None:
    # Same behavior as your attached script: selecting loads immediately
    Log.info(self.LOG_TAG, "Project selected from recent list.", {"project_dir": self.project_dir_var.get()})
    self._on_load_project()

  def _on_browse_project(self) -> None:
    Log.info(self.LOG_TAG, "Opening project directory selector.")
    p = filedialog.askdirectory(title="Select Project Directory")
    if not p:
      Log.warn(self.LOG_TAG, "Project directory selector canceled.")
      return
    self.project_dir_var.set(os.path.abspath(p))
    Log.info(self.LOG_TAG, "Project directory selected from dialog.", {"project_dir": os.path.abspath(p)})
    self._on_load_project()

  def _on_load_project(self) -> None:
    p = (self.project_dir_var.get() or "").strip()
    if not p or not os.path.isdir(p):
      Log.error(self.LOG_TAG, "Load project blocked: missing or invalid directory.", {"project_dir": p})
      messagebox.showerror("Project", "Project directory is missing or invalid.")
      return
    self._load_project_dir(p)

  def _on_clear_history(self) -> None:
    should_clear = messagebox.askyesno("Clear History", "Clear recent project directory history?")
    if not should_clear:
      Log.warn(self.LOG_TAG, "Clear history canceled by user.")
      return
    Log.warn(self.LOG_TAG, "Clearing active project state and recent history.")
    self._clear_project_history()
    self.project_dir_var.set("")
    self.project_dir = ""
    self.project_data_path = ""
    self.transactions = []
    self.aliases_list = []
    self._rebuild_alias_map()
    self.custom_fields_schema = []
    self._rebuild_custom_field_schema_map()
    self.next_id = 1
    self.next_created_order = 1
    self._set_tx_controls_enabled(False)
    self._refresh_aliases_ui()
    self._refresh_all()

  # -----------------------------------------------------------------------------
  # Enable/disable controls if no project loaded
  # -----------------------------------------------------------------------------

  def _set_tx_controls_enabled(self, enabled: bool) -> None:
    state_entry = "normal" if enabled else "disabled"
    state_btn = "normal" if enabled else "disabled"

    for w in [self.entry_date, self.entry_sku, self.entry_qty, self.entry_unit_price, self.entry_note]:
      try:
        w.configure(state=state_entry)
      except Exception:
        pass

    for w in [getattr(self, "btn_date_pick", None)]:
      if w is None:
        continue
      try:
        w.configure(state=("normal" if enabled else "disabled"))
      except Exception:
        pass

    # Alias picker (Entry + dropdown button)
    for w in [getattr(self, "entry_alias", None), getattr(self, "btn_alias_drop", None)]:
      if w is None:
        continue
      try:
        w.configure(state=("normal" if enabled else "disabled"))
      except Exception:
        pass

    if not enabled:
      try:
        if hasattr(self, "_alias_dropdown_hide"):
          self._alias_dropdown_hide()
      except Exception:
        pass

      try:
        if hasattr(self, "_date_dropdown_hide"):
          self._date_dropdown_hide()
      except Exception:
        pass

    for w in [self.opt_type]:
      try:
        w.configure(state=state_btn)
      except Exception:
        pass

    for b in [self.btn_add, self.btn_update, self.btn_delete, self.btn_export]:
      try:
        b.configure(state=state_btn)
      except Exception:
        pass

    # Overview tab controls
    for w in [getattr(self, "opt_ov_view", None)]:

      if w is None:
        continue
      try:
        w.configure(state=state_btn)
      except Exception:
        pass

    for b in [getattr(self, "btn_ov_export", None)]:
      if b is None:
        continue
      try:
        b.configure(state=state_btn)
      except Exception:
        pass

    # Aliases tab controls
    for w in [getattr(self, "entry_alias_sku", None), getattr(self, "entry_alias_name", None)]:
      if w is None:
        continue
      try:
        w.configure(state=state_entry)
      except Exception:
        pass

    for b in [getattr(self, "btn_alias_add", None), getattr(self, "btn_alias_update", None), getattr(self, "btn_alias_delete", None)]:
      if b is None:
        continue
      try:
        b.configure(state=state_btn)
      except Exception:
        pass

    # Custom Fields tab controls
    for w in [
      getattr(self, "entry_custom_schema_key", None),
      getattr(self, "entry_custom_schema_description", None),
    ]:
      if w is None:
        continue
      try:
        w.configure(state=state_entry)
      except Exception:
        pass

    for w in [getattr(self, "opt_custom_schema_target", None), getattr(self, "opt_custom_schema_type", None)]:
      if w is None:
        continue
      try:
        w.configure(state=state_btn)
      except Exception:
        pass

    for b in [
      getattr(self, "btn_custom_schema_add", None),
      getattr(self, "btn_custom_schema_update", None),
      getattr(self, "btn_custom_schema_delete", None),
      getattr(self, "btn_custom_schema_up", None),
      getattr(self, "btn_custom_schema_down", None),
      getattr(self, "btn_custom_enum_edit", None),
    ]:
      if b is None:
        continue
      try:
        b.configure(state=state_btn)
      except Exception:
        pass

    for meta in list(getattr(self, "_tx_custom_field_widgets", {}).values()):
      widget = meta.get("widget") if isinstance(meta, dict) else None
      if widget is None:
        continue
      try:
        widget.configure(state=state_entry)
      except Exception:
        pass

    for meta in list(getattr(self, "_alias_custom_field_widgets", {}).values()):
      widget = meta.get("widget") if isinstance(meta, dict) else None
      if widget is None:
        continue
      try:
        widget.configure(state=state_entry)
      except Exception:
        pass

    # Keep "Update Selected" buttons disabled unless exactly one row is selected.
    try:
      self._sync_update_selected_buttons_state()
    except Exception:
      pass

  # -----------------------------------------------------------------------------
  # Alias UI syncing (Transactions form dropdown)
  # -----------------------------------------------------------------------------

  def _build_alias_display_values(self) -> List[str]:
    """
    Build Alias dropdown display values.

    Format:
      "<Name>  [<SKU>]"
    """
    out: List[str] = []
    for a in (self.aliases_list or []):
      sku = str(a.get("sku") or "").strip()
      name = str(a.get("name") or "").strip()
      if not sku or not name:
        continue
      out.append(f"{name}  [{sku}]")
    out.sort(key=lambda s: s.lower())
    return out

  def _parse_alias_display_value(self, s: str) -> Tuple[str, str]:
    """
    Parse "<Name>  [<SKU>]" -> (sku, name)
    """
    raw = str(s or "").strip()
    if not raw:
      return "", ""
    m = re.search(r"\[(.+?)\]\s*$", raw)
    if not m:
      return "", raw
    sku = m.group(1).strip()
    name = raw[: m.start()].strip()
    return sku, name

  def _refresh_alias_dropdown(self) -> None:
    """
    Refresh the Transactions-tab Alias dropdown cache.

    IMPORTANT:
      We no longer use `alias_combo` (CTkComboBox). The Transactions tab now uses
      `entry_alias` + an overlay dropdown, so this must NOT early-return when
      `alias_combo` is absent.

    Behavior:
      - Rebuild `self._alias_dropdown_values` from `self.aliases_list`.
      - Hide the overlay dropdown if it is currently visible.
      - Sync the displayed alias text from the current SKU (if any).
    """
    self._alias_dropdown_values = [""] + self._build_alias_display_values()

    # If dropdown is open, close it so it can't show stale entries
    try:
      if hasattr(self, "_alias_dropdown_hide"):
        self._alias_dropdown_hide()
    except Exception:
      pass

    # Keep selection consistent with current SKU
    self._sync_alias_choice_from_sku()

  def _sync_alias_choice_from_sku(self) -> None:
    if self._alias_sync_guard:
      return
    self._alias_sync_guard = True
    try:
      sku = (self.var_sku.get() or "").strip()
      name = self._get_alias_for_sku(sku)
      if sku and name:
        disp = f"{name}  [{sku}]"
        try:
          self.var_alias_choice.set(disp)
        except Exception:
          pass
      else:
        try:
          if (self.var_alias_choice.get() or "").strip():
            self.var_alias_choice.set("")
        except Exception:
          pass
    finally:
      self._alias_sync_guard = False

  def _on_alias_selected_in_tx_form(self) -> None:
    if self._alias_sync_guard:
      return
    self._alias_sync_guard = True
    try:
      choice = (self.var_alias_choice.get() or "").strip()
      if not choice:
        return
      sku, _name = self._parse_alias_display_value(choice)
      if sku:
        # Set SKU, but DO NOT steal focus from the Alias dropdown.
        self.var_sku.set(sku)
    finally:
      self._alias_sync_guard = False

  # -----------------------------------------------------------------------------
  # Aliases Tab Actions
  # -----------------------------------------------------------------------------

  def _refresh_aliases_ui(self) -> None:
    """
    Refresh alias tab table + transactions form dropdown.
    Safe to call even before UI exists.
    """
    self._rebuild_alias_map()
    self._refresh_alias_dropdown()

    if not hasattr(self, "alias_tree"):
      return

    alias_schema = self._get_custom_schema_for_target(CUSTOM_TARGET_ALIAS)
    builtin_columns = self._get_visible_builtin_keys(FIELD_SCOPE_ALIAS_TABLE)
    columns = builtin_columns + [str(x.get("key") or "").strip() for x in alias_schema if str(x.get("key") or "").strip()]
    try:
      self.alias_tree["columns"] = columns
      if "sku" in columns:
        self.alias_tree.heading("sku", text="SKU  ", anchor="w")
        self.alias_tree.column("sku", width=240, minwidth=80, anchor="w", stretch=False)
      if "name" in columns:
        self.alias_tree.heading("name", text=("Name  " if len(columns) > len(builtin_columns) else "Name"), anchor="w")
        self.alias_tree.column("name", width=300, minwidth=120, anchor="w", stretch=True)
      for idx, entry in enumerate(alias_schema):
        key = str(entry.get("key") or "").strip()
        if not key:
          continue
        gutter = "  " if idx < (len(alias_schema) - 1) else ""
        anchor = "center" if self._normalize_custom_type(entry.get("type")) == CUSTOM_TYPE_BOOLEAN else "w"
        self.alias_tree.heading(key, text=f"{key}{gutter}", anchor=("center" if anchor == "center" else "w"))
        self.alias_tree.column(key, width=150, minwidth=90, anchor=anchor, stretch=True)
      self.alias_tree.delete(*self.alias_tree.get_children())
    except Exception:
      return

    rows = list(self.aliases_list or [])
    rows.sort(key=lambda x: (str(x.get("name", "")).lower(), str(x.get("sku", "")).lower()))

    for i, a in enumerate(rows):
      sku = str(a.get("sku") or "").strip()
      name = str(a.get("name") or "").strip()
      if not sku or not name:
        continue
      pad_l = "  "
      custom_values = dict(a.get("custom_fields") or {})
      values_list: List[Any] = []
      if "sku" in builtin_columns:
        values_list.append(f"{pad_l}{sku}")
      if "name" in builtin_columns:
        values_list.append(f"{pad_l}{name}")
      for entry in alias_schema:
        key = str(entry.get("key") or "").strip()
        values_list.append(self._format_custom_field_value(entry, custom_values.get(key, None)))
      values = tuple(values_list)
      tag = "even" if (i % 2) == 0 else "odd"
      self.alias_tree.insert("", "end", iid=sku, values=values, tags=(tag,))

    # Keep "Update Selected" disabled unless exactly one row is selected.
    try:
      self._sync_alias_update_selected_state()
    except Exception:
      pass
    self._update_alias_custom_fields_editor_values(next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == self._get_selected_alias_sku()), None))

  def _get_selected_alias_skus(self) -> List[str]:
    """
    Get all selected alias SKUs (extended selection).
    Returns a sorted list of unique SKUs.
    """
    if not hasattr(self, "alias_tree"):
      return []
    sel = self.alias_tree.selection()
    if not sel:
      return []
    out = []
    for iid in sel:
      s = str(iid or "").strip()
      if s:
        out.append(s)
    out = sorted(set(out), key=lambda x: x.lower())
    return out

  def _get_selected_alias_sku(self) -> Optional[str]:
    if not hasattr(self, "alias_tree"):
      return None
    sel = self.alias_tree.selection()
    if not sel:
      return None
    return str(sel[0])

  def _load_selected_alias_into_form(self) -> None:
    sku = self._get_selected_alias_sku()
    if not sku:
      return
    alias_item = next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == sku), None)
    name = self._get_alias_for_sku(sku)
    self.var_alias_sku.set(sku)
    self.var_alias_name.set(name)
    self._update_alias_custom_fields_editor_values(alias_item)

  def _read_alias_form(self) -> Tuple[str, str, Dict[str, Any]]:
    sku = str(self.var_alias_sku.get() or "").strip()
    name = str(self.var_alias_name.get() or "").strip()
    if not sku:
      raise ValueError("Alias SKU is required")
    if not name:
      raise ValueError("Alias Name is required")
    custom_fields = self._read_target_custom_field_form("_alias_custom_field_widgets")
    return sku, name, custom_fields

  def _upsert_alias(self, sku: str, name: str, custom_fields: Optional[Dict[str, Any]] = None) -> None:
    sku = str(sku or "").strip()
    name = str(name or "").strip()
    if not sku or not name:
      return
    custom_map = dict(custom_fields or {})

    found = False
    for a in self.aliases_list:
      if str(a.get("sku") or "").strip() == sku:
        a["name"] = name
        a["custom_fields"] = custom_map
        found = True
        break

    if not found:
      self.aliases_list.append({"sku": sku, "name": name, "custom_fields": custom_map})

    self.aliases_list.sort(key=lambda x: (str(x.get("name", "")).lower(), str(x.get("sku", "")).lower()))

  def _on_alias_add(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Add alias blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    try:
      sku, name, custom_fields = self._read_alias_form()
    except Exception as e:
      Log.error(self.LOG_TAG, "Add alias validation failed.", {"error": str(e)})
      messagebox.showerror("Invalid", str(e))
      return

    self._upsert_alias(sku, name, custom_fields)
    self._save_and_refresh()
    try:
      if hasattr(self, "alias_tree") and self.alias_tree.exists(sku):
        self.alias_tree.selection_set(sku)
        self.alias_tree.focus(sku)
        self.alias_tree.see(sku)
    except Exception:
      pass
    Log.ok(self.LOG_TAG, "Added/updated alias.", {"sku": sku})

  def _on_alias_delete_selected(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Delete aliases blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    skus = self._get_selected_alias_skus()
    if not skus:
      Log.warn(self.LOG_TAG, "Delete aliases requested with no selection.")
      messagebox.showinfo("Delete", "Select one or more alias rows first.")
      return

    preview = ", ".join(skus[:10])
    if len(skus) > 10:
      preview += f", … (+{len(skus) - 10} more)"

    if not messagebox.askyesno("Delete Alias", f"Delete {len(skus)} selected alias(es)?\n\nSKUs: {preview}"):
      Log.warn(self.LOG_TAG, "Delete aliases canceled by user.", {"count": len(skus)})
      return

    sku_set = set(skus)
    before = len(self.aliases_list)
    self.aliases_list = [a for a in self.aliases_list if str(a.get("sku") or "").strip() not in sku_set]
    after = len(self.aliases_list)

    self._save_and_refresh()
    self.var_alias_sku.set("")
    self.var_alias_name.set("")
    Log.warn(self.LOG_TAG, "Deleted aliases.", {"count": (before - after), "skus": skus})

  # -----------------------------------------------------------------------------
  # UI Actions
  # -----------------------------------------------------------------------------

  def _sync_type_fields(self) -> None:
    t = self.var_type.get()

    # Persist what the user typed into the appropriate backing var before swapping.
    cur = (self.var_unit_price.get() or "").strip()
    prev = getattr(self, "_last_type_for_unit", None)

    if prev == TX_PURCHASE:
      self.var_purchase_unit.set(cur or self.var_purchase_unit.get())
    elif prev == TX_SALE:
      self.var_sale_unit.set(cur or self.var_sale_unit.get())

    # Swap label + displayed value.
    if t == TX_PURCHASE:
      self.lbl_unit_price.configure(text="Purchase Unit Cost")
      self.var_unit_price.set(self.var_purchase_unit.get())
    else:
      self.lbl_unit_price.configure(text="Sale Unit Price")
      self.var_unit_price.set(self.var_sale_unit.get())

    self._last_type_for_unit = t

    # Disable field if no project loaded (matches prior behavior).
    self.entry_unit_price.configure(state=("normal" if self.project_data_path else "disabled"))

  def _on_add(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Add transaction blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    try:
      tx = self._read_form_to_transaction(existing_id=None)
    except Exception as e:
      Log.error(self.LOG_TAG, "Add transaction validation failed.", {"error": str(e)})
      messagebox.showerror("Invalid", str(e))
      return

    self.transactions.append(tx)
    self._save_and_refresh()
    self._select_tx_id(tx.id)
    Log.ok(self.LOG_TAG, "Added transaction.", {"id": tx.id, "sku": tx.sku, "type": tx.type})

  def _on_update_selected(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Update transaction blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    ids = self._get_selected_tx_ids()
    if not ids:
      Log.warn(self.LOG_TAG, "Update transaction requested with no selection.")
      messagebox.showinfo("Update", "Select a transaction row first.")
      return

    if len(ids) != 1:
      Log.warn(self.LOG_TAG, "Update transaction requires single selection.", {"selected_count": len(ids)})
      messagebox.showwarning("Update", "Please select exactly ONE transaction row to update.")
      return

    sel = ids[0]

    try:
      updated = self._read_form_to_transaction(existing_id=sel)
    except Exception as e:
      Log.error(self.LOG_TAG, "Update transaction validation failed.", {"id": sel, "error": str(e)})
      messagebox.showerror("Invalid", str(e))
      return

    for i, t in enumerate(self.transactions):
      if t.id == sel:
        # Preserve original insertion order for stable sorting.
        updated.created_order = t.created_order
        self.transactions[i] = updated
        break

    self._save_and_refresh()
    self._select_tx_id(sel)
    Log.ok(self.LOG_TAG, "Updated transaction.", {"id": sel})

  def _on_alias_update_selected(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Update alias blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    skus = self._get_selected_alias_skus()
    if not skus:
      Log.warn(self.LOG_TAG, "Update alias requested with no selection.")
      messagebox.showinfo("Update", "Select an alias row first.")
      return

    if len(skus) != 1:
      Log.warn(self.LOG_TAG, "Update alias requires single selection.", {"selected_count": len(skus)})
      messagebox.showwarning("Update", "Please select exactly ONE alias row to update.")
      return

    sel_sku = skus[0]
    sel_alias = next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == sel_sku), None)

    try:
      sku, name, custom_fields = self._read_alias_form()
    except Exception as e:
      Log.error(self.LOG_TAG, "Update alias validation failed.", {"sku": sel_sku, "error": str(e)})
      messagebox.showerror("Invalid", str(e))
      return

    if sku != sel_sku:
      # Renaming SKU key: delete old alias row and migrate existing transactions.
      self.aliases_list = [a for a in self.aliases_list if str(a.get("sku") or "").strip() != sel_sku]
      for tx in self.transactions:
        if str(tx.sku or "").strip() == sel_sku:
          tx.sku = sku
    elif sel_alias is not None and not custom_fields:
      custom_fields = dict(sel_alias.get("custom_fields") or {})
    self._upsert_alias(sku, name, custom_fields)

    self._save_and_refresh()
    try:
      if hasattr(self, "alias_tree") and self.alias_tree.exists(sku):
        self.alias_tree.selection_set(sku)
        self.alias_tree.focus(sku)
        self.alias_tree.see(sku)
    except Exception:
      pass
    Log.ok(self.LOG_TAG, "Updated alias.", {"sku": sel_sku, "new_sku": sku})

  # -----------------------------------------------------------------------------
  # Custom Fields
  # -----------------------------------------------------------------------------

  def _scope_label(self, scope: str) -> str:
    return {
      FIELD_SCOPE_TX_TABLE: "Transactions",
      FIELD_SCOPE_ALIAS_TABLE: "Aliases",
      FIELD_SCOPE_OVERVIEW_INVENTORY: "Overview",
      CUSTOM_TARGET_TRANSACTION: "Transactions",
      CUSTOM_TARGET_ALIAS: "Aliases",
    }.get(str(scope or "").strip(), str(scope or "").strip())

  def _get_builtin_field_defs(self, scope: Optional[str] = None) -> List[Dict[str, Any]]:
    scope_s = str(scope or "").strip()
    items: List[Dict[str, Any]] = []
    for entry in BUILTIN_FIELD_DEFS:
      if scope_s and str(entry.get("scope") or "").strip() != scope_s:
        continue
      item = dict(entry)
      override = dict((self.field_overrides or {}).get(str(item.get("id") or "").strip(), {}) or {})
      enabled = bool(override.get("enabled", item.get("enabled", True)))
      if not bool(item.get("removable")):
        enabled = True
      item["enabled"] = enabled
      items.append(item)
    return items

  def _is_builtin_field_enabled(self, field_id: str) -> bool:
    item = next((x for x in self._get_builtin_field_defs() if str(x.get("id") or "").strip() == str(field_id or "").strip()), None)
    return bool((item or {}).get("enabled", True))

  def _set_builtin_field_enabled(self, field_id: str, enabled: bool) -> None:
    field_id_s = str(field_id or "").strip()
    if not field_id_s:
      return
    builtin = next((x for x in BUILTIN_FIELD_DEFS if str(x.get("id") or "").strip() == field_id_s), None)
    if not builtin:
      return
    if not bool(builtin.get("removable")):
      enabled = True
    self.field_overrides[field_id_s] = {"enabled": bool(enabled)}

  def _get_visible_builtin_keys(self, scope: str) -> List[str]:
    out: List[str] = []
    for entry in self._get_builtin_field_defs(scope):
      if bool(entry.get("enabled", True)):
        key = str(entry.get("key") or "").strip()
        if key:
          out.append(key)
    return out

  def _get_all_field_registry_entries(self) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for entry in self._get_builtin_field_defs():
      caps = ["toggle" if bool(entry.get("removable")) else "locked"]
      if bool(entry.get("enum_editable")):
        caps.append("enum")
      rows.append({
        **dict(entry),
        "kind": "system",
        "capabilities": ", ".join(caps),
      })
    for entry in (self.custom_fields_schema or []):
      key = str(entry.get("key") or "").strip()
      if not key:
        continue
      rows.append({
        **dict(entry),
        "id": f"custom:{key}",
        "label": key,
        "scope": self._scope_label(self._normalize_custom_target(entry.get("target"))),
        "enabled": True,
        "source": "custom",
        "kind": "custom",
        "capabilities": "rename, reorder, delete",
      })
    return rows

  def _get_custom_schema_for_target(self, target: str) -> List[Dict[str, Any]]:
    target_norm = self._normalize_custom_target(target)
    return [dict(x) for x in (self.custom_fields_schema or []) if self._normalize_custom_target(x.get("target")) == target_norm]

  def _get_all_custom_schema_in_display_order(self) -> List[Dict[str, Any]]:
    return [dict(x) for x in (self.custom_fields_schema or []) if str(x.get("key") or "").strip()]

  def _build_custom_column_tooltip(self, key: str, *, alias_only: bool = False) -> Optional[str]:
    key_s = str(key or "").strip()
    if not key_s:
      return None
    entries = self._get_custom_schema_for_target(CUSTOM_TARGET_ALIAS) if alias_only else self._get_all_custom_schema_in_display_order()
    entry = next((x for x in entries if str(x.get("key") or "").strip() == key_s), None)
    if not entry:
      return None
    desc = str(entry.get("description") or "").strip()
    if desc:
      return f"{key_s}: {desc}"
    dtype = self._normalize_custom_type(entry.get("type"))
    target = self._normalize_custom_target(entry.get("target"))
    vals = ", ".join([str(x) for x in (entry.get("enum") or [])])
    if dtype == CUSTOM_TYPE_ENUM and vals:
      return f"{key_s}: {target} enum field. Values: {vals}."
    return f"{key_s}: {target} custom field ({dtype})."

  def _get_transaction_custom_value_for_overview(self, sku: str, key: str) -> Any:
    sku_s = str(sku or "").strip()
    key_s = str(key or "").strip()
    if not sku_s or not key_s:
      return None
    for tx in sorted(self.transactions or [], key=lambda t: (t.date, t.created_order, t.id), reverse=True):
      if str(getattr(tx, "sku", "") or "").strip() != sku_s:
        continue
      custom_fields = dict(getattr(tx, "custom_fields", {}) or {})
      if key_s in custom_fields:
        return custom_fields.get(key_s)
    return None

  def _rebuild_custom_field_schema_map(self) -> None:
    self._custom_field_schema_map = {
      str(x.get("key") or "").strip(): x
      for x in (self.custom_fields_schema or [])
      if str(x.get("key") or "").strip()
    }

  def _parse_custom_schema_enum_input(self, raw: str) -> List[str]:
    return self._normalize_enum_values([x.strip() for x in str(raw or "").split(",")])

  def _refresh_custom_schema_enum_summary(self) -> None:
    if not hasattr(self, "lbl_custom_enum_summary"):
      return
    vals = list(getattr(self, "_custom_schema_enum_values", []) or [])
    if not vals:
      text = "No enum values"
    elif len(vals) <= 3:
      text = ", ".join(vals)
    else:
      text = ", ".join(vals[:3]) + f", ... (+{len(vals) - 3})"
    try:
      self.lbl_custom_enum_summary.configure(text=text)
    except Exception:
      pass

  def _refresh_custom_schema_enum_popup_tree(self) -> None:
    tree = getattr(self, "_custom_schema_enum_popup_tree", None)
    if tree is None:
      return
    try:
      tree.delete(*tree.get_children())
    except Exception:
      return
    for i, value in enumerate(getattr(self, "_custom_schema_enum_popup_values", []) or []):
      tag = "even" if (i % 2) == 0 else "odd"
      tree.insert("", "end", iid=f"enum_{i}", values=(value,), tags=(tag,))

  def _on_custom_schema_enum_popup_add(self) -> None:
    raw = str(getattr(self, "_custom_schema_enum_popup_input_var", tk.StringVar(value="")).get() or "").strip()
    values = self._parse_custom_schema_enum_input(raw)
    if not values:
      return
    cur = list(getattr(self, "_custom_schema_enum_popup_values", []) or [])
    seen = set(cur)
    for value in values:
      if value not in seen:
        seen.add(value)
        cur.append(value)
    self._custom_schema_enum_popup_values = cur
    self._refresh_custom_schema_enum_popup_tree()
    try:
      self._custom_schema_enum_popup_input_var.set("")
      self._custom_schema_enum_popup_entry.focus_set()
    except Exception:
      pass

  def _on_custom_schema_enum_popup_remove_selected(self) -> None:
    tree = getattr(self, "_custom_schema_enum_popup_tree", None)
    if tree is None:
      return
    selected = list(tree.selection() or [])
    if not selected:
      return
    remove_idx = set()
    for iid in selected:
      try:
        remove_idx.add(int(str(iid).split("_")[-1]))
      except Exception:
        pass
    keep = [value for i, value in enumerate(list(getattr(self, "_custom_schema_enum_popup_values", []) or [])) if i not in remove_idx]
    self._custom_schema_enum_popup_values = keep
    self._refresh_custom_schema_enum_popup_tree()

  def _on_custom_schema_enum_popup_clear(self) -> None:
    self._custom_schema_enum_popup_values = []
    self._refresh_custom_schema_enum_popup_tree()

  def _on_custom_schema_enum_popup_move(self, direction: int) -> None:
    tree = getattr(self, "_custom_schema_enum_popup_tree", None)
    if tree is None:
      return
    selected = list(tree.selection() or [])
    if not selected:
      return
    try:
      selected_idx = sorted(
        {
          int(str(iid).split("_")[-1])
          for iid in selected
          if str(iid).startswith("enum_")
        }
      )
    except Exception:
      return
    values = list(getattr(self, "_custom_schema_enum_popup_values", []) or [])
    if not values or not selected_idx:
      return

    if direction < 0:
      if selected_idx[0] <= 0:
        return
      for idx in selected_idx:
        values[idx - 1], values[idx] = values[idx], values[idx - 1]
      selected_idx = [idx - 1 for idx in selected_idx]
    elif direction > 0:
      if selected_idx[-1] >= len(values) - 1:
        return
      for idx in reversed(selected_idx):
        values[idx + 1], values[idx] = values[idx], values[idx + 1]
      selected_idx = [idx + 1 for idx in selected_idx]
    else:
      return

    self._custom_schema_enum_popup_values = values
    self._refresh_custom_schema_enum_popup_tree()
    try:
      new_ids = [f"enum_{idx}" for idx in selected_idx]
      tree.selection_set(new_ids)
      tree.focus(new_ids[0])
      tree.see(new_ids[0])
    except Exception:
      pass

  def _close_custom_schema_enum_popup(self, *, confirm: bool) -> None:
    if confirm:
      self._custom_schema_enum_values = list(getattr(self, "_custom_schema_enum_popup_values", []) or [])
      self._refresh_custom_schema_enum_summary()
    popup = getattr(self, "_custom_schema_enum_popup", None)
    if popup is not None:
      try:
        popup.destroy()
      except Exception:
        pass
    self._custom_schema_enum_popup = None
    self._custom_schema_enum_popup_tree = None
    self._custom_schema_enum_popup_entry = None
    self._custom_schema_enum_popup_input_var = None
    self._custom_schema_enum_popup_values = []

  def _open_custom_schema_enum_popup(self) -> None:
    if getattr(self, "_custom_schema_enum_popup", None) is not None:
      try:
        self._custom_schema_enum_popup.lift()
        self._custom_schema_enum_popup.focus_force()
      except Exception:
        pass
      return

    popup = ctk.CTkToplevel(self)
    popup.title(f"{APP_TITLE} - Edit Enum Values")
    popup.transient(self)
    popup.resizable(False, False)
    try:
      set_window_icon(popup, APP_ICON_ICO_PATH, APP_ICON_PNG_PATH)
    except Exception:
      pass
    try:
      parent_icon = getattr(self, "_iconphoto_ref", None)
      if parent_icon is not None:
        popup.iconphoto(True, parent_icon)
        popup._iconphoto_ref = parent_icon  # type: ignore[attr-defined]
    except Exception:
      pass
    try:
      popup.grab_set()
    except Exception:
      pass
    popup.grid_columnconfigure(0, weight=1)
    popup.grid_rowconfigure(1, weight=1)

    top = ctk.CTkFrame(popup)
    top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
    top.grid_columnconfigure(1, weight=1)

    lbl_enum_value = ctk.CTkLabel(top, text="Enum Value")
    lbl_enum_value.grid(row=0, column=0, padx=(10, 6), pady=10, sticky="w")
    self._custom_schema_enum_popup_input_var = tk.StringVar(value="")
    self._custom_schema_enum_popup_entry = ctk.CTkEntry(top, textvariable=self._custom_schema_enum_popup_input_var, width=260)
    self._custom_schema_enum_popup_entry.grid(row=0, column=1, padx=6, pady=10, sticky="ew")
    apply_entry_shortcuts(self._custom_schema_enum_popup_entry)
    btn_add = ctk.CTkButton(top, text="Add Value (Enter)", width=140, command=self._on_custom_schema_enum_popup_add)
    btn_add.grid(row=0, column=2, padx=(6, 10), pady=10)
    bind_enter_shortcut(popup, self._on_custom_schema_enum_popup_add)
    bind_enter_shortcut(self._custom_schema_enum_popup_entry, self._on_custom_schema_enum_popup_add)
    bind_enter_shortcut(btn_add, self._on_custom_schema_enum_popup_add)

    table_frame = ctk.CTkFrame(popup)
    table_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
    table_frame.grid_rowconfigure(0, weight=1)
    table_frame.grid_columnconfigure(0, weight=1)
    self._custom_schema_enum_popup_tree = ttk.Treeview(
      table_frame,
      columns=["value"],
      show="headings",
      height=8,
      selectmode="extended",
      style="Treeview",
    )
    self._custom_schema_enum_popup_tree.grid(row=0, column=0, sticky="nsew")
    self._custom_schema_enum_popup_tree.heading("value", text="Allowed Values", anchor="w")
    self._custom_schema_enum_popup_tree.column("value", width=320, minwidth=180, anchor="w", stretch=True)
    self._custom_schema_enum_popup_tree.tag_configure("odd",  background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]))
    self._custom_schema_enum_popup_tree.tag_configure("even", background=_ctk_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]))
    vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._custom_schema_enum_popup_tree.yview, style="Dark.Vertical.TScrollbar")
    self._custom_schema_enum_popup_tree.configure(yscrollcommand=vsb.set)
    vsb.grid(row=0, column=1, sticky="ns")

    mid_btns = ctk.CTkFrame(popup, fg_color="transparent")
    mid_btns.grid(row=2, column=0, sticky="e", padx=12, pady=(0, 8))
    btn_up = ctk.CTkButton(mid_btns, text="Move Up", width=90, command=lambda: self._on_custom_schema_enum_popup_move(-1))
    btn_up.grid(row=0, column=0, padx=4)
    btn_down = ctk.CTkButton(mid_btns, text="Move Down", width=100, command=lambda: self._on_custom_schema_enum_popup_move(1))
    btn_down.grid(row=0, column=1, padx=4)
    btn_remove = ctk.CTkButton(mid_btns, text="Remove", width=90, command=self._on_custom_schema_enum_popup_remove_selected)
    btn_remove.grid(row=0, column=2, padx=4)
    btn_clear = ctk.CTkButton(mid_btns, text="Clear", width=80, command=self._on_custom_schema_enum_popup_clear)
    btn_clear.grid(row=0, column=3, padx=4)

    bottom = ctk.CTkFrame(popup, fg_color="transparent")
    bottom.grid(row=3, column=0, sticky="e", padx=12, pady=(0, 12))
    btn_ok = ctk.CTkButton(bottom, text="Confirm", width=100, command=lambda: self._close_custom_schema_enum_popup(confirm=True))
    btn_ok.grid(row=0, column=0, padx=4)
    btn_reject = ctk.CTkButton(bottom, text="Reject", width=90, command=lambda: self._close_custom_schema_enum_popup(confirm=False))
    btn_reject.grid(row=0, column=1, padx=4)

    tooltip(top, text="Enum Value Entry: type a value and press Enter or Add Value to append it to the allowed values list.")
    tooltip(lbl_enum_value, self._custom_schema_enum_popup_entry, text="Enum Value: type one allowed value here, then press Enter to add it to the list.")
    tooltip(btn_add, text="Add Value: append the typed enum value to the allowed values list.")
    tooltip(self._custom_schema_enum_popup_tree, text="Allowed Values: current ordered list of choices for this enum field.")
    tooltip(btn_up, text="Move Up: move the selected enum value(s) up in the allowed values order.")
    tooltip(btn_down, text="Move Down: move the selected enum value(s) down in the allowed values order.")
    tooltip(btn_remove, text="Remove: delete the selected enum value(s) from the allowed values list.")
    tooltip(btn_clear, text="Clear: remove every allowed enum value from the list.")
    tooltip(btn_ok, text="Confirm: save the popup enum values back to the custom field and close this window.")
    tooltip(btn_reject, text="Reject: discard popup changes and close this window.")

    _popup_tip_state = {"win": None, "lbl": None, "font": None, "last": None}

    def _popup_tip_hide() -> None:
      win = _popup_tip_state.get("win")
      if win is not None:
        try:
          win.destroy()
        except Exception:
          pass
      _popup_tip_state["win"] = None
      _popup_tip_state["lbl"] = None
      _popup_tip_state["last"] = None

    def _popup_tip_show(*, text: str, x_root: int, y_root: int) -> None:
      if _popup_tip_state["win"] is None:
        win = tk.Toplevel(popup)
        win.withdraw()
        win.overrideredirect(True)
        try:
          win.attributes("-topmost", True)
        except Exception:
          pass

        bg = _ctk_color(ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"])
        fg = _ctk_color(ctk.ThemeManager.theme["CTkLabel"]["text_color"])

        from tkinter import font as tkfont
        if _popup_tip_state["font"] is None:
          f = tkfont.nametofont("TkDefaultFont").copy()
          try:
            f.configure(size=int(f.cget("size")) + 4)
          except Exception:
            f.configure(size=14)
          _popup_tip_state["font"] = f

        lbl = tk.Label(
          win,
          text="",
          justify="left",
          anchor="w",
          padx=8,
          pady=4,
          bg=bg,
          fg=fg,
          font=_popup_tip_state["font"],
          bd=1,
          relief="solid",
        )
        lbl.pack()
        _popup_tip_state["win"] = win
        _popup_tip_state["lbl"] = lbl

      win = _popup_tip_state["win"]
      lbl = _popup_tip_state["lbl"]
      if win is None or lbl is None:
        return

      lbl.configure(text=text)
      try:
        win.geometry(f"+{x_root + 14}+{y_root + 16}")
        win.deiconify()
      except Exception:
        pass

    def _on_popup_tree_hover(event) -> None:
      tree = getattr(self, "_custom_schema_enum_popup_tree", None)
      if tree is None:
        _popup_tip_hide()
        return

      region = tree.identify_region(event.x, event.y)
      if region == "heading":
        text = "Allowed Values: current ordered list of choices for this enum field."
        key = ("__heading__", text)
        if _popup_tip_state["last"] != key:
          _popup_tip_state["last"] = key
        _popup_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)
        return

      if region != "cell":
        _popup_tip_hide()
        return

      iid = tree.identify_row(event.y)
      if not iid:
        _popup_tip_hide()
        return
      try:
        text = str(tree.set(iid, "value") or "")
      except Exception:
        _popup_tip_hide()
        return
      if not text:
        _popup_tip_hide()
        return
      key = (iid, text)
      if _popup_tip_state["last"] != key:
        _popup_tip_state["last"] = key
      _popup_tip_show(text=text, x_root=event.x_root, y_root=event.y_root)

    self._custom_schema_enum_popup_tree.bind("<Motion>", _on_popup_tree_hover, add="+")
    self._custom_schema_enum_popup_tree.bind("<Leave>", lambda _e: _popup_tip_hide(), add="+")
    self._custom_schema_enum_popup_tree.bind("<ButtonPress-1>", lambda _e: _popup_tip_hide(), add="+")
    self._custom_schema_enum_popup_tree.bind("<MouseWheel>", lambda _e: _popup_tip_hide(), add="+")
    self._custom_schema_enum_popup_tree.bind("<Destroy>", lambda _e: _popup_tip_hide(), add="+")

    self._custom_schema_enum_popup = popup
    self._custom_schema_enum_popup_values = list(getattr(self, "_custom_schema_enum_values", []) or [])
    self._refresh_custom_schema_enum_popup_tree()
    popup.protocol("WM_DELETE_WINDOW", lambda: self._close_custom_schema_enum_popup(confirm=False))
    try:
      self._custom_schema_enum_popup_entry.focus_set()
    except Exception:
      pass

  def _read_custom_schema_form(self) -> Dict[str, Any]:
    key = str(self.var_custom_schema_key.get() or "").strip()
    if not key:
      raise ValueError("Field Name is required")
    target = self._normalize_custom_target(self.var_custom_schema_target.get())
    dtype = self._normalize_custom_type(self.var_custom_schema_type.get())
    description = str(self.var_custom_schema_description.get() or "").strip()
    enum_vals = list(getattr(self, "_custom_schema_enum_values", []) or []) if dtype == CUSTOM_TYPE_ENUM else []
    if dtype == CUSTOM_TYPE_ENUM and not enum_vals:
      raise ValueError("Enum fields require at least one enum value")
    return {"key": key, "target": target, "type": dtype, "description": description, "enum": enum_vals}

  def _get_selected_field_ids(self) -> List[str]:
    if not hasattr(self, "custom_schema_tree"):
      return []
    out: List[str] = []
    for iid in (self.custom_schema_tree.selection() or []):
      field_id = str(iid or "").strip()
      if field_id:
        out.append(field_id)
    return sorted(set(out), key=lambda x: x.lower())

  def _get_selected_custom_schema_keys(self) -> List[str]:
    out: List[str] = []
    for field_id in self._get_selected_field_ids():
      if not field_id.startswith("custom:"):
        continue
      key = field_id.split(":", 1)[1].strip()
      if key:
        out.append(key)
    return sorted(set(out), key=lambda x: x.lower())

  def _load_selected_custom_schema_into_form(self) -> None:
    field_ids = self._get_selected_field_ids()
    if len(field_ids) != 1:
      try:
        self.entry_custom_schema_key.configure(state="normal")
        self.entry_custom_schema_description.configure(state="normal")
        self.opt_custom_schema_target.configure(state="normal")
        self.opt_custom_schema_type.configure(state="normal")
        self.btn_custom_enum_edit.configure(state="normal")
        self.chk_field_enabled.configure(state="disabled")
      except Exception:
        pass
      return
    field_id = field_ids[0]
    entry = dict(self._field_registry_map.get(field_id) or {})
    self.var_custom_schema_key.set(str(entry.get("key") or ""))
    self.var_custom_schema_target.set(self._normalize_custom_target(entry.get("target")))
    self.var_custom_schema_type.set(self._normalize_custom_type(entry.get("type")))
    self.var_custom_schema_description.set(str(entry.get("description") or ""))
    self.var_field_enabled.set(bool(entry.get("enabled", True)))
    self._custom_schema_enum_values = [str(x) for x in (entry.get("enum") or []) if str(x).strip()]
    self._refresh_custom_schema_enum_summary()
    try:
      if getattr(self, "_custom_schema_enum_popup_input_var", None) is not None:
        self._custom_schema_enum_popup_input_var.set("")
    except Exception:
      pass
    if hasattr(self, "opt_custom_schema_target"):
      try:
        self.opt_custom_schema_target.set(self.var_custom_schema_target.get())
      except Exception:
        pass
    if hasattr(self, "opt_custom_schema_type"):
      try:
        self.opt_custom_schema_type.set(self.var_custom_schema_type.get())
      except Exception:
        pass
    is_custom = str(entry.get("kind") or "") == "custom"
    is_removable_builtin = bool(entry.get("removable"))
    try:
      self.entry_custom_schema_key.configure(state=("normal" if is_custom else "disabled"))
      self.entry_custom_schema_description.configure(state=("normal" if is_custom else "disabled"))
      self.opt_custom_schema_target.configure(state=("normal" if is_custom else "disabled"))
      self.opt_custom_schema_type.configure(state=("normal" if is_custom else "disabled"))
      self.btn_custom_enum_edit.configure(state=("normal" if is_custom else "disabled"))
      self.chk_field_enabled.configure(state=("normal" if is_removable_builtin else "disabled"))
    except Exception:
      pass
    try:
      getattr(self, "_sync_custom_schema_enum_state", lambda: None)()
    except Exception:
      pass

  def _sync_custom_schema_update_selected_state(self) -> None:
    has_project = bool(self.project_data_path)
    field_ids = self._get_selected_field_ids()
    sel_count = len(field_ids)
    entry = dict(self._field_registry_map.get(field_ids[0]) or {}) if sel_count == 1 else {}
    is_custom = bool(entry) and str(entry.get("kind") or "") == "custom"
    can_toggle_builtin = bool(entry) and str(entry.get("kind") or "") == "system" and bool(entry.get("removable"))
    self._set_ctk_button_enabled(getattr(self, "btn_custom_schema_update", None), bool(has_project and sel_count == 1 and (is_custom or can_toggle_builtin)))
    self._set_ctk_button_enabled(getattr(self, "btn_custom_schema_delete", None), bool(has_project and ((sel_count >= 1 and all(x.startswith("custom:") for x in field_ids)) or can_toggle_builtin)))
    self._set_ctk_button_enabled(getattr(self, "btn_custom_schema_up", None), bool(has_project and sel_count == 1 and is_custom))
    self._set_ctk_button_enabled(getattr(self, "btn_custom_schema_down", None), bool(has_project and sel_count == 1 and is_custom))

  def _move_selected_custom_schema(self, direction: int) -> None:
    if not self.project_data_path:
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    keys = self._get_selected_custom_schema_keys()
    if len(keys) != 1:
      messagebox.showinfo("Reorder", "Select exactly one custom field row first.")
      return
    key = keys[0]
    idx = next((i for i, entry in enumerate(self.custom_fields_schema or []) if str(entry.get("key") or "").strip() == key), -1)
    if idx < 0:
      return
    new_idx = idx + int(direction)
    if new_idx < 0 or new_idx >= len(self.custom_fields_schema):
      return
    items = list(self.custom_fields_schema or [])
    items[idx], items[new_idx] = items[new_idx], items[idx]
    self.custom_fields_schema = items
    self._save_and_refresh(schema_changed=True)
    try:
      self.custom_schema_tree.selection_set(f"custom:{key}")
      self.custom_schema_tree.focus(f"custom:{key}")
      self.custom_schema_tree.see(f"custom:{key}")
    except Exception:
      pass

  def _upsert_custom_schema_entry(self, entry: Dict[str, Any], *, replacing_key: Optional[str] = None) -> None:
    new_key = str(entry.get("key") or "").strip()
    if not new_key:
      return
    replacing = str(replacing_key or "").strip()
    new_items: List[Dict[str, Any]] = []
    found = False
    for item in (self.custom_fields_schema or []):
      item_key = str(item.get("key") or "").strip()
      if not item_key:
        continue
      if item_key.lower() == new_key.lower() and item_key != replacing:
        raise ValueError(f"Custom field already exists: {new_key}")
      if replacing and item_key == replacing:
        new_items.append(dict(entry))
        found = True
      elif item_key != replacing:
        new_items.append(dict(item))
    if not found:
      for item in new_items:
        if str(item.get("key") or "").strip().lower() == new_key.lower():
          raise ValueError(f"Custom field already exists: {new_key}")
      new_items.append(dict(entry))
    self.custom_fields_schema = new_items
    self._rebuild_custom_field_schema_map()

  def _rename_custom_schema_key_in_values(self, old_key: str, new_key: str, *, target: str) -> None:
    if old_key == new_key:
      return
    target_norm = self._normalize_custom_target(target)
    if target_norm == CUSTOM_TARGET_TRANSACTION:
      for tx in (self.transactions or []):
        custom_fields = dict(getattr(tx, "custom_fields", {}) or {})
        if old_key in custom_fields:
          custom_fields[new_key] = custom_fields.pop(old_key)
          tx.custom_fields = custom_fields
      return
    for alias in (self.aliases_list or []):
      custom_fields = dict(alias.get("custom_fields") or {})
      if old_key in custom_fields:
        custom_fields[new_key] = custom_fields.pop(old_key)
        alias["custom_fields"] = custom_fields

  def _remove_custom_schema_keys_from_values(self, keys: List[str], *, target: str) -> None:
    key_set = {str(k or "").strip() for k in (keys or []) if str(k or "").strip()}
    if not key_set:
      return
    if self._normalize_custom_target(target) == CUSTOM_TARGET_TRANSACTION:
      for tx in (self.transactions or []):
        custom_fields = dict(getattr(tx, "custom_fields", {}) or {})
        for key in key_set:
          custom_fields.pop(key, None)
        tx.custom_fields = custom_fields
      return
    for alias in (self.aliases_list or []):
      custom_fields = dict(alias.get("custom_fields") or {})
      for key in key_set:
        custom_fields.pop(key, None)
      alias["custom_fields"] = custom_fields

  def _coerce_custom_field_value(self, schema_entry: Dict[str, Any], raw: Any, *, raise_on_error: bool = True) -> Any:
    dtype = self._normalize_custom_type(schema_entry.get("type"))
    if dtype == CUSTOM_TYPE_BOOLEAN:
      if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("", "0", "false", "no", "off", "n"):
          return False
        if s in ("1", "true", "yes", "on", "y"):
          return True
      return bool(raw)

    if raw is None:
      return None

    if dtype == CUSTOM_TYPE_NUMBER:
      s = str(raw).strip()
      if not s:
        return None
      try:
        return float(s)
      except Exception:
        if raise_on_error:
          raise ValueError(f"{schema_entry.get('key')}: number is invalid")
        return None

    if dtype == CUSTOM_TYPE_ENUM:
      s = str(raw or "").strip()
      if not s:
        return None
      enum_vals = self._normalize_enum_values(schema_entry.get("enum", []))
      if enum_vals and s not in enum_vals:
        if raise_on_error:
          raise ValueError(f"{schema_entry.get('key')}: value must be one of {', '.join(enum_vals)}")
        return None
      return s

    s = str(raw or "")
    return s if s != "" else None

  def _format_custom_field_value(self, schema_entry: Dict[str, Any], value: Any) -> str:
    if value is None:
      return ""
    dtype = self._normalize_custom_type(schema_entry.get("type"))
    if dtype == CUSTOM_TYPE_BOOLEAN:
      return "Yes" if bool(value) else "No"
    if dtype == CUSTOM_TYPE_NUMBER:
      try:
        num = float(value)
      except Exception:
        return str(value)
      return str(int(num)) if num.is_integer() else f"{num:g}"
    return str(value)

  def _get_entity_custom_values(self, entity: Any) -> Dict[str, Any]:
    raw = getattr(entity, "custom_fields", None) if hasattr(entity, "custom_fields") else None
    if raw is None and isinstance(entity, dict):
      raw = entity.get("custom_fields")
    return dict(raw or {}) if isinstance(raw, dict) else {}

  def _build_target_custom_field_editor(self, parent: Any, *, target: str, widgets_attr: str, source: Any = None) -> None:
    try:
      for child in parent.winfo_children():
        child.destroy()
    except Exception:
      pass
    widgets: Dict[str, Dict[str, Any]] = {}
    schema_entries = self._get_custom_schema_for_target(target)
    current_values = self._get_entity_custom_values(source)
    if not schema_entries:
      setattr(self, widgets_attr, widgets)
      ctk.CTkLabel(parent, text=f"No {target} custom fields defined.").grid(row=0, column=0, padx=10, pady=8, sticky="w")
      return
    try:
      for col in range(4):
        parent.grid_columnconfigure(col, weight=1)
    except Exception:
      pass
    for i, entry in enumerate(schema_entries):
      row = int(i / 4)
      col = int(i % 4)
      key = str(entry.get("key") or "").strip()
      dtype = self._normalize_custom_type(entry.get("type"))
      desc = str(entry.get("description") or "").strip()
      cell = ctk.CTkFrame(parent, fg_color="transparent")
      cell.grid(row=row, column=col, padx=6, pady=6, sticky="ew")
      try:
        cell.grid_columnconfigure(1, weight=1)
      except Exception:
        pass
      lbl = ctk.CTkLabel(cell, text=key)
      lbl.grid(row=0, column=0, padx=(4, 8), pady=4, sticky="w")
      existing = current_values.get(key, None)
      if dtype == CUSTOM_TYPE_BOOLEAN:
        var = tk.BooleanVar(value=bool(existing))
        widget = ctk.CTkCheckBox(cell, text="", variable=var, onvalue=True, offvalue=False)
        widget.grid(row=0, column=1, padx=4, pady=4, sticky="w")
      elif dtype == CUSTOM_TYPE_ENUM:
        values = [""] + [v for v in self._normalize_enum_values(entry.get("enum", [])) if str(v) != ""]
        current = str(existing if existing is not None else "")
        if current and current not in values:
          values.append(current)
        var = tk.StringVar(value=current)
        widget = ctk.CTkOptionMenu(cell, values=values, variable=var, width=220)
        widget.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
      else:
        var = tk.StringVar(value="" if existing is None else self._format_custom_field_value(entry, existing))
        widget = ctk.CTkEntry(cell, textvariable=var, width=220)
        widget.grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        apply_entry_shortcuts(widget)
      if desc:
        tooltip(lbl, widget, text=desc)
      else:
        clear_tooltip(lbl, widget)
      widgets[key] = {"var": var, "widget": widget, "schema": dict(entry)}
    setattr(self, widgets_attr, widgets)

  def _read_target_custom_field_form(self, widgets_attr: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, meta in dict(getattr(self, widgets_attr, {}) or {}).items():
      schema = dict(meta.get("schema") or {})
      var = meta.get("var")
      raw = var.get() if var is not None and hasattr(var, "get") else None
      value = self._coerce_custom_field_value(schema, raw, raise_on_error=True)
      if value is not None:
        out[key] = value
    return out

  def _set_target_custom_field_editor_values(self, widgets_attr: str, source: Any = None) -> None:
    current_values = self._get_entity_custom_values(source)
    for key, meta in dict(getattr(self, widgets_attr, {}) or {}).items():
      schema = dict(meta.get("schema") or {})
      dtype = self._normalize_custom_type(schema.get("type"))
      var = meta.get("var")
      widget = meta.get("widget")
      if var is None or not hasattr(var, "set"):
        continue
      value = current_values.get(key, None)
      if dtype == CUSTOM_TYPE_BOOLEAN:
        var.set(bool(value))
      elif dtype == CUSTOM_TYPE_ENUM:
        current = "" if value is None else str(value)
        if widget is not None and hasattr(widget, "configure"):
          values = [""] + [v for v in self._normalize_enum_values(schema.get("enum", [])) if str(v) != ""]
          if current and current not in values:
            values.append(current)
          try:
            widget.configure(values=values)
          except Exception:
            pass
        var.set(current)
      else:
        var.set("" if value is None else self._format_custom_field_value(schema, value))

  def _refresh_tx_custom_fields_editor(self, tx: Optional[Transaction] = None) -> None:
    if hasattr(self, "tx_custom_fields_frame"):
      self._build_target_custom_field_editor(
        self.tx_custom_fields_frame,
        target=CUSTOM_TARGET_TRANSACTION,
        widgets_attr="_tx_custom_field_widgets",
        source=tx,
      )

  def _update_tx_custom_fields_editor_values(self, tx: Optional[Transaction] = None) -> None:
    self._set_target_custom_field_editor_values("_tx_custom_field_widgets", tx)

  def _refresh_alias_custom_fields_editor(self, alias_item: Optional[Dict[str, Any]] = None) -> None:
    if hasattr(self, "alias_custom_fields_frame"):
      self._build_target_custom_field_editor(
        self.alias_custom_fields_frame,
        target=CUSTOM_TARGET_ALIAS,
        widgets_attr="_alias_custom_field_widgets",
        source=alias_item,
      )

  def _update_alias_custom_fields_editor_values(self, alias_item: Optional[Dict[str, Any]] = None) -> None:
    self._set_target_custom_field_editor_values("_alias_custom_field_widgets", alias_item)

  def _refresh_custom_schema_ui(self) -> None:
    self._rebuild_custom_field_schema_map()
    self._field_registry_map = {}
    if hasattr(self, "custom_schema_tree"):
      try:
        self.custom_schema_tree.delete(*self.custom_schema_tree.get_children())
      except Exception:
        pass
      for i, entry in enumerate(self._get_all_field_registry_entries()):
        field_id = str(entry.get("id") or "").strip()
        key = str(entry.get("label") or entry.get("key") or "").strip()
        values = (
          f"  {key}",
          self._scope_label(entry.get("scope")) if str(entry.get("kind") or "") == "system" else str(entry.get("scope") or ""),
          str(entry.get("source") or entry.get("kind") or ""),
          self._normalize_custom_type(entry.get("type")),
          "Yes" if bool(entry.get("enabled", True)) else "No",
          str(entry.get("capabilities") or ""),
          ", ".join([str(x) for x in (entry.get("enum") or [])]),
          str(entry.get("description") or ""),
        )
        tag = "even" if (i % 2) == 0 else "odd"
        if field_id:
          self._field_registry_map[field_id] = dict(entry)
          self.custom_schema_tree.insert("", "end", iid=field_id, values=values, tags=(tag,))
    self._refresh_tx_custom_fields_editor()
    self._refresh_alias_custom_fields_editor()
    self._sync_custom_schema_update_selected_state()

  def _on_custom_schema_add(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Add custom field blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    try:
      entry = self._read_custom_schema_form()
      self._upsert_custom_schema_entry(entry)
    except Exception as e:
      Log.error(self.LOG_TAG, "Add custom field validation failed.", {"error": str(e)})
      messagebox.showerror("Invalid", str(e))
      return
    self._save_and_refresh(schema_changed=True)
    Log.ok(self.LOG_TAG, "Added/updated custom field.", {
      "key": str(entry.get("key") or ""),
      "target": self._normalize_custom_target(entry.get("target")),
      "type": self._normalize_custom_type(entry.get("type")),
    })
    try:
      self.custom_schema_tree.selection_set(f"custom:{entry['key']}")
      self.custom_schema_tree.focus(f"custom:{entry['key']}")
      self.custom_schema_tree.see(f"custom:{entry['key']}")
    except Exception:
      pass

  def _on_custom_schema_update_selected(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Update custom field blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    field_ids = self._get_selected_field_ids()
    if not field_ids:
      Log.warn(self.LOG_TAG, "Update custom field requested with no selection.")
      messagebox.showinfo("Update", "Select a field row first.")
      return
    if len(field_ids) != 1:
      Log.warn(self.LOG_TAG, "Update custom field requires single selection.", {"selected_count": len(field_ids)})
      messagebox.showwarning("Update", "Please select exactly ONE field row to update.")
      return
    field_id = field_ids[0]
    field_entry = dict(self._field_registry_map.get(field_id) or {})
    if str(field_entry.get("kind") or "") == "system":
      self._set_builtin_field_enabled(field_id, bool(self.var_field_enabled.get()))
      self._save_and_refresh(schema_changed=True)
      Log.ok(self.LOG_TAG, "Updated built-in field visibility.", {"id": field_id, "enabled": bool(self.var_field_enabled.get())})
      try:
        self.custom_schema_tree.selection_set(field_id)
        self.custom_schema_tree.focus(field_id)
        self.custom_schema_tree.see(field_id)
      except Exception:
        pass
      return
    keys = self._get_selected_custom_schema_keys()
    if not keys:
      Log.warn(self.LOG_TAG, "Update custom field requested with no selection.")
      messagebox.showinfo("Update", "Select a custom field row first.")
      return
    if len(keys) != 1:
      Log.warn(self.LOG_TAG, "Update custom field requires single selection.", {"selected_count": len(keys)})
      messagebox.showwarning("Update", "Please select exactly ONE custom field row to update.")
      return
    old_key = keys[0]
    old_entry = dict(self._custom_field_schema_map.get(old_key) or {})
    try:
      entry = self._read_custom_schema_form()
      self._upsert_custom_schema_entry(entry, replacing_key=old_key)
      self._rename_custom_schema_key_in_values(old_key, entry["key"], target=old_entry.get("target"))
      if self._normalize_custom_type(entry.get("type")) != self._normalize_custom_type(old_entry.get("type")):
        self._remove_custom_schema_keys_from_values([entry["key"]], target=entry.get("target"))
      elif self._normalize_custom_target(entry.get("target")) != self._normalize_custom_target(old_entry.get("target")):
        self._remove_custom_schema_keys_from_values([entry["key"]], target=old_entry.get("target"))
      elif self._normalize_custom_type(entry.get("type")) == CUSTOM_TYPE_ENUM:
        enum_set = set(self._normalize_enum_values(entry.get("enum", [])))
        if self._normalize_custom_target(entry.get("target")) == CUSTOM_TARGET_TRANSACTION:
          for tx in (self.transactions or []):
            values = dict(getattr(tx, "custom_fields", {}) or {})
            cur = values.get(entry["key"], None)
            if cur is not None and enum_set and str(cur) not in enum_set:
              values.pop(entry["key"], None)
              tx.custom_fields = values
        else:
          for alias in (self.aliases_list or []):
            values = dict(alias.get("custom_fields") or {})
            cur = values.get(entry["key"], None)
            if cur is not None and enum_set and str(cur) not in enum_set:
              values.pop(entry["key"], None)
              alias["custom_fields"] = values
    except Exception as e:
      Log.error(self.LOG_TAG, "Update custom field validation failed.", {"key": old_key, "error": str(e)})
      messagebox.showerror("Invalid", str(e))
      return
    self._save_and_refresh(schema_changed=True)
    Log.ok(self.LOG_TAG, "Updated custom field.", {"from": old_key, "to": str(entry.get("key") or old_key)})
    try:
      self.custom_schema_tree.selection_set(f"custom:{entry['key']}")
      self.custom_schema_tree.focus(f"custom:{entry['key']}")
      self.custom_schema_tree.see(f"custom:{entry['key']}")
    except Exception:
      pass

  def _on_custom_schema_delete_selected(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Delete custom fields blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return
    field_ids = self._get_selected_field_ids()
    keys = self._get_selected_custom_schema_keys()
    if not field_ids:
      Log.warn(self.LOG_TAG, "Delete custom fields requested with no selection.")
      messagebox.showinfo("Delete", "Select one or more field rows first.")
      return
    if len(field_ids) == 1:
      field_entry = dict(self._field_registry_map.get(field_ids[0]) or {})
      if str(field_entry.get("kind") or "") == "system":
        if not bool(field_entry.get("removable")):
          messagebox.showwarning("Delete", "That built-in field is locked.")
          return
        if not messagebox.askyesno("Hide Built-in Field", f"Hide built-in field '{field_entry.get('label')}'?"):
          return
        self._set_builtin_field_enabled(field_ids[0], False)
        self._save_and_refresh(schema_changed=True)
        Log.warn(self.LOG_TAG, "Disabled built-in field.", {"id": field_ids[0]})
        return
    preview = ", ".join(keys[:8])
    if len(keys) > 8:
      preview += f", ... (+{len(keys) - 8} more)"
    if not messagebox.askyesno("Delete Custom Field", f"Delete {len(keys)} selected custom field(s)?\n\nFields: {preview}"):
      Log.warn(self.LOG_TAG, "Delete custom fields canceled by user.", {"count": len(keys)})
      return
    entries = [dict(self._custom_field_schema_map.get(k) or {}) for k in keys]
    self.custom_fields_schema = [x for x in (self.custom_fields_schema or []) if str(x.get("key") or "").strip() not in set(keys)]
    for entry in entries:
      if str(entry.get("key") or "").strip():
        self._remove_custom_schema_keys_from_values([str(entry.get("key") or "").strip()], target=entry.get("target"))
    self._save_and_refresh(schema_changed=True)
    self.var_custom_schema_key.set("")
    self._custom_schema_enum_values = []
    self._refresh_custom_schema_enum_summary()
    self.var_custom_schema_description.set("")
    self.var_custom_schema_target.set(CUSTOM_TARGET_ALIAS)
    self.var_custom_schema_type.set(CUSTOM_TYPE_STRING)
    try:
      getattr(self, "_sync_custom_schema_enum_state", lambda: None)()
    except Exception:
      pass
    Log.warn(self.LOG_TAG, "Deleted custom fields.", {"count": len(keys), "keys": keys})

  def _on_delete_selected(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Delete transactions blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    ids = self._get_selected_tx_ids()
    if not ids:
      Log.warn(self.LOG_TAG, "Delete transactions requested with no selection.")
      messagebox.showinfo("Delete", "Select one or more transaction rows first.")
      return

    preview = ", ".join(str(x) for x in ids[:10])
    if len(ids) > 10:
      preview += f", … (+{len(ids) - 10} more)"

    if not messagebox.askyesno("Delete", f"Delete {len(ids)} selected transaction(s)?\n\nIDs: {preview}"):
      Log.warn(self.LOG_TAG, "Delete transactions canceled by user.", {"count": len(ids)})
      return

    id_set = set(ids)
    before = len(self.transactions)
    self.transactions = [t for t in self.transactions if t.id not in id_set]
    after = len(self.transactions)

    self._save_and_refresh(schema_changed=True)
    Log.warn(self.LOG_TAG, "Deleted transactions.", {"count": (before - after), "ids": ids})

  def _load_selected_into_form(self) -> None:
    sel = self._get_selected_tx_id()
    if sel is None:
      return
    tx = next((t for t in self.transactions if t.id == sel), None)
    if not tx:
      return

    self.var_date.set(tx.date)
    self.var_sku.set(tx.sku)
    self.var_type.set(tx.type)
    self.var_qty.set(str(tx.qty))
    self.var_purchase_unit.set(f"{tx.purchase_unit_cost:.2f}")
    self.var_sale_unit.set(f"{tx.sale_unit_price:.2f}")

    if tx.type == TX_PURCHASE:
      self.var_unit_price.set(self.var_purchase_unit.get())
      self._last_type_for_unit = TX_PURCHASE
    else:
      self.var_unit_price.set(self.var_sale_unit.get())
      self._last_type_for_unit = TX_SALE

    self.var_note.set(tx.note or "")
    self._sync_type_fields()
    self._sync_alias_choice_from_sku()
    self._update_tx_custom_fields_editor_values(tx)

  def _read_form_to_transaction(self, existing_id: Optional[int]) -> Transaction:
    date = parse_date(self.var_date.get())
    sku = (self.var_sku.get() or "").strip()
    if not sku:
      raise ValueError("SKU is required")

    ttype = self.var_type.get()
    if ttype not in (TX_PURCHASE, TX_SALE):
      raise ValueError("Type must be PURCHASE or SALE")

    try:
      qty = int(self.var_qty.get())
    except:
      raise ValueError("Qty must be an integer")
    if qty <= 0:
      raise ValueError("Qty must be > 0")

    purchase_unit = 0.0
    sale_unit = 0.0

    if ttype == TX_PURCHASE:
      try:
        purchase_unit = float(self.var_unit_price.get())
      except:
        raise ValueError("Purchase Unit Cost must be a number")
      if purchase_unit < 0:
        raise ValueError("Purchase Unit Cost must be >= 0")
    else:
      try:
        sale_unit = float(self.var_unit_price.get())
      except:
        raise ValueError("Sale Unit Price must be a number")
      if sale_unit < 0:
        raise ValueError("Sale Unit Price must be >= 0")

    note = (self.var_note.get() or "").strip()
    custom_fields = self._read_target_custom_field_form("_tx_custom_field_widgets")

    if existing_id is None:
      tx_id = self.next_id
      self.next_id += 1
      created_order = self.next_created_order
      self.next_created_order += 1
    else:
      tx_id = existing_id
      created_order = 0  # overwritten by caller

    return Transaction(
      id=tx_id,
      date=date,
      sku=sku,
      type=ttype,
      qty=qty,
      purchase_unit_cost=purchase_unit,
      sale_unit_price=sale_unit,
      note=note,
      created_order=created_order,
      custom_fields=custom_fields,
    )

  # -----------------------------------------------------------------------------
  # Refresh / Sort
  # -----------------------------------------------------------------------------

  def _normalize_sort(self) -> None:
    self.transactions.sort(key=lambda t: (t.date, t.created_order, t.id))

  def _refresh_all(self) -> None:
    Log.info(self.LOG_TAG, "Refreshing computed views.", {"tx_count": len(self.transactions)})
    rows, overview = self.engine.compute(self.transactions)
    self._refresh_tx_table(rows)
    self._refresh_overview_table(overview, rows)
    Log.info(self.LOG_TAG, "Refreshed computed views.", {
      "row_count": len(rows),
      "overview_sku_count": len(overview),
    })

  def _refresh_tx_table(self, rows: List[Dict[str, Any]]) -> None:
    # If a hover-tooltip is currently visible, kill it before rebuilding rows.
    try:
      if hasattr(self, "_tx_tree_tip_hide") and callable(self._tx_tree_tip_hide):
        self._tx_tree_tip_hide()
    except Exception:
      pass

    all_custom_entries = self._get_all_custom_schema_in_display_order()
    tx_custom_columns = [str(x.get("key") or "").strip() for x in all_custom_entries if str(x.get("key") or "").strip()]
    tx_builtin_columns = self._get_visible_builtin_keys(FIELD_SCOPE_TX_TABLE)
    alias_idx = tx_builtin_columns.index("alias") if "alias" in tx_builtin_columns else min(len(tx_builtin_columns), 3)
    columns = tx_builtin_columns[:alias_idx + 1] + tx_custom_columns + tx_builtin_columns[alias_idx + 1:]
    headings = {
      "id": "ID",
      "date": "Date",
      "sku": "SKU",
      "alias": "Alias",
      "type": "Type",
      "qty": "Qty",
      "purchase_unit_cost": "Purchase Unit Cost",
      "sale_unit_price": "Sale Unit Price",
      "purchase_total_cost": "Purchase Total Cost",
      "prev_avg_cost": "Prev Avg Cost",
      "onhand_qty": "OnHand Qty",
      "avg_cost_after": "Avg Cost",
      "cogs": "COGS",
      "onhand_cost": "OnHand Cost",
      "sales_rev": "Sales Rev",
      "gross_profit": "Gross Profit",
      "note": "Note",
    }
    widths = {
      "id": 60, "date": 120, "sku": 200, "alias": 260, "type": 120, "qty": 80,
      "purchase_unit_cost": 165, "sale_unit_price": 145,
      "purchase_total_cost": 175, "prev_avg_cost": 145,
      "onhand_qty": 120, "avg_cost_after": 130,
      "cogs": 130, "onhand_cost": 155, "sales_rev": 140, "gross_profit": 180,
      "note": 380,
    }
    col_anchor = {
      "id": "center",
      "date": "w",
      "sku": "w",
      "alias": "w",
      "type": "center",
      "qty": "e",
      "purchase_unit_cost": "e",
      "sale_unit_price": "e",
      "purchase_total_cost": "e",
      "prev_avg_cost": "e",
      "onhand_qty": "e",
      "avg_cost_after": "e",
      "cogs": "e",
      "onhand_cost": "e",
      "sales_rev": "e",
      "gross_profit": "e",
      "note": "w",
    }
    for entry in all_custom_entries:
      key = str(entry.get("key") or "").strip()
      if key:
        headings[key] = key
        widths[key] = 150
        col_anchor[key] = "center" if self._normalize_custom_type(entry.get("type")) == CUSTOM_TYPE_BOOLEAN else "w"

    self.tx_tree["columns"] = columns
    heading_gutter = "  "
    for ci, c in enumerate(columns):
      base_text = headings.get(c, c)
      head_text = (f"{base_text}{heading_gutter}" if ci < (len(columns) - 1) else base_text)
      anchor = col_anchor.get(c, "w")
      self.tx_tree.heading(c, text=head_text, anchor=("center" if anchor == "center" else ("e" if anchor == "e" else "w")))
      self.tx_tree.column(c, width=widths.get(c, 120), minwidth=32, anchor=anchor, stretch=False)

    self.tx_tree.delete(*self.tx_tree.get_children())

    # Most recent first (date DESC). Tie-breaker: higher ID first.
    rows_sorted = sorted(
      rows,
      key=lambda r: (str(r.get("date", "")), int(r.get("id", 0) or 0)),
      reverse=True,
    )

    for i, r in enumerate(rows_sorted):
      # Fake "cell padding" for left-aligned text fields (Treeview has no per-cell padding on Windows ttk)
      pad_l = "  "  # 2 spaces

      sku = str(r.get("sku") or "").strip()
      alias = self._get_alias_for_sku(sku)
      tx_custom_values = dict(r.get("custom_fields") or {})
      alias_item = next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == sku), None)
      alias_custom_values = dict((alias_item or {}).get("custom_fields") or {})
      builtin_value_map = {
        "id": r["id"],
        "date": f"{pad_l}{r['date']}",
        "sku": f"{pad_l}{sku}",
        "alias": f"{pad_l}{alias}" if alias else "",
        "type": r["type"],
        "qty": r["qty"],
        "purchase_unit_cost": money(r["purchase_unit_cost"]) if r["type"] == TX_PURCHASE else "",
        "sale_unit_price": money(r["sale_unit_price"]) if r["type"] == TX_SALE else "",
        "purchase_total_cost": money(r["purchase_total_cost"]) if r["type"] == TX_PURCHASE else money(0.0),
        "prev_avg_cost": money(r["prev_avg_cost"]),
        "onhand_qty": r["onhand_qty"],
        "avg_cost_after": money(r["avg_cost_after"]),
        "cogs": money(r["cogs"]),
        "onhand_cost": money(r["onhand_cost"]),
        "sales_rev": money(r["sales_rev"]),
        "gross_profit": money(r["gross_profit"]),
        "note": f"{pad_l}{(r['note'] or '')}" if (r["note"] or "") else "",
      }
      values_list: List[Any] = []
      for col in tx_builtin_columns[:alias_idx + 1]:
        values_list.append(builtin_value_map.get(col, ""))
      for entry in self._get_all_custom_schema_in_display_order():
        key = str(entry.get("key") or "").strip()
        target = self._normalize_custom_target(entry.get("target"))
        source_values = tx_custom_values if target == CUSTOM_TARGET_TRANSACTION else alias_custom_values
        values_list.append(self._format_custom_field_value(entry, source_values.get(key, None)))
      for col in tx_builtin_columns[alias_idx + 1:]:
        values_list.append(builtin_value_map.get(col, ""))
      values = tuple(values_list)

      # Zebra striping + "error" tint when inventory goes negative after this row
      is_even = (i % 2) == 0
      zebra_tag = "even" if is_even else "odd"

      tag = zebra_tag
      if int(r.get("onhand_qty", 0) or 0) < 0:
        tag = "status_error_even" if is_even else "status_error_odd"

      self.tx_tree.insert("", "end", iid=str(r["id"]), values=values, tags=(tag,))

    # Keep "Update Selected" disabled unless exactly one row is selected.
    try:
      self._sync_tx_update_selected_state()
    except Exception:
      pass

  # ---------------------------------------------------------------------------
  # Overview view (Inventory vs Monthly)
  # ---------------------------------------------------------------------------

  def _on_overview_view_changed(self) -> None:
    self._configure_overview_tree_for_view()
    self._refresh_all()

  def _configure_overview_tree_for_view(self) -> None:
    mode = (self.ov_view_var.get() or "Inventory").strip()

    if mode == "Monthly":
      columns = ["month", "month_date", "purchase_cost", "sales_amount", "cogs"]
      headings = {
        "month": "Month",
        "month_date": "Month Date",
        "purchase_cost": "Purchase Cost",
        "sales_amount": "Sales Amount",
        "cogs": "COGS",
      }
      widths = {
        "month": 140,
        "month_date": 140,
        "purchase_cost": 170,
        "sales_amount": 170,
        "cogs": 150,
      }
      col_anchor = {
        "month": "w",
        "month_date": "w",
        "purchase_cost": "e",
        "sales_amount": "e",
        "cogs": "e",
      }
    else:
      alias_custom_entries = self._get_custom_schema_for_target(CUSTOM_TARGET_ALIAS)
      custom_cols = [str(x.get("key") or "").strip() for x in alias_custom_entries if str(x.get("key") or "").strip()]
      builtin_cols = self._get_visible_builtin_keys(FIELD_SCOPE_OVERVIEW_INVENTORY)
      alias_idx = builtin_cols.index("alias") if "alias" in builtin_cols else min(len(builtin_cols), 2)
      columns = builtin_cols[:alias_idx + 1] + custom_cols + builtin_cols[alias_idx + 1:]
      headings = {
        "sku": "SKU",
        "alias": "Alias",
        "onhand_qty": "OnHand Qty",
        "avg_cost": "Avg Cost",
        "onhand_cost": "OnHand Cost",
        "last_tx_date": "Last Tx Date",
        "last_sale_price": "Last Sale Price",
        "status": "Status",
      }
      for c in custom_cols:
        headings[c] = c
      widths = {
        "sku": 220,
        "alias": 260,
        "onhand_qty": 120,
        "avg_cost": 120,
        "onhand_cost": 170,
        "last_tx_date": 150,
        "last_sale_price": 150,
        "status": 220,
      }
      for c in custom_cols:
        widths[c] = 150
      col_anchor = {
        "sku": "w",
        "alias": "w",
        "onhand_qty": "e",
        "avg_cost": "e",
        "onhand_cost": "e",
        "last_tx_date": "w",
        "last_sale_price": "e",
        "status": "center",
      }
      for c in custom_cols:
        schema = self._custom_field_schema_map.get(c, {})
        col_anchor[c] = "center" if self._normalize_custom_type(schema.get("type")) == CUSTOM_TYPE_BOOLEAN else "w"

    # Apply column set
    self.ov_tree["columns"] = columns

    head_anchor = {
      k: ("center" if v == "center" else ("e" if v == "e" else "w"))
      for k, v in col_anchor.items()
    }

    heading_gutter = "  "  # visual separation between adjacent headers

    for ci, c in enumerate(columns):
      base_text = headings.get(c, c)
      head_text = (f"{base_text}{heading_gutter}" if ci < (len(columns) - 1) else base_text)

      self.ov_tree.heading(
        c,
        text=head_text,
        anchor=head_anchor.get(c, "w"),
      )
      self.ov_tree.column(
        c,
        width=widths.get(c, 120),
        minwidth=32,
        anchor=col_anchor.get(c, "w"),
        stretch=(mode == "Monthly"),
      )

    # Fit after reconfig
    try:
      if hasattr(self, "_ov_fit_columns_now") and callable(self._ov_fit_columns_now):
        self.after(1, self._ov_fit_columns_now)
    except Exception:
      pass

  def _compute_monthly_report_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build month aggregate rows from computed per-transaction rows.

    Columns:
      - month: YYYY-MM
      - month_date: YYYY-MM-01
      - purchase_cost: sum(purchase_total_cost) for PURCHASE rows
      - sales_amount: sum(sales_rev) for SALE rows
      - cogs: sum(cogs) for SALE rows
    """
    bucket: Dict[str, Dict[str, float]] = {}

    for r in (rows or []):
      d = str(r.get("date") or "")
      if len(d) < 7:
        continue
      month = d[:7]

      if month not in bucket:
        bucket[month] = {"purchase_cost": 0.0, "sales_amount": 0.0, "cogs": 0.0}

      if r.get("type") == TX_PURCHASE:
        bucket[month]["purchase_cost"] += float(r.get("purchase_total_cost") or 0.0)
      elif r.get("type") == TX_SALE:
        bucket[month]["sales_amount"] += float(r.get("sales_rev") or 0.0)
        bucket[month]["cogs"] += float(r.get("cogs") or 0.0)

    out: List[Dict[str, Any]] = []
    for month in sorted(bucket.keys(), reverse=True):
      out.append({
        "month": month,
        "month_date": f"{month}-01",
        "purchase_cost": float(bucket[month]["purchase_cost"]),
        "sales_amount": float(bucket[month]["sales_amount"]),
        "cogs": float(bucket[month]["cogs"]),
      })
    return out

  def _refresh_overview_table(self, overview: Dict[str, Dict[str, Any]], rows: List[Dict[str, Any]]) -> None:
    mode = (self.ov_view_var.get() or "Inventory").strip()
    if mode == "Monthly":
      month_rows = self._compute_monthly_report_rows(rows)
      self._refresh_overview_table_monthly(month_rows)
    else:
      self._refresh_overview_table_inventory(overview)

  def _refresh_overview_table_inventory(self, overview: Dict[str, Dict[str, Any]]) -> None:
    try:
      if hasattr(self, "_ov_tree_tip_hide") and callable(self._ov_tree_tip_hide):
        self._ov_tree_tip_hide()
    except Exception:
      pass

    self.ov_tree.delete(*self.ov_tree.get_children())

    def _ov_sort_key(sku_key: str):
      s = overview.get(sku_key) or {}
      qty = int(s.get("onhand_qty", 0) or 0)
      status = str(s.get("status") or "").strip().upper()

      # Group order:
      #   0 = NEGATIVE (top)
      #   1 = IN STOCK
      #   2 = OUT (bottom)
      if qty < 0 or "NEGATIVE" in status:
        grp = 0
      elif qty == 0 or status == "OUT":
        grp = 2
      else:
        grp = 1

      sku_norm = str(s.get("sku") or sku_key or "").strip()
      alias = self._get_alias_for_sku(sku_norm)
      alias_norm = str(alias or "").strip().lower()
      sku_norm_l = sku_norm.lower()

      # Within NEGATIVE: most negative first (e.g., -10 before -1)
      neg_qty_key = qty if grp == 0 else 0

      return (grp, neg_qty_key, alias_norm, sku_norm_l)

    sorted_skus = sorted(overview.keys(), key=_ov_sort_key)

    for i, sku in enumerate(sorted_skus):
      s = overview[sku]
      pad_l = "  "  # 2 spaces

      alias = self._get_alias_for_sku(str(s.get("sku") or "").strip())

      values_list: List[Any] = []
      overview_builtin_cols = self._get_visible_builtin_keys(FIELD_SCOPE_OVERVIEW_INVENTORY)
      if "sku" in overview_builtin_cols:
        values_list.append(f"{pad_l}{s['sku']}")
      if "alias" in overview_builtin_cols:
        values_list.append(f"{pad_l}{alias}" if alias else "")
      alias_item = next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == str(s.get("sku") or "").strip()), None)
      alias_custom_values = dict((alias_item or {}).get("custom_fields") or {})
      for entry in self._get_custom_schema_for_target(CUSTOM_TARGET_ALIAS):
        key = str(entry.get("key") or "").strip()
        values_list.append(self._format_custom_field_value(entry, alias_custom_values.get(key, None)))
      builtin_value_map = {
        "onhand_qty": s["onhand_qty"],
        "avg_cost": money(s["avg_cost"]),
        "onhand_cost": money(s["onhand_cost"]),
        "last_tx_date": f"{pad_l}{s['last_tx_date']}" if s["last_tx_date"] else "",
        "last_sale_price": money(s["last_sale_price"]) if s["last_sale_price"] else "",
        "status": s["status"],
      }
      for col in overview_builtin_cols:
        if col in ("sku", "alias"):
          continue
        values_list.append(builtin_value_map.get(col, ""))
      values = tuple(values_list)

      is_even = (i % 2) == 0
      zebra_tag = "even" if is_even else "odd"

      tag = zebra_tag
      status = str(s.get("status") or "").strip().upper()
      if "NEGATIVE" in status or int(s.get("onhand_qty", 0) or 0) < 0:
        tag = "status_error_even" if is_even else "status_error_odd"
      elif status == "IN STOCK":
        tag = "status_done_even" if is_even else "status_done_odd"

      self.ov_tree.insert("", "end", iid=sku, values=values, tags=(tag,))

  def _refresh_overview_table_monthly(self, month_rows: List[Dict[str, Any]]) -> None:
    try:
      if hasattr(self, "_ov_tree_tip_hide") and callable(self._ov_tree_tip_hide):
        self._ov_tree_tip_hide()
    except Exception:
      pass

    self.ov_tree.delete(*self.ov_tree.get_children())

    for i, r in enumerate(month_rows or []):
      pad_l = "  "  # 2 spaces

      values = (
        f"{pad_l}{r['month']}",
        f"{pad_l}{r['month_date']}",
        money(float(r.get("purchase_cost") or 0.0)),
        money(float(r.get("sales_amount") or 0.0)),
        money(float(r.get("cogs") or 0.0)),
      )

      is_even = (i % 2) == 0
      tag = "even" if is_even else "odd"
      self.ov_tree.insert("", "end", iid=str(r["month"]), values=values, tags=(tag,))

  def _export_overview_csv(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Overview CSV export blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    mode = (self.ov_view_var.get() or "Inventory").strip()
    initialfile = "overview_monthly.csv" if mode == "Monthly" else "overview_inventory.csv"

    path = filedialog.asksaveasfilename(
      title="Export CSV",
      defaultextension=".csv",
      filetypes=[("CSV", "*.csv")],
      initialfile=initialfile,
      initialdir=self.project_dir or None,
    )
    if not path:
      Log.warn(self.LOG_TAG, "Overview CSV export canceled.")
      return

    rows, overview = self.engine.compute(self.transactions)

    if mode == "Monthly":
      data_rows = self._compute_monthly_report_rows(rows)
      headers = ["month", "month_date", "purchase_cost", "sales_amount", "cogs"]
    else:
      alias_custom_entries = self._get_custom_schema_for_target(CUSTOM_TARGET_ALIAS)
      custom_headers = [str(x.get("key") or "").strip() for x in alias_custom_entries if str(x.get("key") or "").strip()]
      overview_builtin_headers = self._get_visible_builtin_keys(FIELD_SCOPE_OVERVIEW_INVENTORY)
      data_rows = []
      for sku in sorted(overview.keys()):
        s = overview[sku]
        row = {
          "sku": s["sku"],
          "alias": self._get_alias_for_sku(str(s.get("sku") or "").strip()),
          "onhand_qty": s["onhand_qty"],
          "avg_cost": float(s["avg_cost"]),
          "onhand_cost": float(s["onhand_cost"]),
          "last_tx_date": s["last_tx_date"],
          "last_sale_price": float(s["last_sale_price"]),
          "status": s["status"],
        }
        alias_item = next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == str(s.get("sku") or "").strip()), None)
        alias_custom_values = dict((alias_item or {}).get("custom_fields") or {})
        for entry in alias_custom_entries:
          key = str(entry.get("key") or "").strip()
          row[key] = self._format_custom_field_value(entry, alias_custom_values.get(key, None))
        data_rows.append(row)
      alias_idx = overview_builtin_headers.index("alias") if "alias" in overview_builtin_headers else min(len(overview_builtin_headers), 2)
      headers = overview_builtin_headers[:alias_idx + 1] + custom_headers + overview_builtin_headers[alias_idx + 1:]

    try:
      with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(headers) + "\n")
        for r in data_rows:
          line = []
          for h in headers:
            v = r.get(h, "")
            if isinstance(v, str):
              if "," in v or '"' in v:
                v = '"' + v.replace('"', '""') + '"'
              line.append(v)
            else:
              line.append(str(v))
          f.write(",".join(line) + "\n")
      Log.ok(self.LOG_TAG, "Exported overview CSV.", {"path": path, "mode": mode})
      messagebox.showinfo("Export", f"Exported to:\n{path}")
    except Exception as e:
      Log.error(self.LOG_TAG, "Overview CSV export failed.", {"error": str(e)})
      messagebox.showerror("Export Failed", str(e))

  # -----------------------------------------------------------------------------
  # Selection Helpers
  # -----------------------------------------------------------------------------

  def _set_ctk_button_enabled(self, btn: Any, enabled: bool) -> None:
    """Enable/disable a CTkButton-like widget (best-effort)."""
    if btn is None:
      return
    try:
      btn.configure(state=("normal" if enabled else "disabled"))
    except Exception:
      pass

  def _sync_tx_update_selected_state(self) -> None:
    """Disable Transactions 'Update Selected' unless exactly one row is selected."""
    try:
      has_project = bool(self.project_data_path)
      sel_count = len(self._get_selected_tx_ids())
      self._set_ctk_button_enabled(getattr(self, "btn_update", None), bool(has_project and sel_count == 1))
    except Exception:
      pass

  def _sync_alias_update_selected_state(self) -> None:
    """Disable Aliases 'Update Selected' unless exactly one row is selected."""
    try:
      has_project = bool(self.project_data_path)
      sel_count = len(self._get_selected_alias_skus())
      self._set_ctk_button_enabled(getattr(self, "btn_alias_update", None), bool(has_project and sel_count == 1))
    except Exception:
      pass

  def _sync_update_selected_buttons_state(self) -> None:
    """Sync all 'Update Selected' button states across views (best-effort)."""
    self._sync_tx_update_selected_state()
    self._sync_alias_update_selected_state()
    self._sync_custom_schema_update_selected_state()

  def _get_selected_tx_id(self) -> Optional[int]:

    """
    Get the "primary" selected transaction ID.
    Keeps legacy single-select call sites working.
    """
    ids = self._get_selected_tx_ids()
    return ids[0] if ids else None

  def _get_selected_tx_ids(self) -> List[int]:
    """
    Get all selected transaction IDs (extended selection).
    Returns a sorted list of ints.
    """
    sel = self.tx_tree.selection()
    if not sel:
      return []
    out: List[int] = []
    for iid in sel:
      try:
        out.append(int(iid))
      except Exception:
        pass
    out = sorted(set(out))
    return out

  def _select_tx_id(self, tx_id: int) -> None:
    iid = str(tx_id)
    if self.tx_tree.exists(iid):
      self.tx_tree.selection_set(iid)
      self.tx_tree.focus(iid)
      self.tx_tree.see(iid)

  # -----------------------------------------------------------------------------
  # Export
  # -----------------------------------------------------------------------------

  def _export_csv(self) -> None:
    if not self.project_data_path:
      Log.error(self.LOG_TAG, "Transactions CSV export blocked: no project selected.")
      messagebox.showerror("Project", "Select a Project Directory first.")
      return

    path = filedialog.asksaveasfilename(
      title="Export CSV",
      defaultextension=".csv",
      filetypes=[("CSV", "*.csv")],
      initialfile="transactions_export.csv",
      initialdir=self.project_dir or None,
    )
    if not path:
      Log.warn(self.LOG_TAG, "Transactions CSV export canceled.")
      return

    rows, _ = self.engine.compute(self.transactions)

    tx_custom_headers = [str(x.get("key") or "").strip() for x in self._get_all_custom_schema_in_display_order() if str(x.get("key") or "").strip()]
    tx_builtin_headers = self._get_visible_builtin_keys(FIELD_SCOPE_TX_TABLE)
    alias_idx = tx_builtin_headers.index("alias") if "alias" in tx_builtin_headers else min(len(tx_builtin_headers), 3)
    headers = tx_builtin_headers[:alias_idx + 1] + tx_custom_headers + tx_builtin_headers[alias_idx + 1:]

    try:
      with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(headers) + "\n")
        for r in rows:
          # add alias on the fly (not part of engine rows)
          sku = str(r.get("sku") or "").strip()
          r2 = dict(r)
          r2["alias"] = self._get_alias_for_sku(sku)
          tx_custom_values = dict(r.get("custom_fields") or {})
          alias_item = next((a for a in (self.aliases_list or []) if str(a.get("sku") or "").strip() == sku), None)
          alias_custom_values = dict((alias_item or {}).get("custom_fields") or {})
          for entry in self._get_all_custom_schema_in_display_order():
            key = str(entry.get("key") or "").strip()
            target = self._normalize_custom_target(entry.get("target"))
            source_values = tx_custom_values if target == CUSTOM_TARGET_TRANSACTION else alias_custom_values
            r2[key] = self._format_custom_field_value(entry, source_values.get(key, None))

          line = []
          for h in headers:
            v = r2.get(h, "")
            if isinstance(v, str):
              if "," in v or '"' in v:
                v = '"' + v.replace('"', '""') + '"'
              line.append(v)
            else:
              line.append(str(v))
          f.write(",".join(line) + "\n")
      Log.ok(self.LOG_TAG, "Exported CSV.", {"path": path})
      messagebox.showinfo("Export", f"Exported to:\n{path}")
    except Exception as e:
      Log.error(self.LOG_TAG, "CSV export failed.", {"error": str(e)})
      messagebox.showerror("Export Failed", str(e))


# =============================================================================
# [🚀 Main]
# =============================================================================

def main() -> None:
  # Must happen early for best taskbar behavior on Windows.
  set_windows_app_user_model_id(APP_USER_MODEL_ID)

  app = InventoryApp()
  app.mainloop()

if __name__ == "__main__":
  main()
