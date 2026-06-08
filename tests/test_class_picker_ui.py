import json
import re

from fastapi.testclient import TestClient

from analisador_videos.main import app
from analisador_videos.util.detection_classes import PEOPLE_VEHICLE_DETECTION_CLASSES


def test_home_includes_class_picker_preset_data():
    client = TestClient(app)
    html = client.get("/").text

    assert html.count("data-class-pick-people-vehicles") >= 1
    assert "/static/detection-classes.js" in html

    matches = re.findall(
        r"data-people-vehicle-classes='([^']*)'",
        html,
    )
    assert matches, "atributo data-people-vehicle-classes ausente"
    for raw in matches:
        classes = json.loads(raw)
        assert set(classes) == set(PEOPLE_VEHICLE_DETECTION_CLASSES)
