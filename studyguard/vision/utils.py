from __future__ import annotations

import math
from typing import Sequence


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.dist((a[0], a[1]), (b[0], b[1]))


def ratio(numerator_a: Sequence[float], numerator_b: Sequence[float], denominator_a: Sequence[float], denominator_b: Sequence[float]) -> float:
    den = distance(denominator_a, denominator_b)
    if den <= 1e-6:
        return 0.0
    return distance(numerator_a, numerator_b) / den
