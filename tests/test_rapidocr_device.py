"""RapidOCR 可選擇用 CPU 或 GPU（Windows DirectML），預設 CPU，可隨時切回。"""
import pytest

from app import create_app
from app.services.document_analysis_service import RapidOcrEngine


def test_rapidocr_engine_defaults_to_cpu():
    params = RapidOcrEngine().build_params()

    assert params["EngineConfig.onnxruntime.use_dml"] is False
    assert "EngineConfig.onnxruntime.dml_ep_cfg" not in params


def test_rapidocr_engine_directml_selects_graphics_device():
    params = RapidOcrEngine(device="dml", dml_device_id=1).build_params()

    assert params["EngineConfig.onnxruntime.use_dml"] is True
    assert params["EngineConfig.onnxruntime.dml_ep_cfg"] == {"device_id": 1}


def test_rapidocr_engine_rejects_unknown_device():
    with pytest.raises(ValueError):
        RapidOcrEngine(device="cuda")


def test_configured_rapidocr_settings_follow_app_config(tmp_path):
    from app.services.ocr_engines import configured_rapidocr_settings

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "OCR_DEVICE": "dml", "OCR_DML_DEVICE_ID": 1})
    with app.app_context():
        assert configured_rapidocr_settings() == ("server", "dml", 1)
    assert configured_rapidocr_settings() == ("server", "cpu", 0)


def test_create_app_passes_device_to_offline_engine(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "DOCUMENT_OCR_ENGINE": "rapidocr",
                      "OCR_DEVICE": "dml", "OCR_DML_DEVICE_ID": 1})

    engine = app.config["OCR_ENGINE"]
    assert (engine.device, engine.dml_device_id) == ("dml", 1)


def test_directml_provider_options_become_plain_dict():
    # rapidocr 3.10 直接把 OmegaConf 設定物件交給 onnxruntime，被拒絕後會悄悄退回 CPU
    from omegaconf import OmegaConf

    from app.services.document_analysis_service import _plain_dict_provider_options

    wrapped = _plain_dict_provider_options(lambda self: OmegaConf.create({"device_id": 1}))
    options = wrapped(object())

    assert type(options) is dict
    assert options == {"device_id": 1}
