"""Video-pane state and portable split layouts, independent of the GUI.

Layouts are ordinary JSON-compatible trees. Horizontal branches arrange their
children from left to right; vertical branches arrange them from top to bottom.
All public layout operations copy their input so callers can retain snapshots.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from math import ceil, isfinite, sqrt
from typing import Any
from uuid import uuid4


MAX_PANES = 64
MAX_DEPTH = 64
MAX_POSITION_MS = 2**53 - 1
FORMAT = "gridstudio"
VERSION = 1
PRESETS = ("grid", "columns", "rows", "focus-left", "focus-top")

Tree = dict[str, Any] | None


def _identifier(value: Any, name: str = "pane id") -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{name} must be a nonempty string of at most 128 characters")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{name} must not contain control characters")
    return value


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be finite and between {minimum} and {maximum}")
    return number


@dataclass
class PaneState:
    """The full state copied when duplicating a video pane."""

    id: str = field(default_factory=lambda: uuid4().hex)
    source: str = ""
    rotation: int = 0
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    fit_mode: str = "contain"
    flip_h: bool = False
    flip_v: bool = False
    position_ms: int = 0
    rate: float = 1.0
    volume: float = 0.5
    muted: bool = True
    loop: bool = True
    loop_start_ms: int = 0
    loop_end_ms: int | None = None
    paused: bool = True
    sync_group: str = ""
    sync_mode: str = "time"
    sync_offset_ms: int = 0
    canvas_rect: tuple[float, float, float, float] | None = None
    z_order: int = 0

    def clone(self) -> PaneState:
        """Copy source, transforms and playback state, with a new identity."""
        duplicate = deepcopy(self)
        duplicate.id = uuid4().hex
        return duplicate

    def to_dict(self) -> dict[str, Any]:
        """Return a validated, independently owned JSON-compatible value."""
        raw = {item.name: deepcopy(getattr(self, item.name)) for item in fields(self)}
        normalized = type(self).from_dict(raw)
        result = {item.name: getattr(normalized, item.name) for item in fields(self)}
        result["crop"] = list(normalized.crop)
        result["canvas_rect"] = list(normalized.canvas_rect) if normalized.canvas_rect is not None else None
        return result

    @classmethod
    def from_dict(cls, data: Any) -> PaneState:
        if not isinstance(data, dict):
            raise ValueError("a pane must be an object")
        valid_names = {item.name for item in fields(cls)}
        if set(data) - valid_names:
            raise ValueError("a pane contains unknown fields")
        if "id" not in data:
            raise ValueError("a saved pane must have an id")

        state = cls()
        state.id = _identifier(data["id"])
        source = data.get("source", state.source)
        if not isinstance(source, str) or len(source) > 32768 or "\0" in source:
            raise ValueError("source must be a string of at most 32768 characters without NUL")
        state.source = source
        rotation = data.get("rotation", state.rotation)
        if type(rotation) is not int or rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180, or 270")
        state.rotation = rotation

        crop = data.get("crop", state.crop)
        if not isinstance(crop, (tuple, list)) or len(crop) != 4:
            raise ValueError("crop must contain x, y, width, and height")
        x, y, width, height = (
            _number(value, f"crop {name}", 0.0, 1.0)
            for value, name in zip(crop, ("x", "y", "width", "height"))
        )
        if width <= 0 or height <= 0 or x + width > 1.0 + 1e-9 or y + height > 1.0 + 1e-9:
            raise ValueError("crop must have positive dimensions and stay inside the source")
        state.crop = (x, y, width, height)

        canvas_rect = data.get("canvas_rect", state.canvas_rect)
        if canvas_rect is not None:
            if not isinstance(canvas_rect, (tuple, list)) or len(canvas_rect) != 4:
                raise ValueError("canvas_rect must contain x, y, width, and height, or be null")
            x = _number(canvas_rect[0], "canvas x", -1.0, 2.0)
            y = _number(canvas_rect[1], "canvas y", -1.0, 2.0)
            width = _number(canvas_rect[2], "canvas width", 0.02, 3.0)
            height = _number(canvas_rect[3], "canvas height", 0.02, 3.0)
            if x >= 1.0 or y >= 1.0 or x + width <= 0.0 or y + height <= 0.0:
                raise ValueError("canvas_rect must intersect the canvas")
            state.canvas_rect = (x, y, width, height)
        z_order = data.get("z_order", state.z_order)
        if type(z_order) is not int or not -1_000_000 <= z_order <= 1_000_000:
            raise ValueError("z_order must be an integer between -1000000 and 1000000")
        state.z_order = z_order

        fit_mode = data.get("fit_mode", state.fit_mode)
        if not isinstance(fit_mode, str) or fit_mode not in ("contain", "cover", "stretch"):
            raise ValueError("fit_mode must be contain, cover, or stretch")
        state.fit_mode = fit_mode

        for name in ("flip_h", "flip_v", "muted", "loop", "paused"):
            value = data.get(name, getattr(state, name))
            if type(value) is not bool:
                raise ValueError(f"{name} must be a boolean")
            setattr(state, name, value)

        for name in ("position_ms", "loop_start_ms"):
            value = data.get(name, getattr(state, name))
            if type(value) is not int or not 0 <= value <= MAX_POSITION_MS:
                raise ValueError(f"{name} must be a nonnegative safe integer")
            setattr(state, name, value)
        loop_end = data.get("loop_end_ms", state.loop_end_ms)
        if loop_end is not None:
            if type(loop_end) is not int or not 0 <= loop_end <= MAX_POSITION_MS:
                raise ValueError("loop_end_ms must be null or a nonnegative safe integer")
            if loop_end <= state.loop_start_ms:
                raise ValueError("loop_end_ms must be greater than loop_start_ms")
        state.loop_end_ms = loop_end

        sync_group = data.get("sync_group", state.sync_group)
        if not isinstance(sync_group, str) or sync_group not in ("", "1", "2", "3", "4"):
            raise ValueError("sync_group must be empty or one of 1, 2, 3, 4")
        state.sync_group = sync_group
        sync_mode = data.get("sync_mode", state.sync_mode)
        if not isinstance(sync_mode, str) or sync_mode not in ("time", "percent"):
            raise ValueError("sync_mode must be time or percent")
        state.sync_mode = sync_mode
        sync_offset = data.get("sync_offset_ms", state.sync_offset_ms)
        if type(sync_offset) is not int or not -MAX_POSITION_MS <= sync_offset <= MAX_POSITION_MS:
            raise ValueError("sync_offset_ms must be a signed safe integer")
        state.sync_offset_ms = sync_offset
        state.rate = _number(data.get("rate", state.rate), "rate", 0.1, 8.0)
        state.volume = _number(data.get("volume", state.volume), "volume", 0.0, 1.0)
        return state


def _tree_copy(tree: Tree) -> tuple[Tree, list[str]]:
    """Validate a tree while copying it; impose limits before recursive work."""
    if tree is None:
        return None, []
    identities: list[str] = []
    seen: set[str] = set()
    node_count = 0

    def visit(node: Any, depth: int) -> dict[str, Any]:
        nonlocal node_count
        node_count += 1
        if depth > MAX_DEPTH or node_count > MAX_PANES * 2 - 1:
            raise ValueError("layout is too deep or contains too many nodes")
        if not isinstance(node, dict):
            raise ValueError("each layout node must be an object")
        if "pane" in node:
            if set(node) != {"pane"}:
                raise ValueError("a leaf must contain only its pane id")
            pane_id = _identifier(node["pane"])
            if pane_id in seen:
                raise ValueError("each pane id may appear only once in the layout")
            seen.add(pane_id)
            identities.append(pane_id)
            if len(identities) > MAX_PANES:
                raise ValueError(f"at most {MAX_PANES} panes are supported")
            return {"pane": pane_id}
        if set(node) != {"axis", "sizes", "children"}:
            raise ValueError("a branch must contain axis, sizes, and children")
        if node["axis"] not in ("horizontal", "vertical"):
            raise ValueError("layout axis must be horizontal or vertical")
        children, sizes = node["children"], node["sizes"]
        if not isinstance(children, list) or not 2 <= len(children) <= MAX_PANES:
            raise ValueError("a branch must contain between 2 and 64 children")
        if not isinstance(sizes, list) or len(sizes) != len(children):
            raise ValueError("each branch child must have a corresponding size")
        copied_sizes = [_number(size, "layout size", 1e-12, 1e12) for size in sizes]
        return {
            "axis": node["axis"],
            "sizes": copied_sizes,
            "children": [visit(child, depth + 1) for child in children],
        }

    return visit(tree, 1), identities


def leaf_ids(tree: Tree) -> list[str]:
    """Return pane ids in their visual tree order, validating the layout."""
    return _tree_copy(tree)[1]


def split_leaf(tree: Tree, pane_id: str, new_id: str, axis: str) -> Tree:
    """Place a new pane after an existing pane along the selected axis."""
    copied, identities = _tree_copy(tree)
    _identifier(pane_id)
    _identifier(new_id)
    if axis not in ("horizontal", "vertical"):
        raise ValueError("split axis must be horizontal or vertical")
    if pane_id not in identities:
        raise ValueError("the pane to split is not in the layout")
    if new_id in identities:
        raise ValueError("the new pane id is already in the layout")
    if len(identities) >= MAX_PANES:
        raise ValueError(f"at most {MAX_PANES} panes are supported")

    def split(node: dict[str, Any]) -> dict[str, Any]:
        if "pane" in node:
            if node["pane"] == pane_id:
                return {
                    "axis": axis,
                    "sizes": [1.0, 1.0],
                    "children": [node, {"pane": new_id}],
                }
            return node
        node["children"] = [split(child) for child in node["children"]]
        return node

    result = split(copied)  # type: ignore[arg-type]
    return _tree_copy(result)[0]


def remove_leaf(tree: Tree, pane_id: str) -> Tree:
    """Remove one pane and collapse branches that have only one child left."""
    copied, identities = _tree_copy(tree)
    _identifier(pane_id)
    if copied is None:
        return None
    if pane_id not in identities:
        raise ValueError("the pane to remove is not in the layout")

    def remove(node: dict[str, Any]) -> Tree:
        if "pane" in node:
            return None if node["pane"] == pane_id else node
        remaining = [
            (size, result)
            for size, child in zip(node["sizes"], node["children"])
            if (result := remove(child)) is not None
        ]
        if len(remaining) == 1:
            return remaining[0][1]
        return {
            "axis": node["axis"],
            "sizes": [size for size, _ in remaining],
            "children": [child for _, child in remaining],
        }

    return remove(copied)


def swap_leaves(tree: Tree, a: str, b: str) -> Tree:
    """Exchange pane positions while preserving branch sizes and structure."""
    copied, identities = _tree_copy(tree)
    if a not in identities or b not in identities:
        raise ValueError("both panes to swap must be in the layout")

    def swap(node: dict[str, Any]) -> None:
        if "pane" in node:
            if node["pane"] == a:
                node["pane"] = b
            elif node["pane"] == b:
                node["pane"] = a
        else:
            for child in node["children"]:
                swap(child)

    swap(copied)  # type: ignore[arg-type]
    return copied


def _branch(axis: str, children: list[dict[str, Any]], sizes: list[float] | None = None) -> Tree:
    if not children:
        return None
    if len(children) == 1:
        return children[0]
    return {"axis": axis, "sizes": sizes or [1.0] * len(children), "children": children}


def make_layout(ids: list[str], preset: str = "grid") -> Tree:
    """Build a preset using every pane, including the last incomplete grid row."""
    if preset not in PRESETS:
        raise ValueError(f"unknown layout preset: {preset}")
    if not isinstance(ids, (tuple, list)) or len(ids) > MAX_PANES:
        raise ValueError(f"ids must contain at most {MAX_PANES} pane ids")
    identities = [_identifier(pane_id) for pane_id in ids]
    if len(set(identities)) != len(identities):
        raise ValueError("pane ids must be unique")
    leaves = [{"pane": pane_id} for pane_id in identities]
    if len(leaves) <= 1:
        return leaves[0] if leaves else None
    if preset == "columns":
        return _branch("horizontal", leaves)
    if preset == "rows":
        return _branch("vertical", leaves)
    if preset in ("focus-left", "focus-top"):
        outer_axis = "horizontal" if preset == "focus-left" else "vertical"
        side_axis = "vertical" if preset == "focus-left" else "horizontal"
        side = _branch(side_axis, leaves[1:])
        return _branch(outer_axis, [leaves[0], side], [2.0, 1.0])  # type: ignore[list-item]
    columns = ceil(sqrt(len(leaves)))
    rows = [
        _branch("horizontal", leaves[index:index + columns])
        for index in range(0, len(leaves), columns)
    ]
    return _branch("vertical", rows)  # type: ignore[arg-type]


def get_layout_mode(data: Any) -> str:
    """Return the session's display mode, using the original grid for old files."""
    if not isinstance(data, dict):
        raise ValueError("a session must be an object")
    layout_mode = data.get("layout_mode", "grid")
    if not isinstance(layout_mode, str) or layout_mode not in ("grid", "canvas"):
        raise ValueError("layout_mode must be grid or canvas")
    return layout_mode


