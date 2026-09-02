"""WHO growth standards: table loading and validation (day-6-growth-assessment)."""

import statistics
from pathlib import Path

import pytest
import yaml

from backend.models.enums import Sex
from backend.nutrition.growth import (
    CURVE_PERCENTILES,
    DEFAULT_GROWTH_TABLE_PATH,
    GrowthIndicator,
    LoadedGrowthTable,
    assess_growth,
    band_for,
    get_growth_table,
    get_reference_curves,
    load_growth_table,
    reference,
    reference_curves,
    reset_growth_table_cache,
    value_at_percentile,
    who_label_for,
    z_score,
)
from backend.schemas.tools import GrowthAssessmentInput

REPO_ROOT = Path(__file__).parent.parent
COMMITTED = REPO_ROOT / DEFAULT_GROWTH_TABLE_PATH


@pytest.fixture(scope="module")
def table() -> LoadedGrowthTable:
    return load_growth_table(COMMITTED)


class TestLoading:
    def test_committed_file_loads_with_provenance(self, table: LoadedGrowthTable) -> None:
        assert table.source == "WHO Child Growth Standards (2006)"
        assert table.source_url.startswith("https://www.who.int/")
        assert len(table.table.files) == 14
        assert all(len(f.sha256) == 64 for f in table.table.files)

    def test_every_monthly_indicator_covers_both_sexes_0_to_60(
        self, table: LoadedGrowthTable
    ) -> None:
        for indicator in (
            GrowthIndicator.WEIGHT_FOR_AGE,
            GrowthIndicator.LENGTH_HEIGHT_FOR_AGE,
            GrowthIndicator.BMI_FOR_AGE,
        ):
            for sex in Sex:
                for month in (0, 24, 60):
                    big_l, big_m, big_s = table.monthly(indicator, sex, month)
                    assert big_m > 0 and big_s > 0

    def test_length_and_height_subtables_cover_their_ranges(self, table: LoadedGrowthTable) -> None:
        for sex in Sex:
            assert table.weight_for_lh_range(sex, 8) == (45.0, 110.0)
            assert table.weight_for_lh_range(sex, 24) == (65.0, 120.0)
            assert table.weight_for_lh(sex, 8, 69.0) is not None
            assert table.weight_for_lh(sex, 8, 40.0) is None  # below the length table

    def test_cached_accessor_and_reset(self) -> None:
        reset_growth_table_cache()
        first = get_growth_table()
        assert get_growth_table() is first
        reset_growth_table_cache()
        assert get_growth_table() is not first

    def test_missing_s_parameter_fails_naming_indicator_sex_and_key(self, tmp_path: Path) -> None:
        raw = yaml.safe_load(COMMITTED.read_text(encoding="utf-8"))
        # Drop the S value from one row: girls' weight-for-age at month 7.
        raw["tables"]["weight_for_age"]["female"][7] = raw["tables"]["weight_for_age"]["female"][7][
            :3
        ]
        broken = tmp_path / "broken.yaml"
        broken.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(ValueError, match=r"weight_for_age/female key 7.*\[key, L, M, S\]"):
            load_growth_table(broken)

    def test_non_contiguous_months_fail(self, tmp_path: Path) -> None:
        raw = yaml.safe_load(COMMITTED.read_text(encoding="utf-8"))
        del raw["tables"]["bmi_for_age"]["male"][30]
        broken = tmp_path / "gap.yaml"
        broken.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(ValueError, match="bmi_for_age/male key 31.*contiguous"):
            load_growth_table(broken)

    def test_negative_s_fails(self, tmp_path: Path) -> None:
        raw = yaml.safe_load(COMMITTED.read_text(encoding="utf-8"))
        raw["tables"]["length_height_for_age"]["male"][3][3] = -0.01
        broken = tmp_path / "negative.yaml"
        broken.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(ValueError, match="length_height_for_age/male key 3.*S must be > 0"):
            load_growth_table(broken)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_growth_table(tmp_path / "absent.yaml")


def test_no_langchain_import_under_nutrition() -> None:
    """Day 4 Decision 1: no growth number can touch the model."""
    hits = [
        path
        for path in (REPO_ROOT / "backend" / "nutrition").glob("*.py")
        if "langchain" in path.read_text(encoding="utf-8")
    ]
    assert hits == []


def child(
    age: int, weight: float, height: float | None = None, sex: Sex = Sex.FEMALE
) -> GrowthAssessmentInput:
    return GrowthAssessmentInput(age_months=age, sex=sex, weight_kg=weight, height_cm=height)


