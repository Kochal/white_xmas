from whitexmas.config import Config


def test_windows_follow_contract_order(cfg: Config):
    ids = [w.id for w in cfg.windows()]
    assert ids[:4] == ["1950_2025", "1961_1990", "1996_2025", "2016_2025"]
    assert ids[-1] == "1956_1965"
    assert "1996_2005" in ids
    assert [w.kind for w in cfg.windows()][:3] == ["full", "normal", "normal"]


def test_default_definition(cfg: Config):
    assert cfg.default_definition == "christmas_day"
    assert cfg.definition_ids == ["christmas_day", "all_three_days", "any_day"]


def test_change_pair_survives_unquoted_yaml():
    import yaml

    raw = yaml.safe_load("windows:\n  change:\n    from: 1961_1990\n    to: 1996_2025\n")
    assert Config(raw).change_pair == ("1961_1990", "1996_2025")


def test_shipped_config_change_pair(cfg: Config):
    assert cfg.change_pair == ("1961_1990", "1996_2025")
    assert set(cfg.change_pair) <= {w.id for w in cfg.windows()}
