"""Selection/inspector updates stay proportional to the actual change."""

from collections import Counter

from test_app import drain_events, qapp
from test_free_canvas import canvas_window


def record(monkeypatch, counts, obj, method, label):
    original = getattr(obj, method)

    def call(*args, **kwargs):
        counts[label] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(obj, method, call)


def watch_inspector(monkeypatch, win):
    counts = Counter()
    for name in ("selected_label", "source_label", "rotation_label", "crop_label"):
        record(monkeypatch, counts, getattr(win, name), "setText", name)
    for name in ("fit_mode", "rate"):
        record(monkeypatch, counts, getattr(win, name), "setCurrentIndex", name)
    for name in ("flip_h", "flip_v", "muted", "loop"):
        record(monkeypatch, counts, getattr(win, name), "setChecked", name)
    record(monkeypatch, counts, win.volume, "setValue", "volume")
    return counts


def test_repeated_selection_does_not_visit_other_layers_or_rewrite_controls(canvas_window, qapp, monkeypatch):
    win = canvas_window
    for _ in range(7):
        win.add_blank()
    win.set_layout_mode("grid")
    win.set_clean_mode(False)
    win.select(win.active_id)
    drain_events(qapp)
    # Native QWidget attributes must be restored while the window is alive,
    # before canvas_window's teardown runs its deferred Qt deletions.
    with monkeypatch.context() as patch:
        counts = watch_inspector(patch, win)
        for pane in win.panes.values():
            record(patch, counts, pane, "property", "pane_property")
        for _ in range(500):
            win.select(win.active_id)
        assert counts == {}, counts


def test_volume_change_only_updates_volume_field_and_selection_remains_correct(canvas_window, qapp, monkeypatch):
    win = canvas_window
    first = win.active()
    win.add_blank()
    second = win.active()
    win.set_layout_mode("grid")
    win.set_clean_mode(False)
    win.select(first.state.id)
    drain_events(qapp)
    with monkeypatch.context() as patch:
        counts = watch_inspector(patch, win)
        first.state.volume = .73
        win.refresh_inspector()
        assert win.volume.value() == 73
        assert counts == {"volume": 1}
        win.select(second.state.id)
        assert not first.property("selected")
        assert second.property("selected")
        assert win.volume.value() == round(second.state.volume * 100)
        win.set_clean_mode(True)
        assert not first.property("selected") and not second.property("selected")


def test_loading_same_ids_replaces_selected_widget_and_updates_inspector(canvas_window, qapp, tmp_path):
    win = canvas_window
    win.set_layout_mode("grid")
    win.set_clean_mode(False)
    first = win.active()
    pane_id = first.state.id
    first.state.volume = .27
    first.state.rotation = 90
    first.apply_state()
    path = tmp_path / "same-ids.gstudio"
    assert win.save_session(path)
    assert win.load_session(path)
    drain_events(qapp)
    replacement = win.active()
    assert replacement.state.id == pane_id
    assert replacement is not first
    assert replacement.property("selected")
    assert win.volume.value() == 27
    assert win.rotation_label.text().endswith("90°")


def test_unchanged_layout_choice_keeps_workspace_and_focused_choice_restores_canvas(canvas_window, qapp):
    win = canvas_window
    stage = win.canvas_workspace
    win.set_layout_mode("canvas")
    assert win.canvas_workspace is stage
    win.toggle_focus()
    drain_events(qapp)
    assert win.focus_id is not None
    win.set_layout_mode("canvas")
    drain_events(qapp)
    assert win.focus_id is None
    assert win.root_widget is win.canvas_workspace
