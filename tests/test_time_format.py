from analisador_videos.util.time_format import format_hms


def test_format_hms_zero():
    assert format_hms(0) == "00:00:00"


def test_format_hms_one_hour():
    assert format_hms(3600) == "01:00:00"


def test_format_hms_example():
    assert format_hms(2834) == "00:47:14"
