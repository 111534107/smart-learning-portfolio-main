"""Adapter contract tests: no OCR binaries, network access, or model downloads."""

import importlib.util
import json
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image


@pytest.fixture
def engines(monkeypatch):
    # Load only this standalone module; do not require a Flask application.
    path = Path(__file__).resolve().parents[1] / "app/services/ocr_engines.py"
    assert path.exists(), "The standalone OCR adapter has not been implemented"
    for package in ("paddleocr", "paddle", "pytesseract"):
        monkeypatch.setitem(sys.modules, package, None)
    spec = importlib.util.spec_from_file_location("ocr_engines_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample_image():
    return Image.new("RGB", (120, 80), (10, 20, 30))


def tesseract_data(texts, scores):
    n = len(texts)
    return {
        "level": [5] * n, "page_num": [1] * n, "block_num": [1] * n,
        "par_num": [1] * n, "line_num": [1] * n, "word_num": list(range(1, n + 1)),
        "left": [7] * n, "top": [11] * n, "width": [23] * n,
        "height": [9] * n, "conf": scores, "text": texts,
    }


def install_tesseract(monkeypatch, image_to_data):
    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(
        Output=SimpleNamespace(DICT="dict"), image_to_data=image_to_data,
    ))


def paddle_result(np):
    # Real v3 field shapes, including numpy arrays and unused metadata.
    polygons = np.array([
        [[9, 10], [41, 8], [43, 22], [11, 24]],
        [[50, 30], [70, 30], [70, 40], [50, 40]],
    ], dtype=np.int16)
    return {
        "input_path": None, "page_index": None,
        "model_settings": {"use_doc_preprocessor": False, "use_textline_orientation": False},
        "doc_preprocessor_res": {"output_img": np.zeros((80, 120, 3), dtype=np.uint8)},
        "dt_polys": polygons, "text_det_params": {"thresh": 0.3, "box_thresh": 0.6},
        "text_type": "general", "textline_orientation_angles": np.array([-1, -1]),
        "text_rec_score_thresh": 0.0, "rec_texts": ["繁體中文 English", "待確認"],
        "rec_scores": np.array([0.98, 0.0]), "rec_polys": polygons,
        "rec_boxes": np.array([[9, 8, 43, 24], [50, 30, 70, 40]], dtype=np.int16),
    }


def install_paddle(monkeypatch, result, observations=None):
    observations = observations if observations is not None else {}

    class PaddleOCR:
        def __init__(self, **kwargs):
            observations.setdefault("constructors", []).append(kwargs)

        def predict(self, input, **kwargs):
            observations.setdefault("inputs", []).append(input)
            observations.setdefault("predictions", []).append(kwargs)
            yield result

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=PaddleOCR))
    return observations


def test_import_is_lazy_without_any_ocr_package(engines):
    assert callable(engines.recognize)


def test_default_tesseract_keeps_low_unknown_and_zero_confidence(engines, monkeypatch, sample_image):
    def image_to_data(image, **kwargs):
        assert image.size == (120, 80)
        assert kwargs["lang"] == "chi_tra+eng"
        assert "--psm 6" in kwargs["config"]
        assert kwargs["output_type"] == "dict"
        assert 0 < kwargs["timeout"] <= 120
        return tesseract_data(["", "  ", "國文", "English", "數學", "待確認"],
                              [-1, -1, "96.125", "4.0", "0", "-1"])

    install_tesseract(monkeypatch, image_to_data)
    assert engines.recognize(sample_image) == [
        {"text": "國文", "bbox": [7.0, 11.0, 30.0, 20.0], "confidence": 0.96125},
        {"text": "English", "bbox": [7.0, 11.0, 30.0, 20.0], "confidence": 0.04},
        {"text": "數學", "bbox": [7.0, 11.0, 30.0, 20.0], "confidence": 0.0},
        {"text": "待確認", "bbox": [7.0, 11.0, 30.0, 20.0], "confidence": None},
    ]


