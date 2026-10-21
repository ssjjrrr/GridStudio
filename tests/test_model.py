"""Invariant tests for duplication, split layouts, and untrusted session files."""

import json
import unittest
from copy import deepcopy

from gridstudio.model import (
    MAX_PANES,
    MAX_POSITION_MS,
    PRESETS,
    PaneState,
    decode_session,
    encode_session,
    get_layout_mode,
    leaf_ids,
    make_layout,
    remove_leaf,
    split_leaf,
    swap_leaves,
)


class PaneTests(unittest.TestCase):
    def test_duplicate_preserves_transforms_and_playback_with_independent_identity(self):
        original = PaneState(
            source="C:/片段/clip.mp4", rotation=270, crop=(0.1, 0.2, 0.7, 0.6),
            flip_h=True, flip_v=True, position_ms=98765, rate=1.5, volume=0.8,
            muted=False, loop=False, loop_start_ms=1200, loop_end_ms=8000,
            paused=False, fit_mode="cover", sync_group="3", sync_mode="percent",
            sync_offset_ms=-600,
            canvas_rect=(-0.1, 0.2, 0.7, 0.6), z_order=31,
        )
        duplicate = original.clone()
        self.assertNotEqual(original.id, duplicate.id)
        expected = original.to_dict()
        actual = duplicate.to_dict()
        expected.pop("id")
        actual.pop("id")
        self.assertEqual(expected, actual)
        duplicate.crop = (0, 0, 0.5, 0.5)
        duplicate.rotation = 90
        duplicate.canvas_rect = (0.2, 0.1, 0.5, 0.4)
        duplicate.z_order = 32
        self.assertEqual(original.crop, (0.1, 0.2, 0.7, 0.6))
        self.assertEqual(original.rotation, 270)
        self.assertEqual(original.canvas_rect, (-0.1, 0.2, 0.7, 0.6))
        self.assertEqual(original.z_order, 31)

    def test_defaults_show_full_frame_and_keep_loop_and_sync_unconfigured(self):
        state = PaneState.from_dict({"id": "a"})
        self.assertEqual(state.fit_mode, "contain")
        self.assertTrue(state.loop)
        self.assertEqual(state.loop_start_ms, 0)
        self.assertIsNone(state.loop_end_ms)
        self.assertEqual(state.sync_group, "")
        self.assertEqual(state.sync_mode, "time")
        self.assertEqual(state.sync_offset_ms, 0)
        self.assertIsNone(state.canvas_rect)
        self.assertEqual(state.z_order, 0)

    def test_canvas_rect_allows_partial_offstage_positions_and_serializes_independently(self):
        for rect in ((0, 0, 1, 1), (-1, -1, 3, 3), (0.99, 0.99, 0.02, 0.02),
                     (-0.25, 0.2, 0.5, 0.7), (0, -0.25, 0.5, 0.5)):
            with self.subTest(rect=rect):
                original = PaneState(id="a", canvas_rect=rect)
                data = original.to_dict()
                self.assertIsInstance(data["canvas_rect"], list)
                restored = PaneState.from_dict(json.loads(json.dumps(data, allow_nan=False)))
                self.assertEqual(restored.canvas_rect, rect)
                data["canvas_rect"][0] = 0.5
                self.assertEqual(restored.canvas_rect, rect)
                self.assertEqual(original.canvas_rect, rect)

    def test_canvas_z_order_boundary_values_roundtrip(self):
        for z_order in (-1_000_000, -1, 0, 1, 1_000_000):
            with self.subTest(z_order=z_order):
                state = PaneState(id="a", z_order=z_order)
                self.assertEqual(PaneState.from_dict(state.to_dict()).z_order, z_order)

    def test_canvas_geometry_and_layer_order_reject_invalid_or_invisible_frames(self):
        invalid_rects = (
            (), (0, 0, 1), (0, 0, 1, 1, 0), "0,0,1,1", {},
            (True, 0, 1, 1), (0, False, 1, 1), (0, 0, "1", 1),
            (float("nan"), 0, 1, 1), (0, float("inf"), 1, 1),
            (0, 0, float("nan"), 1), (0, 0, 1, float("inf")),
            (-1.01, 0, 2, 1), (0, -1.01, 1, 2),
            (2.01, 0, 1, 1), (0, 2.01, 1, 1),
            (0, 0, 0, 1), (0, 0, 0.019, 1), (0, 0, 1, 0.019),
            (0, 0, 3.01, 1), (0, 0, 1, 3.01),
            (1, 0, 1, 1), (0, 1, 1, 1), (-1, 0, 1, 1), (0, -1, 1, 1),
        )
        for rect in invalid_rects:
            with self.subTest(rect=rect), self.assertRaises(ValueError):
                PaneState.from_dict({"id": "a", "canvas_rect": rect})
        for z_order in (True, False, 0.0, "0", None, [], -1_000_001, 1_000_001):
            with self.subTest(z_order=z_order), self.assertRaises(ValueError):
                PaneState.from_dict({"id": "a", "z_order": z_order})

    def test_fit_modes_and_sync_groups_are_supported(self):
        for fit_mode in ("contain", "cover", "stretch"):
            for group in ("", "1", "2", "3", "4"):
                for sync_mode in ("time", "percent"):
                    with self.subTest(fit_mode=fit_mode, group=group, sync_mode=sync_mode):
                        data = {"id": "a", "fit_mode": fit_mode, "sync_group": group,
                                "sync_mode": sync_mode}
                        restored = PaneState.from_dict(data)
                        self.assertEqual(restored.fit_mode, fit_mode)
                        self.assertEqual(restored.sync_group, group)
                        self.assertEqual(restored.sync_mode, sync_mode)

    def test_loop_markers_allow_a_only_and_minimum_one_millisecond_interval(self):
        a_only = PaneState.from_dict({"id": "a", "loop_start_ms": MAX_POSITION_MS})
        self.assertEqual(a_only.loop_start_ms, MAX_POSITION_MS)
        self.assertIsNone(a_only.loop_end_ms)
        shortest = PaneState.from_dict({"id": "a", "loop_start_ms": MAX_POSITION_MS - 1,
                                       "loop_end_ms": MAX_POSITION_MS})
        self.assertEqual(shortest.loop_end_ms - shortest.loop_start_ms, 1)

    def test_signed_sync_offset_boundaries_roundtrip(self):
        for offset in (-MAX_POSITION_MS, -1, 0, 1, MAX_POSITION_MS):
            state = PaneState(id="a", sync_offset_ms=offset)
            with self.subTest(offset=offset):
                self.assertEqual(PaneState.from_dict(state.to_dict()).sync_offset_ms, offset)

    def test_invalid_fit_loop_and_sync_settings_are_rejected(self):
        invalid = (
            {"fit_mode": "fill"}, {"fit_mode": None}, {"fit_mode": 1},
            {"fit_mode": []}, {"loop_start_ms": -1}, {"loop_start_ms": True},
            {"loop_start_ms": 1.5}, {"loop_start_ms": MAX_POSITION_MS + 1},
            {"loop_end_ms": -1}, {"loop_end_ms": False}, {"loop_end_ms": "100"},
            {"loop_end_ms": 1.0}, {"loop_end_ms": MAX_POSITION_MS + 1},
            {"loop_end_ms": 0}, {"loop_start_ms": 100, "loop_end_ms": 100},
            {"loop_start_ms": 100, "loop_end_ms": 99}, {"sync_group": "5"},
            {"sync_group": 1}, {"sync_group": None}, {"sync_group": []},
            {"sync_mode": "timestamp"}, {"sync_mode": None}, {"sync_mode": []},
            {"sync_offset_ms": True}, {"sync_offset_ms": "0"},
            {"sync_offset_ms": 0.0}, {"sync_offset_ms": float("nan")},
            {"sync_offset_ms": MAX_POSITION_MS + 1},
            {"sync_offset_ms": -MAX_POSITION_MS - 1},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                PaneState.from_dict({"id": "a", **changes})

    def test_serialization_copies_crop_and_normalizes_numbers(self):
        state = PaneState(id="video", volume=1, crop=(0, 0, 1, 1))
        data = state.to_dict()
        restored = PaneState.from_dict(data)
        data["crop"][0] = 0.5
        self.assertEqual(restored.crop, (0.0, 0.0, 1.0, 1.0))
        self.assertEqual(state.crop, (0, 0, 1, 1))

    def test_invalid_transforms_and_playback_are_rejected(self):
        invalid = (
            {"rotation": 45}, {"rotation": True}, {"crop": (0, 0, 0, 1)},
            {"crop": (0.8, 0, 0.3, 1)}, {"crop": (0, 0, float("nan"), 1)},
            {"crop": (0, 0, 1)}, {"rate": float("inf")}, {"volume": -0.1},
            {"rate": 0}, {"position_ms": -1}, {"position_ms": 1.5},
            {"muted": 1}, {"source": "bad\0path"}, {"unexpected": 1},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                PaneState.from_dict({"id": "a", **changes})


class LayoutTests(unittest.TestCase):
    def test_split_is_persistent_and_remove_collapses_single_child_branches(self):
        original = {"pane": "a"}
        two = split_leaf(original, "a", "b", "horizontal")
        three = split_leaf(two, "b", "c", "vertical")
        self.assertEqual(original, {"pane": "a"})
        self.assertEqual(leaf_ids(two), ["a", "b"])
        self.assertEqual(leaf_ids(three), ["a", "b", "c"])
        self.assertEqual(remove_leaf(three, "c"), two)
        self.assertEqual(remove_leaf(two, "a"), {"pane": "b"})
        self.assertIsNone(remove_leaf(original, "a"))
        self.assertEqual(leaf_ids(three), ["a", "b", "c"])

    def test_remove_preserves_surviving_sizes(self):
        tree = make_layout(["a", "b", "c"], "columns")
        tree["sizes"] = [2, 3, 5]
        reduced = remove_leaf(tree, "b")
        self.assertEqual(reduced["sizes"], [2, 5])
        self.assertEqual(leaf_ids(reduced), ["a", "c"])

    def test_swap_preserves_layout_and_does_not_mutate_input(self):
        tree = split_leaf(make_layout(["a", "b"], "columns"), "b", "c", "vertical")
        tree["sizes"] = [3, 7]
        swapped = swap_leaves(tree, "a", "c")
        self.assertEqual(leaf_ids(swapped), ["c", "b", "a"])
        self.assertEqual(swapped["sizes"], [3, 7])
        self.assertEqual(leaf_ids(tree), ["a", "b", "c"])
        self.assertEqual(swap_leaves(tree, "a", "a"), tree)

    def test_every_preset_preserves_all_panes_and_roundtrips(self):
        for count in (0, 1, 2, 3, 5, 7, 10, 63, 64):
            panes = [PaneState(id=f"pane-{i}", source=f"clip-{i}.mp4") for i in range(count)]
            identities = [pane.id for pane in panes]
            for preset in PRESETS:
                with self.subTest(count=count, preset=preset):
                    tree = make_layout(identities, preset)
                    self.assertEqual(leaf_ids(tree), identities)
                    data = json.loads(json.dumps(encode_session(panes, tree), allow_nan=False))
                    loaded_panes, loaded_tree = decode_session(data)
                    self.assertEqual(loaded_tree, tree)
                    self.assertEqual([pane.id for pane in loaded_panes], identities)

    def test_grid_keeps_incomplete_final_row(self):
        tree = make_layout(["a", "b", "c", "d", "e"], "grid")
        self.assertEqual(tree["axis"], "vertical")
        self.assertEqual([leaf_ids(row) for row in tree["children"]], [["a", "b", "c"], ["d", "e"]])

    def test_invalid_operations_do_not_silently_lose_panes(self):
        tree = make_layout(["a", "b"], "rows")
        operations = (
            lambda: split_leaf(tree, "missing", "c", "horizontal"),
            lambda: split_leaf(tree, "a", "b", "horizontal"),
            lambda: split_leaf(tree, "a", "c", "diagonal"),
            lambda: remove_leaf(tree, "missing"),
            lambda: swap_leaves(tree, "a", "missing"),
            lambda: make_layout(["a", "a"], "grid"),
            lambda: make_layout(["a"], "unknown"),
        )
        for operation in operations:
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(leaf_ids(tree), ["a", "b"])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.valid = encode_session([PaneState(id="a"), PaneState(id="b")], make_layout(["a", "b"], "columns"))

    def test_old_version_one_session_loads_safe_display_loop_and_sync_defaults(self):
        # Version 0.3 sessions have no display-fit, fragment-loop, or sync fields.
        old_data = {
            "format": "gridstudio", "version": 1,
            "panes": [{"id": "a", "source": "clip.mp4", "rotation": 90,
                       "crop": [0.1, 0.2, 0.7, 0.6], "position_ms": 5432,
                       "loop": False, "paused": False}],
            "layout": {"pane": "a"},
        }
        panes, tree = decode_session(old_data)
        state = panes[0]
        self.assertEqual(state.fit_mode, "contain")
        self.assertFalse(state.loop)
        self.assertEqual(state.loop_start_ms, 0)
        self.assertIsNone(state.loop_end_ms)
        self.assertEqual(state.sync_group, "")
        self.assertEqual(state.sync_mode, "time")
        self.assertEqual(state.sync_offset_ms, 0)
        self.assertEqual(state.position_ms, 5432)
        self.assertEqual(state.rotation, 90)
        self.assertEqual(state.crop, (0.1, 0.2, 0.7, 0.6))
        self.assertIsNone(state.canvas_rect)
        self.assertEqual(state.z_order, 0)
        self.assertEqual(get_layout_mode(old_data), "grid")
        encoded = encode_session(panes, tree)
        self.assertEqual(encoded["version"], 1)
        restored, restored_tree = decode_session(json.loads(json.dumps(encoded)))
        self.assertEqual(restored, panes)
        self.assertEqual(restored_tree, tree)

    def test_canvas_session_preserves_geometry_stacking_and_mode(self):
        panes = [PaneState(id="a", canvas_rect=(0.1, 0.2, 0.6, 0.5), z_order=17),
                 PaneState(id="b", canvas_rect=(-0.2, 0.3, 0.8, 0.7), z_order=-5)]
        tree = make_layout(["a", "b"], "columns")
        encoded = encode_session(panes, tree, layout_mode="canvas")
        data = json.loads(json.dumps(encoded, allow_nan=False))
        self.assertEqual(get_layout_mode(data), "canvas")
        restored, restored_tree = decode_session(data)
        self.assertEqual(restored, panes)
        self.assertEqual(restored_tree, tree)
        self.assertEqual(encode_session(restored, restored_tree, layout_mode="canvas"), encoded)

    def test_session_mode_defaults_to_grid_and_rejects_invalid_values(self):
        self.assertEqual(get_layout_mode(self.valid), "grid")
        old = deepcopy(self.valid)
        old.pop("layout_mode")
        self.assertEqual(get_layout_mode(old), "grid")
        self.assertEqual(decode_session(old), decode_session(self.valid))
        for mode in (None, True, 0, "free", [], {}):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    decode_session({**self.valid, "layout_mode": mode})
                with self.assertRaises(ValueError):
                    encode_session([PaneState(id="a")], {"pane": "a"}, layout_mode=mode)

    def test_session_preserves_fit_fragment_loop_and_sync_fields(self):
        panes = [PaneState(id="a", fit_mode="stretch", loop_start_ms=1500,
                           loop_end_ms=6750, sync_group="2", sync_mode="percent",
                           sync_offset_ms=-250)]
        tree = {"pane": "a"}
        data = json.loads(json.dumps(encode_session(panes, tree), allow_nan=False))
        restored, restored_tree = decode_session(data)
        self.assertEqual(restored, panes)
        self.assertEqual(restored_tree, tree)

    def test_session_is_an_independent_snapshot(self):
        panes = [PaneState(id="a")]
        tree = {"pane": "a"}
        data = encode_session(panes, tree)
        panes[0].source = "changed.mp4"
        tree["pane"] = "changed"
        restored, restored_tree = decode_session(data)
        self.assertEqual(restored[0].source, "")
        self.assertEqual(restored_tree, {"pane": "a"})

    def test_malformed_session_data_is_rejected(self):
        invalid = []
        for key, value in (("format", "other"), ("version", 2), ("version", True), ("panes", {})):
            data = deepcopy(self.valid)
            data[key] = value
            invalid.append(data)
        duplicate_panes = deepcopy(self.valid)
        duplicate_panes["panes"][1]["id"] = "a"
        invalid.append(duplicate_panes)
        for layout in (
            None, {"pane": "missing"},
            {"axis": "horizontal", "sizes": [1, 1], "children": [{"pane": "a"}, {"pane": "a"}]},
            {"axis": "diagonal", "sizes": [1, 1], "children": [{"pane": "a"}, {"pane": "b"}]},
            {"axis": "horizontal", "sizes": [1], "children": [{"pane": "a"}, {"pane": "b"}]},
            {"axis": "horizontal", "sizes": [0, 1], "children": [{"pane": "a"}, {"pane": "b"}]},
            {"axis": "horizontal", "sizes": [float("nan"), 1], "children": [{"pane": "a"}, {"pane": "b"}]},
            {"axis": "horizontal", "sizes": [1], "children": [{"pane": "a"}]},
            {"pane": "a", "children": []},
        ):
            data = deepcopy(self.valid)
            data["layout"] = layout
            invalid.append(data)
        bad_crop = deepcopy(self.valid)
        bad_crop["panes"][0]["crop"] = [0, 0, float("nan"), 1]
        invalid.append(bad_crop)
        invalid.extend((None, [], {}, {**self.valid, "extra": 1}))
        for index, data in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(ValueError):
                decode_session(data)

    def test_oversized_and_deep_layouts_are_rejected(self):
        with self.assertRaises(ValueError):
            make_layout([str(i) for i in range(MAX_PANES + 1)])
        with self.assertRaises(ValueError):
            decode_session({**self.valid, "panes": [{"id": str(i)} for i in range(MAX_PANES + 1)]})
        deep = {"pane": "a"}
        for index in range(100):
            deep = {"axis": "horizontal", "sizes": [1, 1], "children": [deep, {"pane": f"extra-{index}"}]}
        with self.assertRaises(ValueError):
            leaf_ids(deep)
        # A cycle cannot be represented in JSON, but in-memory callers must also fail safely.
        cycle = {"axis": "horizontal", "sizes": [1, 1], "children": []}
        cycle["children"] = [cycle, {"pane": "a"}]
        with self.assertRaises(ValueError):
            leaf_ids(cycle)


if __name__ == "__main__":
    unittest.main()
