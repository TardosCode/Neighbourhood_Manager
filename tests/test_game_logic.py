"""Tests for game_logic.py — Silo/Barn upgrade math."""

import pytest

import game_logic as gl


# ----- constants ------------------------------------------------------------

def test_constants():
    assert gl.INITIAL_CAPACITY == 50
    assert gl.SMALL_STEP == 25
    assert gl.LARGE_STEP == 50
    assert gl.THRESHOLD == 1000
    assert gl.SILO_MAX_CAPACITY is None
    assert gl.BARN_MAX_CAPACITY == 25000
    assert gl.UPGRADES_TO_THRESHOLD == 38


# ----- get_upgrade_index / get_required_items -------------------------------

@pytest.mark.parametrize("cap,expected_idx", [
    (50, 1),
    (75, 2),
    (100, 3),
    (275, 10),
    (975, 38),
    (1000, 39),
    (1050, 40),
    (1100, 41),
    (1450, 48),
])
def test_get_upgrade_index(cap, expected_idx):
    assert gl.get_upgrade_index(cap) == expected_idx


def test_get_required_items_matches_index():
    for cap in (50, 75, 1000, 1050):
        assert gl.get_required_items(cap) == gl.get_upgrade_index(cap)


def test_get_upgrade_index_below_initial_raises():
    with pytest.raises(ValueError):
        gl.get_upgrade_index(49)


# ----- get_next_capacity ----------------------------------------------------

@pytest.mark.parametrize("cap,expected_next", [
    (50, 75),
    (75, 100),
    (975, 1000),
    (1000, 1050),   # threshold itself uses LARGE_STEP (cap < THRESHOLD is False)
    (1050, 1100),
])
def test_get_next_capacity(cap, expected_next):
    assert gl.get_next_capacity(cap) == expected_next


# ----- can_upgrade ----------------------------------------------------------

def test_can_upgrade_silo_always_true():
    assert gl.can_upgrade("silo", 50) is True
    assert gl.can_upgrade("silo", 999999) is True


def test_can_upgrade_barn_respects_max():
    assert gl.can_upgrade("barn", 24950) is True
    assert gl.can_upgrade("barn", gl.BARN_MAX_CAPACITY) is False
    assert gl.can_upgrade("barn", gl.BARN_MAX_CAPACITY + 50) is False


# ----- is_valid_capacity ----------------------------------------------------

@pytest.mark.parametrize("cap,valid", [
    (50, True),
    (75, True),
    (1000, True),
    (1050, True),
    (49, False),    # below initial
    (60, False),    # not on a 25-step boundary
    (1025, False),  # above threshold but not on a 50-step boundary
    (1100, True),
])
def test_is_valid_capacity(cap, valid):
    assert gl.is_valid_capacity(cap) is valid


# ----- item definitions -----------------------------------------------------

def test_item_definitions():
    assert gl.SILO_ITEMS == ["nail", "screw", "wood_panel"]
    assert gl.BARN_ITEMS == ["bolt", "plank", "duct_tape"]
    assert gl.ITEM_DISPLAY_NAMES["duct_tape"] == "Duct Tape"
    assert gl.DAILY_LIMIT_MAX == 89
