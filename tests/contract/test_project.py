import hashlib
import json

import pytest

from src.services.project import SCHEMA_VERSION, Dam, Flow, Project, slugify


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_c_m1_01_saved_project_reopens_identically(tmp_path):
    project = Project.new(tmp_path / "region", "Sakarya Region")
    project.inputs["basins"] = "inputs/basins.csv"
    project.inputs["fractions"] = "inputs/fractions.csv"
    cubuk = project.add_dam("Çubuk 1")
    cubuk.sheet = "inputs/dams/cubuk_1.csv"
    cubuk.flow = Flow(path="inputs/flow/cubuk_1_flow.csv", sigma=0.4, seed=7)
    cubuk.commissioning_year = 1965
    cubuk.h_min_m = 892.5
    cubuk.shape_class = "hill"
    project.add_dam("Kavşakkaya")
    project.save()

    reopened = Project.open(tmp_path / "region")

    assert reopened == project
    assert [d.slug for d in reopened.dams] == ["cubuk_1", "kavsakkaya"]
    assert reopened.dams[0].trap_efficiency_pct == 100.0
    assert reopened.dams[1].analysis_year is None


def test_c_m1_01_project_json_is_utf8_with_schema_version(tmp_path):
    project = Project.new(tmp_path / "p", "Çubuk Study")

    data = json.loads((tmp_path / "p" / "project.json").read_text(encoding="utf-8"))

    assert data["schema_version"] == SCHEMA_VERSION
    assert data["name"] == "Çubuk Study"
    assert (project.folder / "inputs").is_dir()
    assert (project.folder / "outputs").is_dir()


def test_c_m1_01_newer_schema_version_is_a_clear_error(tmp_path):
    project = Project.new(tmp_path / "p", "x")
    path = project.folder / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = SCHEMA_VERSION + 1
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=r"newer.*schema_version 2.*supports 1"):
        Project.open(project.folder)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "project.json"),
        ("{not json", "not valid JSON"),
        ('{"name": "x"}', "schema_version"),
        ('{"schema_version": 1, "dams": [{"slug": "a"}]}', "malformed"),
        ('{"schema_version": 1, "dams": ["x"]}', "malformed"),
        ('{"schema_version": 1, "dams": [null]}', "malformed"),
        ('{"schema_version": 1, "dams": [{"name": "a", "slug": "a", "flow": null}]}', "malformed"),
        ('{"schema_version": 1, "inputs": null}', "malformed"),
        ('{"schema_version": 1, "inputs": []}', "malformed"),
    ],
)
def test_c_m1_01_unreadable_project_errors_name_the_problem(tmp_path, content, message):
    folder = tmp_path / "p"
    folder.mkdir()
    if content is not None:
        (folder / "project.json").write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        Project.open(folder)


def test_c_m1_01_save_leaves_no_temporary_file(tmp_path):
    project = Project.new(tmp_path / "p", "x")
    project.save()

    assert sorted(p.name for p in project.folder.iterdir()) == ["inputs", "outputs", "project.json"]


def test_c_m1_01_new_refuses_to_overwrite_an_existing_project(tmp_path):
    Project.new(tmp_path / "p", "first")

    with pytest.raises(ValueError, match="already contains a project"):
        Project.new(tmp_path / "p", "second")


def test_c_m1_01_dam_slugs_are_ascii_and_unique(tmp_path):
    assert slugify("Çubuk 1") == "cubuk_1"
    assert slugify("İznik Barajı") == "iznik_baraji"
    project = Project.new(tmp_path / "p", "x")
    project.add_dam("Çubuk 1")

    with pytest.raises(ValueError, match="cubuk_1"):
        project.add_dam("cubuk 1")
    with pytest.raises(ValueError, match="slug"):
        project.add_dam("???")


def test_c_m1_02_import_copies_bytes_and_leaves_the_original_alone(tmp_path):
    source = tmp_path / "downloads" / "master_yield.csv"
    source.parent.mkdir()
    source.write_bytes("Dam Name,Drainage Area (km2)\r\nÇubuk 1,834.7\r\n".encode("cp1254"))
    before = _sha256(source)
    project = Project.new(tmp_path / "p", "x")

    relative = project.import_file(source, "inputs/basins.csv")

    assert relative == "inputs/basins.csv"
    assert _sha256(project.folder / relative) == before
    assert _sha256(source) == before


def test_c_m1_02_reimporting_the_projects_own_copy_is_a_no_op(tmp_path):
    source = tmp_path / "s.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    project = Project.new(tmp_path / "p", "x")
    relative = project.import_file(source, "inputs/basins.csv")
    before = _sha256(project.folder / relative)

    again = project.import_file(project.folder / relative, "inputs/basins.csv")

    assert again == relative
    assert _sha256(project.folder / relative) == before


def test_c_m1_02_import_creates_subfolders_and_returns_a_posix_path(tmp_path):
    source = tmp_path / "sheet.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    project = Project.new(tmp_path / "p", "x")

    relative = project.import_file(source, "inputs/dams/cubuk_1.csv")

    assert relative == "inputs/dams/cubuk_1.csv"
    assert (project.folder / "inputs" / "dams" / "cubuk_1.csv").is_file()


@pytest.mark.parametrize("destination", ["../escape.csv", "outputs/x.csv", "/abs/x.csv", "inputs/../../x.csv"])
def test_c_m1_02_import_refuses_destinations_outside_inputs(tmp_path, destination):
    source = tmp_path / "s.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    project = Project.new(tmp_path / "p", "x")

    with pytest.raises(ValueError, match="inputs"):
        project.import_file(source, destination)


def test_c_m1_02_import_of_a_missing_file_names_it(tmp_path):
    project = Project.new(tmp_path / "p", "x")

    with pytest.raises(FileNotFoundError, match="nowhere.csv"):
        project.import_file(tmp_path / "nowhere.csv", "inputs/basins.csv")


def test_dam_dataclass_defaults():
    dam = Dam(name="A", slug="a")
    assert dam.trap_efficiency_pct == 100.0
    assert dam.flow == Flow()


def test_c_m1_01_phi_round_trips_and_a_project_saved_without_it_opens_with_zero(tmp_path):
    project = Project.new(tmp_path / "p", "x")
    dam = project.add_dam("A")
    dam.flow = Flow(path="inputs/flow/a_flow.csv", sigma=0.4, seed=7, phi=0.7)
    project.save()
    assert Project.open(tmp_path / "p").dams[0].flow.phi == 0.7

    file = tmp_path / "p" / "project.json"
    data = json.loads(file.read_text(encoding="utf-8"))
    del data["dams"][0]["flow"]["phi"]
    file.write_text(json.dumps(data), encoding="utf-8")

    assert Project.open(tmp_path / "p").dams[0].flow.phi == 0.0


def test_c_x_07_an_imported_file_is_recorded_in_the_project_log(tmp_path):
    from src.utils.log import attach_project_log, detach_project_log

    source = tmp_path / "basins.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    project = Project.new(tmp_path / "project", "Region")
    path = attach_project_log(project.folder)

    project.import_file(source, "inputs/basins.csv")
    detach_project_log()

    assert f"Imported {source} as inputs/basins.csv." in path.read_text(encoding="utf-8")
