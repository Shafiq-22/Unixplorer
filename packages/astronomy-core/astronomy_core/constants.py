"""Physical constants and units, all taken from astropy (CLAUDE.md §7)."""

from __future__ import annotations

import astropy.constants as const
import astropy.units as u

#: Speed of light in vacuum (exact, SI definition).
C = const.c
#: Standard acceleration of gravity, 9.80665 m/s^2 (exact by definition).
STANDARD_GRAVITY = const.g0
#: astropy's `yr` is the Julian year (365.25 d), the year §10 uses.
JULIAN_YEAR = u.yr
