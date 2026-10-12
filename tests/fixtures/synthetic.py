"""SYNTHETIC test fixtures. These values are invented for tests and are not astronomical data.

They exist only to exercise file handling (hashing, row counts, Parquet building). Real-data
tests use files cut from data/raw/ and are marked `snapshot`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from astropy.io.votable import from_table, writeto
from astropy.table import MaskedColumn, Table


def write_votable(path: Path) -> Path:
    t = Table()
    t["SOURCE_ID"] = np.array([1, 2, 3], dtype=np.int64)  # Gaia's actual casing
    t["ra"] = MaskedColumn([10.0, 20.0, 30.0], unit="deg")
    t["parallax"] = MaskedColumn([50.0, np.nan, 12.5], unit="mas", mask=[False, False, False])
    t["phot_g_mean_mag"] = MaskedColumn([5.0, 6.0, 7.0], unit="mag", mask=[False, True, False])
    t["ref_epoch"] = MaskedColumn([2016.0, 2016.0, 2016.0], unit="yr")
    t["designation"] = ["SYNTH 1", "SYNTH 2", "SYNTH 3"]
    path.parent.mkdir(parents=True, exist_ok=True)
    writeto(from_table(t), str(path))
    return path


HORIZONS_RESULT = """*******************************************************************************
 Revised: SYNTHETIC FIXTURE                  Testbody                       9999
*******************************************************************************
Ephemeris / API_USER SYNTHETIC
Target body name: Testbody (9999)                 {source: SYNTHETIC}
Center body name: Solar System Barycenter (0)     {source: SYNTHETIC-DE}
*******************************************************************************
Start time      : A.D. 2016-Jan-01 12:00:00.0000 TDB
Output units    : KM-S
Reference frame : ICRF
*******************************************************************************
            JDTDB,            Calendar Date (TDB),                      X,                      Y,                      Z,                     VX,                     VY,                     VZ,
**************************************************************************************************************************************************************************************************
$$SOE
2457389.000000000, A.D. 2016-Jan-01 12:00:00.0000,  1.000000000000000E+03,  2.000000000000000E+03, -3.000000000000000E+03,  1.000000000000000E+00,  2.000000000000000E+00,  3.000000000000000E+00,
$$EOE
"""


def write_horizons(dir_: Path) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / "testbody.json"
    path.write_text(json.dumps({"signature": {"version": "synthetic"}, "result": HORIZONS_RESULT}))
    (dir_ / "requests.json").write_text(
        json.dumps(
            [{"body": "Testbody", "url": "https://example.invalid/api?OUT_UNITS=%27KM-S%27"}]
        )
    )
    return path
