"""Painting: every drawn attribute must be part of the run-coalescing key.

The paint path coalesces adjacent cells with identical attributes into one
drawText run. Any attribute that is actually drawn (colors, bold, italics,
underscore, reverse, selection) must be in the key — otherwise, e.g., an
italic cell following a non-italic cell gets merged into the non-italic run
and rendered upright.
"""

import pyte

from widgets.terminal_paint import cells_mergeable

Char = pyte.screens.Char


def test_identical_cells_merge():
    a = Char(data="a")
    b = Char(data="b")
    assert cells_mergeable(a, b, False, False)


def test_italics_difference_blocks_merge():
    plain = Char(data="a", italics=False)
    italic = Char(data="b", italics=True)
    # Regression: italics was previously omitted from the key, so an italic
    # cell merged into a plain run and rendered upright.
    assert not cells_mergeable(plain, italic, False, False)
    assert cells_mergeable(italic, Char(data="c", italics=True), False, False)


def test_other_drawn_attributes_block_merge():
    base = Char(data="a")
    assert not cells_mergeable(base, Char(data="b", bold=True), False, False)
    assert not cells_mergeable(base, Char(data="b", underscore=True), False, False)
    assert not cells_mergeable(base, Char(data="b", reverse=True), False, False)
    assert not cells_mergeable(base, Char(data="b", fg="red"), False, False)
    assert not cells_mergeable(base, Char(data="b", bg="red"), False, False)


def test_selection_state_blocks_merge():
    a = Char(data="a")
    b = Char(data="b")
    assert not cells_mergeable(a, b, True, False)
    assert cells_mergeable(a, b, True, True)