def indicator(result, key: str):
    return next(i for i in result.indicators if i.indicator == key)


class TestZScoreArithmetic:
    def test_median_is_z_zero_and_the_50th_percentile(self, table: LoadedGrowthTable) -> None:
        _, big_m, _ = table.monthly(GrowthIndicator.WEIGHT_FOR_AGE, Sex.FEMALE, 8)
        result = assess_growth(child(8, weight=big_m), table)
        wfa = indicator(result, "weight_for_age")
        assert wfa.z_score == 0.00
        assert wfa.percentile == 50.0

    def test_the_derived_plus_two_sd_value_scores_z_two(self, table: LoadedGrowthTable) -> None:
        big_l, big_m, big_s = table.monthly(GrowthIndicator.WEIGHT_FOR_AGE, Sex.FEMALE, 8)
        at_sd2 = big_m * (1 + big_l * big_s * 2) ** (1 / big_l)
        assert z_score(at_sd2, big_l, big_m, big_s, tail_adjust=True) == pytest.approx(2.0)

    def test_tail_adjustment_engages_for_weight_for_age_above_three(
        self, table: LoadedGrowthTable
    ) -> None:
        big_l, big_m, big_s = table.monthly(GrowthIndicator.WEIGHT_FOR_AGE, Sex.FEMALE, 8)
        sd = lambda t: big_m * (1 + big_l * big_s * t) ** (1 / big_l)  # noqa: E731
        heavy = sd(3) + 2 * (sd(3) - sd(2))  # two SD-widths above the +3 curve
        adjusted = z_score(heavy, big_l, big_m, big_s, tail_adjust=True)
        raw = z_score(heavy, big_l, big_m, big_s, tail_adjust=False)
        assert adjusted == pytest.approx(5.0)  # WHO's linear extrapolation: 3 + 2
        assert adjusted != pytest.approx(raw)

    def test_length_for_age_is_never_tail_adjusted(self, table: LoadedGrowthTable) -> None:
        big_l, big_m, big_s = table.monthly(GrowthIndicator.LENGTH_HEIGHT_FOR_AGE, Sex.FEMALE, 8)
        very_tall = big_m * 1.25
        result = assess_growth(child(8, weight=8.5, height=very_tall), table)
        lhfa = indicator(result, "length_height_for_age")
        raw = z_score(very_tall, big_l, big_m, big_s, tail_adjust=False)
        assert raw > 3
        assert lhfa.z_score == round(raw, 2)

    def test_girls_and_boys_differ_at_equal_inputs(self, table: LoadedGrowthTable) -> None:
        girl = assess_growth(child(8, weight=8.5, height=69.0, sex=Sex.FEMALE), table)
        boy = assess_growth(child(8, weight=8.5, height=69.0, sex=Sex.MALE), table)
        for key in (
            "weight_for_age",
            "length_height_for_age",
            "weight_for_length_height",
            "bmi_for_age",
        ):
            assert indicator(girl, key).z_score != indicator(boy, key).z_score, key
            assert indicator(girl, key).percentile != indicator(boy, key).percentile, key

    def test_identical_inputs_give_equal_results(self, table: LoadedGrowthTable) -> None:
        first = assess_growth(child(8, weight=8.5, height=69.0), table)
        second = assess_growth(child(8, weight=8.5, height=69.0), table)
        assert first == second


class TestBandsAndLabels:
    @pytest.mark.parametrize(
        ("z", "band"),
        [
            (-3.01, "well_below"),
            (-3.0, "below"),
            (-2.01, "below"),
            (-2.0, "expected"),
            (0.0, "expected"),
            (2.0, "expected"),
            (2.01, "above"),
            (3.0, "above"),
            (3.01, "well_above"),
        ],
    )
    def test_who_cut_offs(self, z: float, band: str) -> None:
        assert band_for(GrowthIndicator.WEIGHT_FOR_AGE, z) == band

    def test_who_labels_follow_the_kb_cut_off_table(self) -> None:
        lhfa = GrowthIndicator.LENGTH_HEIGHT_FOR_AGE
        wfa = GrowthIndicator.WEIGHT_FOR_AGE
        wflh = GrowthIndicator.WEIGHT_FOR_LENGTH_HEIGHT
        bmi = GrowthIndicator.BMI_FOR_AGE
        assert who_label_for(lhfa, "below") == "stunted"
        assert who_label_for(lhfa, "well_below") == "severely stunted"
        assert who_label_for(lhfa, "above") is None  # WHO's table has "—"
        assert who_label_for(wfa, "below") == "underweight"
        assert who_label_for(wfa, "well_below") == "severely underweight"
        assert who_label_for(wfa, "above") is None  # tallness is not overweight
        assert who_label_for(wflh, "above") == "overweight"
        assert who_label_for(wflh, "well_above") == "obese"
        assert who_label_for(bmi, "below") == "wasted"
        assert who_label_for(bmi, "well_below") == "severely wasted"
        assert who_label_for(wfa, "expected") is None

    def test_a_stunted_length_is_banded_and_labelled(self, table: LoadedGrowthTable) -> None:
        # Boys 8 months: WHO's published −2 SD is 66.2 cm; 64.9 cm sits between −3 and −2.
        result = assess_growth(child(8, weight=8.5, height=64.9, sex=Sex.MALE), table)
        lhfa = indicator(result, "length_height_for_age")
        assert lhfa.band == "below"
        assert lhfa.who_label == "stunted"