@pytest.mark.parametrize("score, expected", [(None, None), ("bad", None), ("nan", None),
                                                ("inf", None), ("120", 1.0)])
def test_tesseract_normalizes_unusable_or_out_of_range_scores(
    engines, monkeypatch, sample_image, score, expected,
):
    install_tesseract(monkeypatch, lambda *a, **k: tesseract_data(["字"], [score]))
    assert engines.recognize(sample_image)[0]["confidence"] == expected


@pytest.mark.parametrize("engine, package", [("tesseract", "pytesseract"), ("paddleocr", "paddleocr")])
def test_missing_packages_are_actionable_without_fallback(engines, sample_image, engine, package):
    with pytest.raises(RuntimeError) as error:
        engines.recognize(sample_image, engine=engine)
    assert package in str(error.value)
    assert "requirements-ocr.txt" in str(error.value)


def test_unknown_engine_fails_without_echoing_untrusted_value(engines, sample_image):
    with pytest.raises(ValueError) as error:
        engines.recognize(sample_image, engine="private student record")
    assert "private student record" not in str(error.value)


def test_tesseract_failures_are_sanitized(engines, monkeypatch, sample_image):
    def failure(*args, **kwargs):
        raise RuntimeError("private student record C:/private/file.png")

    install_tesseract(monkeypatch, failure)
    with pytest.raises(RuntimeError) as error:
        engines.recognize(sample_image)
    rendered = "".join(traceback.format_exception(error.value))
    assert "private student record" not in rendered
    assert "chi_tra" in str(error.value)
    assert "逾時" in str(error.value)


@pytest.mark.parametrize("shape", ["dict", "wrapped", "json_dict", "json_string"])
def test_paddle_v3_shapes_preserve_polygon_coordinates_and_low_scores(
    engines, monkeypatch, sample_image, shape,
):
    np = pytest.importorskip("numpy")
    result = paddle_result(np)
    if shape == "wrapped":
        result = {"res": result}
    elif shape == "json_dict":
        result = SimpleNamespace(json={"res": result})
    elif shape == "json_string":
        result = SimpleNamespace(json=json.dumps({"res": result}, default=lambda v: v.tolist()))
    observations = install_paddle(monkeypatch, result)
    before = sample_image.tobytes()
    tokens = engines.recognize(sample_image, engine="paddleocr")
    assert tokens == [
        {"text": "繁體中文 English", "bbox": [9.0, 8.0, 43.0, 24.0], "confidence": 0.98},
        {"text": "待確認", "bbox": [50.0, 30.0, 70.0, 40.0], "confidence": 0.0},
    ]
    assert all(type(v) is float for token in tokens for v in token["bbox"])
    image = observations["inputs"][0]
    assert image.shape == (80, 120, 3)
    assert image.dtype == np.uint8
    assert image.flags.c_contiguous
    assert image[0, 0].tolist() == [30, 20, 10]
    assert sample_image.tobytes() == before
    options = observations["constructors"][0]
    assert options["ocr_version"] == "PP-OCRv5"
    assert options["text_detection_model_name"] == "PP-OCRv5_server_det"
    assert options["text_recognition_model_name"] == "PP-OCRv5_server_rec"
    assert options["device"] == "cpu"
    assert options["text_det_limit_type"] == "max"
    assert options["text_det_limit_side_len"] == 2560
    assert options["cpu_threads"] == 4
    assert options["enable_mkldnn"] is False
    assert options["text_recognition_batch_size"] == 16
    for key in ("use_doc_orientation_classify", "use_doc_unwarping", "use_textline_orientation"):
        assert options[key] is False
    assert options["text_rec_score_thresh"] == 0.0


