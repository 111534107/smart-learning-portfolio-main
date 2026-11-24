"""Print timing and token counts only; never print private OCR text."""
import argparse
import time

from app.services.ocr_pipeline import detect_transcript_panels, load_document_pages, _recognize_crop, parse_panel_words


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--engine", default="paddleocr")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--rec-model", default="PP-OCRv5_server_rec")
    parser.add_argument("--header-only", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--scale", type=float)
    parser.add_argument("--separate-only", action="store_true")
    parser.add_argument("--compare-baseline", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--compare-server", action="store_true")
    args = parser.parse_args()
    if args.analyze:
        from app.services.ocr_pipeline import analyze
        started = time.perf_counter()
        result = analyze("transcript", args.source, args.engine)
        courses = result["courses"]
        print(f"total_seconds={time.perf_counter()-started:.2f}", flush=True)
        print(f"course_count={len(courses)}", flush=True)
        print(f"complete_count={sum(row['credits'] is not None and row['score'] is not None for row in courses)}", flush=True)
        print(f"zero_credit_count={sum(row['credits'] == 0 for row in courses)}", flush=True)
        print(f"unknown_name_count={sum(row['course_name'] == '課名待確認' for row in courses)}", flush=True)
        return
    if args.batch_size or args.profile or args.rec_model != "PP-OCRv5_server_rec":
        from paddleocr import PaddleOCR
        from app.services import ocr_engines
        t0 = time.perf_counter()
        ocr_engines._paddle_engine = PaddleOCR(
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name=args.rec_model,
            device="cpu", cpu_threads=4, enable_mkldnn=False,
            text_det_limit_type="max", text_det_limit_side_len=2560,
            text_recognition_batch_size=args.batch_size or 1,
            use_doc_orientation_classify=False, use_doc_unwarping=False,
            use_textline_orientation=False, text_rec_score_thresh=0.0,
        )
        print(f"initialization_seconds={time.perf_counter()-t0:.2f}", flush=True)
        print(f"recognition_batch_size={ocr_engines._paddle_engine.paddlex_pipeline._pipeline.text_rec_model.batch_sampler.batch_size}", flush=True)
        if args.profile:
            pipeline = ocr_engines._paddle_engine.paddlex_pipeline._pipeline
            print(f"pipeline_type={type(pipeline).__name__}", flush=True)
            print(f"pipeline_inner_type={type(getattr(pipeline, '_pipeline', None)).__name__}", flush=True)
            for name in ("text_det_model", "text_rec_model"):
                model = getattr(pipeline, name)
                def timed_model(*a, _model=model, _name=name, **kw):
                    start = time.perf_counter()
                    results = list(_model(*a, **kw))
                    print(f"{_name}_seconds={time.perf_counter()-start:.2f}, count={len(results)}", flush=True)
                    return iter(results)
                setattr(pipeline, name, timed_model)
    started = time.perf_counter()
    image = next(load_document_pages(args.source))
    panels = detect_transcript_panels(image)
    if not panels:
        raise SystemExit("No matching transcript panel")
    panel = panels[0]
    left, _, right, _ = panel["bbox"]
    top, bottom = panel["body"]
    boxes = [("header", [left, max(0, top - image.height * .1), right, top])]
    boxes += [(f"column_{i}", [left + a + 2, top, left + b - 2, bottom])
              for i, (a, b) in enumerate(zip(panel["columns"], panel["columns"][1:]))]
    if args.header_only:
        boxes = boxes[:1]
    if args.scale:
        from PIL import Image
        from app.services import ocr_pipeline
        original_recognize = ocr_pipeline._recognize_crop
        def resized_recognize(source, box, engine):
            crop = source.crop(tuple(int(v) for v in box)).convert("RGB")
            crop = crop.resize((round(crop.width*args.scale), round(crop.height*args.scale)), Image.Resampling.LANCZOS)
            from app.services.ocr_engines import recognize
            words = recognize(crop, engine)
            for word in words:
                word["bbox"] = [word["bbox"][0]/args.scale+box[0], word["bbox"][1]/args.scale+box[1], word["bbox"][2]/args.scale+box[0], word["bbox"][3]/args.scale+box[1]]
            return words
        recognize_crop = resized_recognize
    else:
        recognize_crop = _recognize_crop
    print(f"geometry_seconds={time.perf_counter() - started:.2f}", flush=True)
    column_words = []
    for label, box in boxes:
        t0 = time.perf_counter()
        tokens = recognize_crop(image, box, args.engine)
        print(f"{label}: seconds={time.perf_counter()-t0:.2f}, tokens={len(tokens)}", flush=True)
        if label != "header":
            column_words.extend(tokens)
    if args.header_only:
        return
    if args.compare_baseline:
        baseline_words = []
        for label, box in boxes[1:]:
            t0 = time.perf_counter()
            words = _recognize_crop(image, box, args.engine)
            baseline_words.extend(words)
            print(f"baseline_{label}: seconds={time.perf_counter()-t0:.2f}, tokens={len(words)}", flush=True)
        def parse(words):
            relative = [{**w, "bbox": [w["bbox"][0]-left, w["bbox"][1],
                                       w["bbox"][2]-left, w["bbox"][3]]} for w in words]
            return parse_panel_words(relative, (right-left, image.height), 1,
                                     body=panel["body"], columns=panel["columns"])
        fast, baseline = parse(column_words), parse(baseline_words)
        print(f"fast_rows={len(fast)}, baseline_rows={len(baseline)}", flush=True)
        for field in ("course_name", "credits", "score", "semester"):
            matched = 0
            for ref in baseline:
                near = [row for row in fast if row["semester"] == ref["semester"]
                        and abs(row["source_bbox"][1]-ref["source_bbox"][1]) <= 8]
                if any(row[field] == ref[field] for row in near):
                    matched += 1
            print(f"{field}_matching={matched}/{len(baseline)}", flush=True)
        for label, rows in (("fast", fast), ("baseline", baseline)):
            print(f"{label}_complete={sum(row['credits'] is not None and row['score'] is not None for row in rows)}", flush=True)
            print(f"{label}_zero_credit={sum(row['credits'] == 0 for row in rows)}", flush=True)
            print(f"{label}_unknown_name={sum(row['course_name'] == '課名待確認' for row in rows)}", flush=True)
        print(f"total_seconds={time.perf_counter()-started:.2f}", flush=True)
        return
    if args.separate_only or args.compare_server:
        relative = [{**w, "bbox": [w["bbox"][0]-left, w["bbox"][1],
                                   w["bbox"][2]-left, w["bbox"][3]]} for w in column_words]
        rows = parse_panel_words(relative, (right-left, image.height), 1,
                                 body=panel["body"], columns=panel["columns"])
        print(f"rows={len(rows)}, complete={sum(r['credits'] is not None and r['score'] is not None for r in rows)}, zero_credit={sum(r['credits'] == 0 for r in rows)}, unknown_name={sum(r['course_name'] == '課名待確認' for r in rows)}", flush=True)
        if args.compare_server:
            from paddleocr import PaddleOCR
            from app.services import ocr_engines
            ocr_engines._paddle_engine = PaddleOCR(
                text_detection_model_name="PP-OCRv5_server_det",
                text_recognition_model_name="PP-OCRv5_server_rec",
                device="cpu", cpu_threads=4, enable_mkldnn=False,
                text_det_limit_type="max", text_det_limit_side_len=2560,
                text_recognition_batch_size=args.batch_size or 16,
                use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, text_rec_score_thresh=0.0,
            )
            server_words = []
            for label, box in boxes[1:]:
                t0 = time.perf_counter()
                server_words.extend(recognize_crop(image, box, args.engine))
                print(f"server_{label}_seconds={time.perf_counter()-t0:.2f}", flush=True)
            relative_server = [{**w, "bbox": [w["bbox"][0]-left, w["bbox"][1],
                                                 w["bbox"][2]-left, w["bbox"][3]]} for w in server_words]
            server_rows = parse_panel_words(relative_server, (right-left, image.height), 1,
                                            body=panel["body"], columns=panel["columns"])
            print(f"server_rows={len(server_rows)}, server_complete={sum(r['credits'] is not None and r['score'] is not None for r in server_rows)}", flush=True)
            for field in ("course_name", "credits", "score", "semester"):
                matching = 0
                for ref in server_rows:
                    near = [row for row in rows if row["semester"] == ref["semester"]
                            and abs(row["source_bbox"][1]-ref["source_bbox"][1]) <= 8]
                    if any(row[field] == ref[field] for row in near):
                        matching += 1
                print(f"mobile_{field}_matching={matching}/{len(server_rows)}", flush=True)
        print(f"separate_seconds={time.perf_counter()-started:.2f}", flush=True)
        return
    t0 = time.perf_counter()
    merged_words = recognize_crop(image, [left, top, right, bottom], args.engine)
    print(f"merged: seconds={time.perf_counter()-t0:.2f}, tokens={len(merged_words)}", flush=True)
    def rows(words):
        relative = [{**w, "bbox": [w["bbox"][0]-left, w["bbox"][1],
                                   w["bbox"][2]-left, w["bbox"][3]]} for w in words]
        return parse_panel_words(relative, (right-left, image.height), 1,
                                 body=panel["body"], columns=panel["columns"])
    separate, combined = rows(column_words), rows(merged_words)
    print(f"separate_rows={len(separate)}, separate_complete={sum(r['credits'] is not None and r['score'] is not None for r in separate)}", flush=True)
    print(f"merged_rows={len(combined)}, merged_complete={sum(r['credits'] is not None and r['score'] is not None for r in combined)}", flush=True)
    # Compare by physical row location, not OCR text content.
    matching = 0
    for reference in separate:
        close = [r for r in combined if r['semester'] == reference['semester']
                 and abs(r['source_bbox'][1] - reference['source_bbox'][1]) <= 7]
        if close and any(all(r[field] == reference[field]
                             for field in ('course_name', 'credits', 'score')) for r in close):
            matching += 1
    print(f"matching_fields_by_row={matching}/{len(separate)}", flush=True)
    print(f"total_seconds={time.perf_counter()-started:.2f}")


if __name__ == "__main__":
    main()