class TestAgeSelectsTheLengthOrHeightTable:
    def test_under_24_months_uses_the_length_table(self, table: LoadedGrowthTable) -> None:
        assert table.weight_for_lh(Sex.FEMALE, 8, 80.0) == pytest.approx(
            table._by_cm[(Sex.FEMALE, "length")][80.0]
        )
        assert table.weight_for_lh(Sex.FEMALE, 24, 80.0) == pytest.approx(
            table._by_cm[(Sex.FEMALE, "height")][80.0]
        )

    def test_same_measurements_score_differently_across_the_boundary(
        self, table: LoadedGrowthTable
    ) -> None:
        before = assess_growth(child(23, weight=11.0, height=85.0), table)
        after = assess_growth(child(24, weight=11.0, height=85.0), table)
        assert (
            indicator(before, "weight_for_length_height").z_score
            != indicator(after, "weight_for_length_height").z_score
        )


class TestSkippingNeverFailing:
    def test_no_height_computes_weight_for_age_only(self, table: LoadedGrowthTable) -> None:
        result = assess_growth(child(8, weight=8.5), table)
        assert [i.indicator for i in result.indicators] == ["weight_for_age"]
        assert [s.indicator for s in result.skipped] == [
            "length_height_for_age",
            "weight_for_length_height",
            "bmi_for_age",
        ]
        for skipped in result.skipped:
            assert "length or height" in skipped.reason and "side panel" not in skipped.reason

    def test_out_of_range_length_skips_weight_for_length_only(
        self, table: LoadedGrowthTable
    ) -> None:
        result = assess_growth(child(2, weight=4.5, height=40.0), table)
        assert [i.indicator for i in result.indicators] == [
            "weight_for_age",
            "length_height_for_age",
            "bmi_for_age",
        ]
        [skipped] = result.skipped
        assert skipped.indicator == "weight_for_length_height"
        assert "45" in skipped.reason and "110" in skipped.reason

    def test_note_states_granularity_and_the_height_reading(self, table: LoadedGrowthTable) -> None:
        young = assess_growth(child(8, weight=8.5, height=69.0), table)
        assert "completed month" in young.note and "recumbent length" in young.note
        older = assess_growth(child(30, weight=13.0, height=92.0), table)
        assert "standing height" in older.note
        assert young.source == "WHO Child Growth Standards (2006)"


class TestWhoOracleValues:
    """Reference triples typed by hand from WHO's published z-score tables (SD2neg/SD0/SD2
    columns, retrieved 2026-09-01) — never derived from this codebase."""

    def test_girls_8_months_weight_for_age(self, table: LoadedGrowthTable) -> None:
        result = assess_growth(child(8, weight=7.9487), table)  # WHO M for this row
        wfa = indicator(result, "weight_for_age")
        assert wfa.reference.sd2neg == 6.3
        assert wfa.reference.median == 7.9
        assert wfa.reference.sd2pos == 10.2
        assert wfa.z_score == 0.00

    def test_boys_8_months_length_for_age(self, table: LoadedGrowthTable) -> None:
        result = assess_growth(child(8, weight=8.5, height=70.5994, sex=Sex.MALE), table)
        lhfa = indicator(result, "length_height_for_age")
        assert lhfa.reference.sd2neg == 66.2
        assert lhfa.reference.median == 70.6
        assert lhfa.reference.sd2pos == 75.0
        assert lhfa.z_score == 0.00

    def test_girls_30_months_bmi_for_age(self, table: LoadedGrowthTable) -> None:
        # Weight and height chosen so BMI equals WHO's median of 15.5276 for this row.
        result = assess_growth(child(30, weight=12.5723, height=90.0), table)
        bmi = indicator(result, "bmi_for_age")
        assert bmi.reference.sd2neg == 13.2
        assert bmi.reference.median == 15.5
        assert bmi.reference.sd2pos == 18.5
        assert bmi.z_score == 0.00


