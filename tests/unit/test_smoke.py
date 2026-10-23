def test_import_smoke():
    import src.core
    import src.services
    import src.utils.paths

    assert src.core and src.services and src.utils.paths
