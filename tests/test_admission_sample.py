from app.services.admission_sample import load_sample_programs


def test_seed_programs_are_grouped_and_weights_sum_to_100():
    programs = load_sample_programs()

    assert [p["code"] for p in programs] == ["208001", "208002", "208003", "299003"]
    for program in programs:
        assert sum(item["weight"] for item in program["items"]) == 100


def test_missing_seed_file_returns_empty_list(tmp_path):
    assert load_sample_programs(tmp_path / "none.csv") == []
