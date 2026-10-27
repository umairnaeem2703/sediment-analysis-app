"""C-X-05: INPUT_FORMAT.md, the guide the user follows, lists every canonical label the program reads."""

from src.services import labels
from src.utils.paths import resource_path


def test_c_x_05_the_input_guide_names_every_canonical_label():
    guide = resource_path("INPUT_FORMAT.md").read_text(encoding="utf-8")
    canonical = {
        *labels.BASIN_TABLE,
        *labels.ZONAL,
        *labels.SHEET_REQUIRED,
        *labels.SHEET_OPTIONAL,
        *labels.FRACTIONS_REQUIRED,
        *labels.FRACTIONS_OPTIONAL,
        *labels.DAILY_FLOW,
        *labels.DAILY_FLOW_OPTIONAL,
        *labels.DSI_REQUIRED,
        *labels.DSI_OPTIONAL,
    }

    assert [label for label in sorted(canonical) if f"`{label}`" not in guide] == []
