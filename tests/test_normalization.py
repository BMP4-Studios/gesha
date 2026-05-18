from gesha.normalization.normalize import normalize_process, normalize_country, normalize_tasting_notes, remove_emojis


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


def test_remove_emojis() -> None:
    assert remove_emojis("LOVEBUZZ 😵‍💫 💙") == "LOVEBUZZ"
    assert remove_emojis("‧₊˚❀༉‧₊˚. Bouquet. 𝒷𝓁𝑜𝓈𝓈𝑜𝓂𝑒𝒹 𝑒𝒹𝒾𝓉𝒾𝑜𝓃") == ". Bouquet. blossomed edition"
    assert normalize_tasting_notes("Apricot • Honey • Orange") == ["apricot", "honey", "orange"]
    assert normalize_tasting_notes("Honey. Caramel. Chocolate.") == ["caramel", "chocolate", "honey"]