class TestReferenceCurves:
    """growth-charts design Decision 1: the LMS read the other way, sampled for the charts."""

    def test_value_at_the_50th_is_the_median_and_round_trips_z(
        self, table: LoadedGrowthTable
    ) -> None:
        big_l, big_m, big_s = table.monthly(GrowthIndicator.WEIGHT_FOR_AGE, Sex.FEMALE, 8)
        assert value_at_percentile(50, big_l, big_m, big_s) == pytest.approx(big_m)
        for p in CURVE_PERCENTILES:
            value = value_at_percentile(p, big_l, big_m, big_s)
            z = z_score(value, big_l, big_m, big_s, tail_adjust=True)
            assert z == pytest.approx(statistics.NormalDist().inv_cdf(p / 100)), p

    def test_four_sets_with_nine_ordered_curves(self, table: LoadedGrowthTable) -> None:
        sets = reference_curves(table, Sex.FEMALE, use_height_table=False)
        assert [s.indicator for s in sets] == [
            "weight_for_age",
            "length_height_for_age",
            "weight_for_length_height",
            "bmi_for_age",
        ]
        for curve_set in sets:
            assert [c.percentile for c in curve_set.curves] == list(CURVE_PERCENTILES)
            for i in range(len(curve_set.xs)):
                # Non-decreasing at every x; rounding to one decimal can make neighbouring
                # percentiles coincide at the smallest sizes (2.4 kg at 45 cm).
                column = [c.values[i] for c in curve_set.curves]
                assert column == sorted(column), (curve_set.indicator, curve_set.xs[i])
            at_month_8 = [c.values[8] for c in curve_set.curves]
            assert len(set(at_month_8)) == 9, curve_set.indicator

    def test_monthly_sets_span_0_to_60_and_the_50th_is_the_published_median(
        self, table: LoadedGrowthTable
    ) -> None:
        sets = {s.indicator: s for s in reference_curves(table, Sex.MALE, use_height_table=False)}
        for key, indicator in (
            ("weight_for_age", GrowthIndicator.WEIGHT_FOR_AGE),
            ("length_height_for_age", GrowthIndicator.LENGTH_HEIGHT_FOR_AGE),
            ("bmi_for_age", GrowthIndicator.BMI_FOR_AGE),
        ):
            curve_set = sets[key]
            assert curve_set.x_unit == "months" and curve_set.x_label_table is None
            assert curve_set.xs == [float(m) for m in range(61)]
            p50 = next(c for c in curve_set.curves if c.percentile == 50)
            for month in (0, 8, 24, 60):
                lms = table.monthly(indicator, Sex.MALE, month)
                assert round(p50.values[month], 1) == reference(*lms).median, (key, month)

    def test_length_or_height_table_by_flag(self, table: LoadedGrowthTable) -> None:
        length = reference_curves(table, Sex.FEMALE, use_height_table=False)[2]
        height = reference_curves(table, Sex.FEMALE, use_height_table=True)[2]
        assert length.x_unit == "cm" and length.x_label_table == "length"
        assert (length.xs[0], length.xs[-1], len(length.xs)) == (45.0, 110.0, 66)
        assert height.x_label_table == "height"
        assert (height.xs[0], height.xs[-1], len(height.xs)) == (65.0, 120.0, 56)
        assert length.y_unit == "kg" and sets_differ(length, height)

    def test_cached_accessor_is_per_sex_and_table(self) -> None:
        reset_growth_table_cache()
        girls = get_reference_curves(Sex.FEMALE, False)
        assert get_reference_curves(Sex.FEMALE, False) is girls
        assert get_reference_curves(Sex.MALE, False) is not girls
        assert (
            girls[0].curves[4].values != get_reference_curves(Sex.MALE, False)[0].curves[4].values
        )


def sets_differ(a, b) -> bool:
    """Curves for the overlapping 65-110 cm differ between the length and height tables."""
    a_at_80 = a.curves[4].values[a.xs.index(80.0)]
    b_at_80 = b.curves[4].values[b.xs.index(80.0)]
    return a_at_80 != b_at_80
