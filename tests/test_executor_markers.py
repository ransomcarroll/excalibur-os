from excalibur.text_utils import scan_markers


def test_done_marker_recorded_once():
    done: list[str] = []
    blocked: dict[str, str] = {}
    scan_markers("PLAN[ABC-1]: doing the thing\nDONE[ABC-1]\n", done, blocked)
    scan_markers("DONE[ABC-1]\n", done, blocked)  # duplicate emission
    assert done == ["ABC-1"]
    assert blocked == {}


def test_blocked_marker_captures_reason():
    done: list[str] = []
    blocked: dict[str, str] = {}
    scan_markers("BLOCKED[ABC-1]: tests fail and I can't fix them\n", done, blocked)
    assert blocked == {"ABC-1": "tests fail and I can't fix them"}
    assert done == []


def test_mixed_markers_in_one_chunk():
    done: list[str] = []
    blocked: dict[str, str] = {}
    chunk = """
    PLAN[ABC-1]: ok
    DONE[ABC-1]
    PLAN[ABC-2]: ok
    BLOCKED[ABC-2]: missing context on which surface
    """
    scan_markers(chunk, done, blocked)
    assert done == ["ABC-1"]
    assert blocked == {"ABC-2": "missing context on which surface"}
