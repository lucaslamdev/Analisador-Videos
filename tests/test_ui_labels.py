from analisador_videos.util.ui_labels import stage_label_pt, status_label_pt


def test_status_label_pt():
    assert status_label_pt("running") == "Em execução"
    assert status_label_pt("done") == "Concluído"


def test_stage_label_pt():
    assert stage_label_pt("detect") == "Detecção"
