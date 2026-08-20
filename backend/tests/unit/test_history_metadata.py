from app.api.v1.resources import _birth_date_from_basic, _city_from_basic


def test_history_uses_birth_datetime_not_record_created_at() -> None:
    basic = {
        "birth_datetime_local": "1995-12-22T08:30:00",
        "birthplace": {"province": "安徽省", "city": "合肥市"},
    }

    assert _birth_date_from_basic(basic) == "1995-12-22"
    assert _city_from_basic(basic) == "合肥市"


def test_history_supports_legacy_basic_date_fields() -> None:
    assert _birth_date_from_basic({"solar_datetime": "1988-06-09 12:00:00"}) == "1988-06-09"
    assert _birth_date_from_basic({"civil_time": "2001-01-02T03:04:05"}) == "2001-01-02"
    assert _birth_date_from_basic({}) is None


def test_history_city_falls_back_to_province_only_when_city_missing() -> None:
    assert _city_from_basic({"birthplace": {"province": "浙江省"}}) == "浙江省"
    assert _city_from_basic({}) is None
