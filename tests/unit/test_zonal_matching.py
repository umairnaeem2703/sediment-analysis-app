"""U-M2-01: matching a dam's sub-basins to zonal means (FR-M2-01)."""

import pandas as pd

from src.core.rusle import ZonalMatcher
from src.services.regional import SUBBASIN


def _lookup(*rows):
    return ZonalMatcher.build_lookup(pd.DataFrame(rows, columns=[SUBBASIN, "MEAN"]))


def test_u_m2_01_an_exact_name_is_matched():
    lookup = _lookup(("Ankara Alt Havzası", 3.1), ("Göksu Alt Havzası", 2.8))

    resolved = ZonalMatcher.resolve_all(lookup, ["Ankara Alt Havzası"])

    assert resolved.means == [3.1] and resolved.loose == {} and resolved.unresolved == []


def test_u_m2_01_spelling_variants_of_the_same_name_are_alias_matches():
    lookup = _lookup(("Asagi sakarya Alt Havzası", 3.23))

    names = ["Aşağı Sakarya Alt Havzası", "ASAGI SAKARYA", "Sub-basin Asagi Sakarya"]
    resolved = ZonalMatcher.resolve_all(lookup, names)

    assert resolved.means == [3.23, 3.23, 3.23]
    assert resolved.loose == {} and resolved.unresolved == []


def test_u_m2_01_a_loose_match_is_accepted_when_every_candidate_carries_one_value():
    lookup = _lookup(("Orta Sakarya Alt Havzası", 2.5))

    resolved = ZonalMatcher.resolve_all(lookup, ["Sakarya Alt Havzası"])

    assert resolved.means == [2.5]
    assert list(resolved.loose) == ["Sakarya Alt Havzası"]
    assert resolved.unresolved == []


def test_u_m2_01_a_loose_match_with_candidates_of_different_values_is_ambiguous():
    lookup = _lookup(("Orta Sakarya Alt Havzası", 2.5), ("Asagi Sakarya Alt Havzası", 3.2))

    resolved = ZonalMatcher.resolve_all(lookup, ["Sakarya Alt Havzası"])

    assert resolved.means == [None]
    assert len(resolved.unresolved) == 1
    assert resolved.unresolved[0].startswith("Sakarya Alt Havzası") and "ambiguous" in resolved.unresolved[0]


def test_u_m2_01_a_name_with_no_zonal_entry_is_unresolved():
    lookup = _lookup(("Ankara Alt Havzası", 3.1))

    resolved = ZonalMatcher.resolve_all(lookup, ["Konya Alt Havzası", "Ankara Alt Havzası"])

    assert resolved.means == [None, 3.1]
    assert resolved.unresolved == ["Konya Alt Havzası"]


def test_u_m2_01_a_name_listed_twice_with_different_values_matches_neither():
    lookup = _lookup(("Ankara Alt Havzası", 3.1), ("Ankara Alt Havzası", 9.9), ("Göksu Alt Havzası", 2.8))

    resolved = ZonalMatcher.resolve_all(lookup, ["Ankara Alt Havzası", "Göksu Alt Havzası"])

    assert resolved.means == [None, 2.8]
    assert resolved.unresolved == ["Ankara Alt Havzası"]


def test_u_m2_01_a_name_listed_twice_with_the_same_value_still_matches():
    lookup = _lookup(("Ankara Alt Havzası", 3.1), ("Ankara Alt Havzası", 3.1))

    assert ZonalMatcher.resolve_all(lookup, ["Ankara Alt Havzası"]).means == [3.1]


def test_u_m2_01_entries_whose_aliases_collide_do_not_resolve_to_the_last_one():
    lookup = _lookup(("Kuzey Havza 1", 1.0), ("Guney Havza 1", 7.0))

    resolved = ZonalMatcher.resolve_all(lookup, ["Havza 1"])

    assert resolved.means == [None]
