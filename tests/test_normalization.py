from gesha.normalization.normalize import normalize_process, normalize_country, normalize_tasting_notes


def test_normalize_process_variants() -> None:
    assert normalize_process("Fully Washed") == "washed"
    assert normalize_process("wet process") == "washed"
    assert normalize_process("honey") == "honey"


def test_normalize_country_aliases() -> None:
    assert normalize_country("canada") == "Canada"
    assert normalize_country("Ethiopia") == "Ethiopia"


def test_normalize_tasting_notes_from_string() -> None:
    assert normalize_tasting_notes("berry; chocolate; floral") == ["berry", "chocolate", "floral"]
    assert normalize_tasting_notes("Maple, spice") == ["maple", "spice"]
