"""
Hay Day game logic for Silo and Barn upgrades.

Capacity rules:
- Initial capacity: 50
- From 50 to 1000: each upgrade adds +25 capacity
- From 1000 upwards: each upgrade adds +50 capacity
- Barn maximum capacity: 25,000 (Silo has no upper limit)

Upgrade cost rules:
- Each upgrade requires N items of EACH expansion type, where N is the
  upgrade index (1-based). The first upgrade (50 -> 75) costs 1 of each;
  the second (75 -> 100) costs 2 of each; and so on.
- Upgrade #38 is 975 -> 1000 (cost: 38 of each)
- Upgrade #39 is 1000 -> 1050 (first +50 step, cost: 39 of each)
"""

# Constants
INITIAL_CAPACITY = 50
SMALL_STEP = 25                # capacity gain per upgrade up to 1000
LARGE_STEP = 50                # capacity gain per upgrade above 1000
THRESHOLD = 1000               # capacity at which step size changes
SILO_MAX_CAPACITY = None       # no limit
BARN_MAX_CAPACITY = 25000

# Number of upgrades needed to reach 1000 from 50: (1000 - 50) / 25 = 38
UPGRADES_TO_THRESHOLD = (THRESHOLD - INITIAL_CAPACITY) // SMALL_STEP  # 38


def get_upgrade_index(current_capacity: int) -> int:
    """Return the 1-based index of the NEXT upgrade given the current capacity.

    Example:
        50  -> 1   (next upgrade is the 1st: 50 -> 75, cost 1 of each)
        75  -> 2   (2nd upgrade: 75 -> 100, cost 2)
        1000 -> 39 (first +50 step: 1000 -> 1050, cost 39)
        1050 -> 40
    """
    if current_capacity < INITIAL_CAPACITY:
        raise ValueError(f"Capacity cannot be less than {INITIAL_CAPACITY}.")

    if current_capacity <= THRESHOLD:
        # in the small-step zone (50 to 1000)
        # 50 -> upgrade #1, 75 -> #2, ..., 1000 -> #39
        return ((current_capacity - INITIAL_CAPACITY) // SMALL_STEP) + 1
    else:
        # in the large-step zone (1000+)
        # 1050 -> #40, 1100 -> #41, ...
        upgrades_above = (current_capacity - THRESHOLD) // LARGE_STEP
        return UPGRADES_TO_THRESHOLD + 1 + upgrades_above


def get_required_items(current_capacity: int) -> int:
    """Return the number of EACH expansion item needed for the next upgrade."""
    return get_upgrade_index(current_capacity)


def get_next_capacity(current_capacity: int) -> int:
    """Return the capacity after the next upgrade."""
    if current_capacity < THRESHOLD:
        return current_capacity + SMALL_STEP
    else:
        return current_capacity + LARGE_STEP


def can_upgrade(building_type: str, current_capacity: int) -> bool:
    """Return whether this building can be upgraded further (max capacity check)."""
    if building_type == "barn":
        return current_capacity < BARN_MAX_CAPACITY
    return True  # silo: no limit


def is_valid_capacity(capacity: int) -> bool:
    """Check whether a manually entered capacity value is reachable in the game."""
    if capacity < INITIAL_CAPACITY:
        return False
    if capacity <= THRESHOLD:
        return (capacity - INITIAL_CAPACITY) % SMALL_STEP == 0
    return (capacity - THRESHOLD) % LARGE_STEP == 0


# Item definitions per building
SILO_ITEMS = ["nail", "screw", "wood_panel"]
BARN_ITEMS = ["bolt", "plank", "duct_tape"]

ITEM_DISPLAY_NAMES = {
    "nail": "Nail",
    "screw": "Screw",
    "wood_panel": "Wood Panel",
    "bolt": "Bolt",
    "plank": "Plank",
    "duct_tape": "Duct Tape",
}


# Daily limit on total expansion-item purchases (per Hay Day mechanics)
DAILY_LIMIT_MAX = 89


# Quick self-test
if __name__ == "__main__":
    test_cases = [
        (50, 1, 75),
        (75, 2, 100),
        (100, 3, 125),
        (275, 10, 300),
        (975, 38, 1000),
        (1000, 39, 1050),
        (1050, 40, 1100),
        (1450, 48, 1500),
    ]
    print("Sanity-checking upgrade math:")
    for cap, expected_idx, expected_next in test_cases:
        idx = get_upgrade_index(cap)
        nxt = get_next_capacity(cap)
        ok = (idx == expected_idx) and (nxt == expected_next)
        print(f"  cap={cap}: upgrade #{idx} (expected {expected_idx}), "
              f"next={nxt} (expected {expected_next}) -> {'OK' if ok else 'FAIL'}")