def encode_session(panes: list[PaneState], tree: Tree, *, layout_mode: str = "grid") -> dict[str, Any]:
    """Validate state and build the versioned JSON session envelope."""
    if not isinstance(panes, list) or len(panes) > MAX_PANES:
        raise ValueError(f"a session may contain at most {MAX_PANES} panes")
    if any(not isinstance(pane, PaneState) for pane in panes):
        raise ValueError("panes must contain PaneState instances")
    data = {
        "format": FORMAT,
        "version": VERSION,
        "panes": [pane.to_dict() for pane in panes],
        "layout": deepcopy(tree),
        "layout_mode": layout_mode,
    }
    restored_panes, restored_tree = decode_session(data)
    return {
        "format": FORMAT,
        "version": VERSION,
        "panes": [pane.to_dict() for pane in restored_panes],
        "layout": restored_tree,
        "layout_mode": layout_mode,
    }


def decode_session(data: Any) -> tuple[list[PaneState], Tree]:
    """Read an untrusted session without opening any of its media paths."""
    required_keys = {"format", "version", "panes", "layout"}
    if not isinstance(data, dict) or not required_keys <= set(data) or set(data) - required_keys - {"layout_mode"}:
        raise ValueError("session must contain format, version, panes, and layout")
    get_layout_mode(data)
    if data["format"] != FORMAT or type(data["version"]) is not int or data["version"] != VERSION:
        raise ValueError("unsupported session format or version")
    pane_data = data["panes"]
    if not isinstance(pane_data, list) or len(pane_data) > MAX_PANES:
        raise ValueError(f"a session may contain at most {MAX_PANES} panes")
    panes = [PaneState.from_dict(item) for item in pane_data]
    identities = [pane.id for pane in panes]
    if len(set(identities)) != len(identities):
        raise ValueError("session pane ids must be unique")
    tree, tree_ids = _tree_copy(data["layout"])
    if set(identities) != set(tree_ids):
        raise ValueError("layout must reference every session pane exactly once")
    return panes, tree
