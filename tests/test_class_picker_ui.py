import json
import re

from fastapi.testclient import TestClient

from analisador_videos.main import app
from analisador_videos.util.detection_classes import PEOPLE_VEHICLE_DETECTION_CLASSES


def test_home_includes_class_picker_preset_data():
    client = TestClient(app)
    html = client.get("/").text

    assert html.count('data-class-pick="people-vehicles"') >= 1
    assert 'data-class-pick="all"' in html
    assert 'data-class-pick="none"' in html
    assert "/static/detection-classes.js?v=5" in html

    json_blocks = re.findall(
        r'data-people-vehicle-classes-json>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert json_blocks, "bloco JSON do preset ausente"
    for raw in json_blocks:
        classes = json.loads(raw.strip())
        assert set(classes) == set(PEOPLE_VEHICLE_DETECTION_CLASSES)

    attr_matches = re.findall(
        r"data-people-vehicle-classes='([^']*)'",
        html,
    )
    assert attr_matches
    for raw in attr_matches:
        assert set(json.loads(raw)) == set(PEOPLE_VEHICLE_DETECTION_CLASSES)
