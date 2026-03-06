# File: athena/movement_order.py
# Version: v1.0 — UI ordering + QC thresholds (separate from final_movement_names.py)
#
# Purpose:
# - Control the order movements appear in B5 manual panes (UI ergonomics).
# - Provide simple pane-level QC thresholds (used by /b5/manual/pane response).
#
# This file is meant to be edited freely over time.

from __future__ import annotations

from typing import Dict, List

# -------------------------------
# Movement ordering (canonical keys)
# -------------------------------
MOVEMENT_ORDER: List[str] = [
    # Big functional / global first
    "sit_stand",
    "regular_squat",
    "sumo_squat",
    "jump_on_both_legs",
    "lumbar_flexion_extension",

    # Gait last (often ignored)
    "walking",

    # Single-leg
    "right_leg_single_leg_hop",
    "left_leg_single_leg_hop",

    # Shoe tying (standing)
    "right_leg_standing_shoe_tying",
    "left_leg_standing_shoe_tying",

    # Shoe tying (figure-4)
    "right_leg_figure_4_(tying_shoes)",
    "left_leg_figure_4_(tying_shoes)",

    # Seated ROM — Right
    "right_leg_seated_deep_flexion",
    "right_leg_seated_internal_rotation",
    "right_leg_seated_external_rotation",
    "right_leg_seated_abduction",
    "right_leg_seated_adduction",
    "right_leg_seated_deep_flexion_internal_rotation",
    "right_leg_seated_deep_flexion_external_rotation",

    # Seated ROM — Left
    "left_leg_seated_deep_flexion",
    "left_leg_seated_internal_rotation",
    "left_leg_seated_external_rotation",
    "left_leg_seated_abduction",
    "left_leg_seated_adduction",
    "left_leg_seated_deep_flexion_internal_rotation",
    "left_leg_seated_deep_flexion_external_rotation",
]

# Derived rank map (movement -> index). Unknown movements go to the bottom.
MOVEMENT_RANK: Dict[str, int] = {mv: i for i, mv in enumerate(MOVEMENT_ORDER)}

def movement_rank(mv: str) -> int:
    return MOVEMENT_RANK.get((mv or "").strip().lower(), 10_000_000)

# -------------------------------
# Pane-level QC thresholds
# -------------------------------
QC: Dict[str, float] = {
    # If pane window length < this, flag as too_short
    "min_frames": 60,

    # If amplitude (max-min) is < this threshold in degrees, flag as flat_signal
    "min_amp_deg": 2.0,
}