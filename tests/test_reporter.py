import pandas as pd
import pytest

from src.data.reporter import IntegrationModule
from src.utils.paths import read_table, resource_path


def test_broadcast_rusle_output_suspended_volume():
    p2 = pd.DataFrame({"Suspended_Volume_m3": [2000.0]})
    p3 = pd.DataFrame(
        {
            "Year": [2012, 2013, 2014],
            "Bedload_Volume_m3": [100.0, 500.0, 250.0],
        }
    )
    module = IntegrationModule()
    merged, warning = module.merge_sediment_data(p2, p3)
    assert warning is None
    assert len(merged) == 3
    assert list(merged["Year"]) == [2012, 2013, 2014]
    assert (merged["Suspended_Volume_m3"] == 2000.0).all()
    assert list(merged["Total_Volume_m3"]) == [2100.0, 2500.0, 2250.0]

    min_record, max_record = module.locate_extremes(merged)
    assert int(min_record["Year"]) == 2012
    assert min_record["Total_Volume_m3"] == 2100.0
    assert int(max_record["Year"]) == 2013
    assert max_record["Total_Volume_m3"] == 2500.0


def test_broadcast_rusle_output_volume_m3_yr_field():
    p2 = pd.DataFrame({"Volume_m3_yr": [1500.0]})
    p3 = pd.DataFrame(
        {
            "Year": [2012, 2013],
            "Bedload_Volume_m3": [200.0, 400.0],
        }
    )
    merged, warning = IntegrationModule().merge_sediment_data(p2, p3)
    assert warning is None
    assert len(merged) == 2
    assert (merged["Suspended_Volume_m3"] == 1500.0).all()
    assert list(merged["Total_Volume_m3"]) == [1700.0, 1900.0]


def test_merge_sediment_data_validation():
    module = IntegrationModule()
    with pytest.raises(ValueError, match="empty"):
        module.merge_sediment_data(pd.DataFrame(), pd.DataFrame({"Bedload_Volume_m3": [10.0]}))

    with pytest.raises(KeyError, match="Phase 2"):
        module.merge_sediment_data(
            pd.DataFrame({"Wrong_Col": [10.0]}),
            pd.DataFrame({"Bedload_Volume_m3": [10.0]}),
        )

    with pytest.raises(KeyError, match="Phase 3"):
        module.merge_sediment_data(
            pd.DataFrame({"Suspended_Volume_m3": [10.0]}),
            pd.DataFrame({"Wrong_Col": [10.0]}),
        )


def test_bathymetry_clamp_warning():
    bathy = read_table(resource_path("inputs", "bathymetry.csv"))
    module = IntegrationModule()
    volumes, elevations = module.prepare_bathymetry(bathy)
    values, warnings = module.interpolate_elevations(volumes, elevations, [0.0, 9_000_000.0])
    assert len(warnings) == 1 or len(warnings) == 2
    assert values[0] == elevations[0]
    assert values[1] == elevations[-1]


def test_duplicate_volumes_rejected():
    df = pd.DataFrame({"Volume_m3": [1.0, 1.0], "Elevation_m": [10.0, 11.0]})
    with pytest.raises(ValueError, match="unique"):
        IntegrationModule().prepare_bathymetry(df)


def test_locate_extremes_identifies_best_and_worst_case():
    merged_df = pd.DataFrame(
        {
            "Year": [2010, 2011, 2012, 2013],
            "Suspended_Volume_m3": [500.0, 500.0, 500.0, 500.0],
            "Bedload_Volume_m3": [120.0, 450.0, 80.0, 310.0],
            "Total_Volume_m3": [620.0, 950.0, 580.0, 810.0],
        }
    )
    module = IntegrationModule()
    min_rec, max_rec = module.locate_extremes(merged_df)
    assert min_rec["Year"] == 2012
    assert min_rec["Total_Volume_m3"] == 580.0
    assert max_rec["Year"] == 2011
    assert max_rec["Total_Volume_m3"] == 950.0


