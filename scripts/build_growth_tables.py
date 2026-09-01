"""Build ``nutrition-data/who-growth-standards.yaml`` from WHO's published z-score tables.

Run once with an ephemeral openpyxl (the app itself never reads .xlsx):

    uv run --with openpyxl scripts/build_growth_tables.py

Downloads the WHO Child Growth Standards (2006) LMS tables — per sex: weight-for-age
0-5 years, length/height-for-age 0-2 and 2-5 years, weight-for-length 45-110 cm,
weight-for-height 65-120 cm, BMI-for-age 0-2 and 2-5 years — verifies the L, M, S
columns and key contiguity, applies WHO's month-24 convention (the 2-5-year file, which
uses standing height, supplies month 24), and writes one YAML file with full provenance:
source, per-file URL and sha256, retrieval date.

The ``weight_for_length_height`` indicator holds a ``length`` and a ``height`` subtable
because the two WHO tables overlap in centimetres (65-110) with different values —
selection between them is by age (under 24 months: length) and happens at assessment
time. The other three indicators are flat ``[[month, L, M, S], ...]`` lists.

Re-running on the same day must produce a byte-identical file; keys and file order are
fixed and floats are written exactly as read.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import sys
import urllib.request
from pathlib import Path

import openpyxl
import yaml

OUT_PATH = Path(__file__).parent.parent / "nutrition-data" / "who-growth-standards.yaml"

SOURCE = "WHO Child Growth Standards (2006)"
SOURCE_URL = "https://www.who.int/tools/child-growth-standards/standards"

_CDN = (
    "https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators"
)

# (indicator, sex, part, key column header, expected keys, file name, pinned URL).
# `part` merges the split WHO files: for the monthly indicators the 0-2 and 2-5 files
# are halves of one 0-60 table; for weight-for-length/height they are the two subtables.
# URLs verified 2026-09-01; the sfvrsn query strings pin the exact revisions.
MONTHS_0_60 = [m / 1 for m in range(61)]
MONTHS_0_24 = list(range(0, 25))
MONTHS_24_60 = list(range(24, 61))
LENGTH_KEYS = [round(45.0 + i * 0.1, 1) for i in range(651)]  # 45.0-110.0 cm
HEIGHT_KEYS = [round(65.0 + i * 0.1, 1) for i in range(551)]  # 65.0-120.0 cm

FILES: tuple[tuple[str, str, str | None, str, list[float], str, str], ...] = (
    # -- weight-for-age: one file per sex covers 0-60 months --------------------------------
    (
        "weight_for_age",
        "female",
        None,
        "Month",
        MONTHS_0_60,
        "wfa_girls_0-to-5-years_zscores.xlsx",
        f"{_CDN}/weight-for-age/wfa_girls_0-to-5-years_zscores.xlsx?sfvrsn=4c03b8db_7",
    ),
    (
        "weight_for_age",
        "male",
        None,
        "Month",
        MONTHS_0_60,
        "wfa_boys_0-to-5-years_zscores.xlsx",
        f"{_CDN}/weight-for-age/wfa_boys_0-to-5-years_zscores.xlsx?sfvrsn=97a05331_9",
    ),
    # -- length/height-for-age: 0-2 (recumbent length) + 2-5 (standing height) --------------
    (
        "length_height_for_age",
        "female",
        "0-2",
        "Month",
        MONTHS_0_24,
        "lhfa_girls_0-to-2-years_zscores.xlsx",
        f"{_CDN}/length-height-for-age/lhfa_girls_0-to-2-years_zscores.xlsx?sfvrsn=e9e66a95_11",
    ),
    (
        "length_height_for_age",
        "female",
        "2-5",
        "Month",
        MONTHS_24_60,
        "lhfa_girls_2-to-5-years_zscores.xlsx",
        f"{_CDN}/length-height-for-age/lhfa_girls_2-to-5-years_zscores.xlsx?sfvrsn=2ec187b9_11",
    ),
    (
        "length_height_for_age",
        "male",
        "0-2",
        "Month",
        MONTHS_0_24,
        "lhfa_boys_0-to-2-years_zscores.xlsx",
        f"{_CDN}/length-height-for-age/lhfa_boys_0-to-2-years_zscores.xlsx?sfvrsn=30e044c_9",
    ),
    (
        "length_height_for_age",
        "male",
        "2-5",
        "Month",
        MONTHS_24_60,
        "lhfa_boys_2-to-5-years_zscores.xlsx",
        f"{_CDN}/length-height-for-age/lhfa_boys_2-to-5-years_zscores.xlsx?sfvrsn=17e5ad91_9",
    ),
    # -- weight-for-length (under 24 months) and weight-for-height (from 24 months) ---------
    # The standard z-score files step by 0.5 cm; the 0.1 cm resolution the assessment
    # keys on is in WHO's expanded tables, so those are the pinned sources here.
    (
        "weight_for_length_height",
        "female",
        "length",
        "Length",
        LENGTH_KEYS,
        "wfl-girls-zscore-expanded-table.xlsx",
        f"{_CDN}/weight-for-length-height/expanded-tables/wfl-girls-zscore-expanded-table.xlsx?sfvrsn=db7b5d6b_8",
    ),
    (
        "weight_for_length_height",
        "female",
        "height",
        "Height",
        HEIGHT_KEYS,
        "wfh-girls-zscore-expanded-tables.xlsx",
        f"{_CDN}/weight-for-length-height/expanded-tables/wfh-girls-zscore-expanded-tables.xlsx?sfvrsn=daac732c_8",
    ),
    (
        "weight_for_length_height",
        "male",
        "length",
        "Length",
        LENGTH_KEYS,
        "wfl-boys-zscore-expanded-table.xlsx",
        f"{_CDN}/weight-for-length-height/expanded-tables/wfl-boys-zscore-expanded-table.xlsx?sfvrsn=d307434f_8",
    ),
    (
        "weight_for_length_height",
        "male",
        "height",
        "Height",
        HEIGHT_KEYS,
        "wfh-boys-zscore-expanded-tables.xlsx",
        f"{_CDN}/weight-for-length-height/expanded-tables/wfh-boys-zscore-expanded-tables.xlsx?sfvrsn=ac60cb13_8",
    ),
    # -- BMI-for-age: 0-2 + 2-5 (note WHO's own "zcores" filename for boys 0-2) -------------
    (
        "bmi_for_age",
        "female",
        "0-2",
        "Month",
        MONTHS_0_24,
        "bmi_girls_0-to-2-years_zscores.xlsx",
        f"{_CDN}/body-mass-index-for-age/bmi_girls_0-to-2-years_zscores.xlsx?sfvrsn=2be9859c_7",
    ),
    (
        "bmi_for_age",
        "female",
        "2-5",
        "Month",
        MONTHS_24_60,
        "bmi_girls_2-to-5-years_zscores.xlsx",
        f"{_CDN}/body-mass-index-for-age/bmi_girls_2-to-5-years_zscores.xlsx?sfvrsn=452aca36_7",
    ),
    (
        "bmi_for_age",
        "male",
        "0-2",
        "Month",
        MONTHS_0_24,
        "bmi_boys_0-to-2-years_zcores.xlsx",
        f"{_CDN}/body-mass-index-for-age/bmi_boys_0-to-2-years_zcores.xlsx?sfvrsn=df725cc9_7",
    ),
    (
        "bmi_for_age",
        "male",
        "2-5",
        "Month",
        MONTHS_24_60,
        "bmi_boys_2-to-5-years_zscores.xlsx",
        f"{_CDN}/body-mass-index-for-age/bmi_boys_2-to-5-years_zscores.xlsx?sfvrsn=73010c9b_5",
    ),
)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "build_growth_tables/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def read_lms(data: bytes, key_header: str, name: str) -> list[list[float]]:
    """[[key, L, M, S], ...] from the first sheet, located by header name."""
    sheet = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell).strip() if cell is not None else "" for cell in next(rows)]
    try:
        columns = {label: header.index(label) for label in (key_header, "L", "M", "S")}
    except ValueError as exc:
        raise SystemExit(f"{name}: expected columns {key_header}, L, M, S in {header}") from exc
    out = []
    for row in rows:
        if row[columns[key_header]] is None:
            continue
        out.append([float(row[columns[label]]) for label in (key_header, "L", "M", "S")])
    return out


def check_keys(rows: list[list[float]], expected: list[float], name: str) -> None:
    keys = [round(row[0], 1) for row in rows]
    want = [round(key, 1) for key in expected]
    if keys != want:
        raise SystemExit(
            f"{name}: keys are not the expected contiguous range "
            f"({want[0]}..{want[-1]}, {len(want)} rows); got {len(keys)} rows "
            f"{keys[0]}..{keys[-1]}"
        )


def main() -> None:
    tables: dict[str, dict[str, object]] = {}
    files_meta: list[dict[str, str]] = []
    downloads: dict[str, bytes] = {}

    for indicator, sex, part, key_header, expected, name, url in FILES:
        print(f"fetching {name} ...", file=sys.stderr)
        data = fetch(url)
        downloads[name] = data
        files_meta.append({"name": name, "url": url, "sha256": hashlib.sha256(data).hexdigest()})
        rows = read_lms(data, key_header, name)
        check_keys(rows, expected, name)
        by_sex = tables.setdefault(indicator, {})
        if part in ("0-2", "2-5"):
            # Month 24 appears in both files; WHO's 2-5 charts (standing height) own it.
            merged = by_sex.setdefault(sex, [])
            merged.extend(row for row in rows if part == "2-5" or row[0] < 24)
            merged.sort(key=lambda row: row[0])
        elif part in ("length", "height"):
            by_sex.setdefault(sex, {})[part] = rows
        else:
            by_sex[sex] = rows

    for indicator in ("weight_for_age", "length_height_for_age", "bmi_for_age"):
        for sex in ("female", "male"):
            check_keys(tables[indicator][sex], MONTHS_0_60, f"{indicator}/{sex} (merged)")

    document = {
        "version": 1,
        "source": SOURCE,
        "source_url": SOURCE_URL,
        "retrieved": dt.date.today().isoformat(),
        "files": files_meta,
        "tables": tables,
    }
    OUT_PATH.write_text(
        "# Generated by scripts/build_growth_tables.py — do not edit by hand.\n"
        + yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"wrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
