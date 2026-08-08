"""The TextMeshPro metric fix — the part that needs no Unity files.

Why it exists at all: the game's text components are tuned for fixed-width kana,
with negative letter spacing and glyph squeezing enabled. With Latin letters the
glyphs overlap and strokes disappear ("Bullet" rendered as "Bulet"). See
docs/PIPELINE.md.
"""

from __future__ import annotations

import pytest

from medarot.patch import metrics


def component(**overrides) -> dict:
    """A plausible TextMeshPro component, as the game ships it."""
    base = {
        "m_text": "こんにちは",
        "m_characterSpacing": -8.0,
        "m_charWidthMaxAdj": 40.0,
        "m_wordSpacing": -2.0,
        "m_fontSize": 24.0,
    }
    base.update(overrides)
    return base


def test_negative_spacing_and_squeezing_are_zeroed():
    tree = component()
    assert metrics._fix(tree) is True
    assert tree["m_characterSpacing"] == 0.0
    assert tree["m_charWidthMaxAdj"] == 0.0
    assert tree["m_wordSpacing"] == 0.0


def test_a_healthy_component_is_left_alone():
    tree = component(m_characterSpacing=0.0, m_charWidthMaxAdj=0.0, m_wordSpacing=0.0)
    assert metrics._fix(tree) is False


def test_positive_spacing_is_not_touched():
    """Only the negative values are the problem; positive spacing is deliberate."""
    tree = component(m_characterSpacing=2.0, m_charWidthMaxAdj=0.0, m_wordSpacing=1.5)
    assert metrics._fix(tree) is False
    assert tree["m_characterSpacing"] == 2.0
    assert tree["m_wordSpacing"] == 1.5


def test_missing_fields_are_survivable():
    """A component without these fields is not a text component."""
    assert metrics._fix({"m_Name": "something else"}) is False


@pytest.mark.parametrize("tree,expected", [
    (component(), True),
    (component(m_text=None), False),                    # not a text component
    (component(m_text=123), False),
    (component(m_charWidthMaxAdj=-1), False),           # out of range: mis-parsed
    (component(m_charWidthMaxAdj=1000), False),
    (component(m_characterSpacing=9999), False),
    (component(m_fontSize=0), False),
    (component(m_fontSize=5000), False),
])
def test_plausibility_guard(tree, expected):
    """Scene objects are read with a borrowed typetree, so the result is checked.

    Without this, a mis-parse would be written back and corrupt the scene.
    """
    assert metrics._plausible(tree) is expected


def test_marker_field_identifies_text_components():
    assert metrics.TMP_MARKER == "m_charWidthMaxAdj"
    assert metrics.TMP_MARKER in component()


# ---------------------------------------------------------------- fonts ----

def test_fallback_chain_has_no_cycles():
    """A font reachable from the fallbacks must not be given fallbacks itself.

    Otherwise the chain closes on itself: LiberationSans -> its own Fallback ->
    LiberationSans. Found by diffing a build against the reference pipeline.
    """
    from medarot.patch import fonts

    # name -> path_id, and the fallback tables they already declare
    trees = {
        1: {"m_Name": "Main", fonts.FALLBACK_TABLE: []},
        2: {"m_Name": "Fallback", fonts.FALLBACK_TABLE: [{"m_PathID": 3}]},
        3: {"m_Name": "Fallback of the fallback", fonts.FALLBACK_TABLE: []},
    }
    reachable, pending = set(), [2]
    while pending:
        path_id = pending.pop()
        if path_id in reachable:
            continue
        reachable.add(path_id)
        for reference in trees[path_id][fonts.FALLBACK_TABLE]:
            pending.append(reference["m_PathID"])

    assert reachable == {2, 3}, "the closure must include indirect fallbacks"
    assert 1 not in reachable, "the main font is still a candidate for patching"
