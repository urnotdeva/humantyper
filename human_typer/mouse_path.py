"""Fitts-law humanized mouse paths."""

from __future__ import annotations

import math
import random

FITTS_A = 0.55
FITTS_B = 0.1276


def _bezier_coord(p0, p1, p2, p3, t):
    return ((1 - t) ** 3) * p0 + 3 * t * (1 - t) ** 2 * p1 + 3 * (1 - t) * t**2 * p2 + t**3 * p3


def _cubic_bezier(p0, p1, p2, p3, t):
    return (
        _bezier_coord(p0[0], p1[0], p2[0], p3[0], t),
        _bezier_coord(p0[1], p1[1], p2[1], p3[1], t),
    )


def _random_signed(a, b):
    r = random.randint(int(a), int(b))
    return -r if random.random() < 0.5 else r


def _fitts_movement_time(distance, target_width):
    target_width = max(target_width, 8.0)
    index_of_difficulty = math.log2((2.0 * max(distance, 1.0)) / target_width)
    return max(0.15, FITTS_A + FITTS_B * index_of_difficulty)


def _logistic_sigmoid(x):
    return 2 / (1 + math.exp(-x)) - 1


_SIGMOID_NORM = _logistic_sigmoid(4.5)


def humanized_path(
    start,
    end,
    target_width=60.0,
    radius_interval=(20, 40),
    distortion_zone_len=0.05,
    distortion_freq=0.15,
    deviation_range=(1, 5),
):
    """Returns (points, step_delay). Duration is derived from Fitts's Law."""
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    duration = _fitts_movement_time(distance, target_width)

    p1 = (start[0] + _random_signed(*radius_interval), start[1] + _random_signed(*radius_interval))
    p2 = (end[0] + _random_signed(*radius_interval), end[1] + _random_signed(*radius_interval))

    n_zones = int(1 / distortion_zone_len)
    zones = [
        (i * distortion_zone_len, (i + 1) * distortion_zone_len)
        for i in range(n_zones)
        if random.random() < distortion_freq
    ]
    offsets = [(_random_signed(*deviation_range), _random_signed(*deviation_range)) for _ in zones]

    def distorted_point(t):
        pt = _cubic_bezier(start, p1, p2, end, t)
        for (z0, z1), (ox, oy) in zip(zones, offsets):
            if z0 <= t <= z1:
                progress = (t - z0) / (z1 - z0)
                factor = progress * 2 if progress < 0.5 else (1 - (progress - 0.5) * 2)
                return (pt[0] + ox * factor, pt[1] + oy * factor)
        return pt

    steps = max(4, int(duration * 60))
    points = []
    for i in range(steps + 1):
        t_lin = i / steps
        warped = _logistic_sigmoid(t_lin * 4.5) / _SIGMOID_NORM
        points.append(distorted_point(warped))
    return points, duration / max(steps, 1)