def test_bathymetric_interpolation_two_extremes():
    df_bathy = pd.DataFrame(
        {
            "Volume_m3": [100.0, 500.0, 1000.0],
            "Elevation_m": [50.0, 75.0, 100.0],
        }
    )
    module = IntegrationModule()
    # 1D linear interpolation for 300 (halfway between 100 and 500 => 62.5m) and 750 (halfway between 500 and 1000 => 87.5m)
    extreme_volumes = [300.0, 750.0]
    elevations = module.interpolate_elevation(df_bathy, extreme_volumes)
    assert len(elevations) == 2
    assert pytest.approx(elevations[0], rel=1e-2) == 62.5
    assert pytest.approx(elevations[1], rel=1e-2) == 87.5


def test_out_of_bounds_target_volume_clamped_warning(caplog):
    import logging

    df_bathy = pd.DataFrame(
        {
            "Volume_m3": [100.0, 500.0, 1000.0],
            "Elevation_m": [50.0, 75.0, 100.0],
        }
    )
    module = IntegrationModule()
    with caplog.at_level(logging.WARNING):
        elev, warnings = module.interpolate_elevation(df_bathy, 1500.0, return_warnings=True)

    assert elev == 100.0  # Clamped to max reservoir elevation
    assert len(warnings) == 1
    assert "clamped to the maximum reservoir height" in warnings[0]
    assert any("clamped to the maximum reservoir height" in record.message for record in caplog.records)


def test_locate_extremes_maps_reservoir_elevations():
    merged_df = pd.DataFrame(
        {
            "Year": [2012, 2013],
            "Total_Volume_m3": [300.0, 750.0],
        }
    )
    df_bathy = pd.DataFrame(
        {
            "Volume_m3": [100.0, 500.0, 1000.0],
            "Elevation_m": [50.0, 75.0, 100.0],
        }
    )
    module = IntegrationModule()
    min_rec, max_rec = module.locate_extremes(merged_df, df_bathy)
    assert "Interpolated_Elevation_m" in min_rec
    assert "Interpolated_Elevation_m" in max_rec
    assert pytest.approx(min_rec["Interpolated_Elevation_m"], rel=1e-2) == 62.5
    assert pytest.approx(max_rec["Interpolated_Elevation_m"], rel=1e-2) == 87.5


def test_phase2_multiple_subbasins_are_summed():
    p2 = read_table(resource_path("inputs", "test_yield_results.csv"))
    p3 = pd.DataFrame({"Year": [2012, 2013], "Bedload_Volume_m3": [0.0, 100.0]})
    merged, _ = IntegrationModule().merge_sediment_data(p2, p3)
    expected = p2["Transported_Volume_m3_yr"].sum()
    assert merged["Suspended_Volume_m3"].iloc[0] == pytest.approx(expected)
    assert merged["Total_Volume_m3"].iloc[1] == pytest.approx(expected + 100.0)


def test_phase2_multi_year_totals_are_averaged():
    p2 = pd.DataFrame({"Year": [2020, 2020, 2021], "Suspended_Volume_m3": [100.0, 200.0, 500.0]})
    p3 = pd.DataFrame({"Year": [2012], "Bedload_Volume_m3": [0.0]})
    merged, _ = IntegrationModule().merge_sediment_data(p2, p3)
    assert merged["Suspended_Volume_m3"].iloc[0] == pytest.approx(400.0)


def test_merge_exported_rusle_and_wilcock_results():
    p2 = read_table(resource_path("inputs", "test_yield_results.csv"))
    p3 = read_table(resource_path("inputs", "test_bedload_results.csv"))
    merged, _ = IntegrationModule().merge_sediment_data(p2, p3)
    assert list(merged["Year"]) == [2012, 2013, 2014]
    tons_2013 = p3["Annual Average Bed Load (metric tons/year)"].iloc[1]
    assert merged["Bedload_Volume_m3"].iloc[1] == pytest.approx(tons_2013 / 2.65)
    min_rec, max_rec = IntegrationModule().locate_extremes(merged)
    assert int(max_rec["Year"]) == 2013
