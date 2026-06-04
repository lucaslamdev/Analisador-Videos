from analisador_videos.util.class_labels import class_label_pt


def test_class_label_pt_known():
    assert class_label_pt("person") == "Pessoa"
    assert class_label_pt("car") == "Carro"


def test_class_label_pt_coco_extra():
    assert class_label_pt("dog") == "Cachorro"
    assert class_label_pt("cell phone") == "Celular"


def test_class_label_pt_unknown_passthrough():
    assert class_label_pt("custom_widget") == "Custom Widget"