def test_paddle_caches_one_model_and_accepts_grayscale(engines, monkeypatch):
    np = pytest.importorskip("numpy")
    observations = install_paddle(monkeypatch, paddle_result(np))
    for _ in range(2):
        engines.recognize(Image.new("L", (120, 80), 71), engine="paddle")
    assert len(observations["constructors"]) == 1
    assert observations["inputs"][0][0, 0].tolist() == [71, 71, 71]


@pytest.mark.parametrize("scores", [None, [None, float("nan")]])
def test_paddle_missing_scores_retain_regions(engines, monkeypatch, sample_image, scores):
    np = pytest.importorskip("numpy")
    result = paddle_result(np)
    result["rec_scores"] = scores
    install_paddle(monkeypatch, result)
    tokens = engines.recognize(sample_image, "paddleocr")
    assert len(tokens) == 2
    assert [t["confidence"] for t in tokens] == [None, None]


def test_paddle_empty_page(engines, monkeypatch, sample_image):
    np = pytest.importorskip("numpy")
    result = paddle_result(np)
    result.update(rec_texts=[], rec_scores=np.array([]), rec_polys=np.empty((0, 4, 2)))
    install_paddle(monkeypatch, result)
    assert engines.recognize(sample_image, "paddleocr") == []


@pytest.mark.parametrize("bad", ["mismatch", "nonfinite", "error"])
def test_paddle_bad_results_raise_instead_of_silently_dropping_tokens(
    engines, monkeypatch, sample_image, bad,
):
    np = pytest.importorskip("numpy")
    result = paddle_result(np)
    if bad == "mismatch":
        result["rec_polys"] = result["rec_polys"][:1]
    elif bad == "nonfinite":
        result["rec_polys"] = result["rec_polys"].astype(float)
        result["rec_polys"][0, 0, 0] = np.nan
    else:
        result = {"error": "private student record"}
    install_paddle(monkeypatch, result)
    with pytest.raises(RuntimeError) as error:
        engines.recognize(sample_image, "paddleocr")
    assert "private student record" not in str(error.value)


@pytest.mark.parametrize("stage", ["initialize", "iterate"])
def test_paddle_failures_are_sanitized_and_not_cached_as_success(
    engines, monkeypatch, sample_image, stage,
):
    pytest.importorskip("numpy")

    class BrokenOCR:
        def __init__(self, **kwargs):
            if stage == "initialize":
                raise OSError("private student record")

        def predict(self, *args, **kwargs):
            yield {"rec_texts": [], "rec_scores": [], "rec_polys": []}
            raise RuntimeError("private student record")

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=BrokenOCR))
    with pytest.raises(RuntimeError) as error:
        engines.recognize(sample_image, "paddleocr")
    assert "private student record" not in "".join(traceback.format_exception(error.value))
    assert "模型" in str(error.value)
    if stage == "initialize":
        install_paddle(monkeypatch, {"rec_texts": [], "rec_scores": [], "rec_polys": []})
        assert engines.recognize(sample_image, "paddleocr") == []


def test_paddle_lock_covers_lazy_prediction_iteration(engines, monkeypatch, sample_image):
    pytest.importorskip("numpy")
    entered = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    concurrent = threading.Event()
    active = threading.Lock()
    constructors = []

    class PaddleOCR:
        def __init__(self, **kwargs):
            constructors.append(self)

        def predict(self, *args, **kwargs):
            acquired = active.acquire(blocking=False)
            if not acquired:
                concurrent.set()
            try:
                entered.set()
                assert release.wait(5)
                yield {"rec_texts": [], "rec_scores": [], "rec_polys": []}
            finally:
                if acquired:
                    active.release()

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=PaddleOCR))

    def second_call():
        second_started.set()
        return engines.recognize(sample_image, "paddleocr")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(engines.recognize, sample_image, "paddleocr")
        try:
            assert entered.wait(5)
            second = pool.submit(second_call)
            assert second_started.wait(5)
            assert not concurrent.wait(0.1)
        finally:
            release.set()
        assert first.result(timeout=5) == second.result(timeout=5) == []
    assert len(constructors) == 1
