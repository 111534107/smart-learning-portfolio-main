"""保留既有資料的 5205 本機整合預覽，使用離線 RapidOCR。"""

import argparse

from run_demo import DEMO_ACCOUNTS, PROJECT_ROOT, create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="instance 內既有 SQLite 檔名")
    parser.add_argument("--uploads", required=True, help="instance 內既有上傳目錄名")
    parser.add_argument("--port", type=int, default=5205)
    args = parser.parse_args()
    root = (PROJECT_ROOT / "instance").resolve()

    database = (root / args.database).resolve()
    uploads = (root / args.uploads).resolve()
    if database.parent != root or database.suffix != ".db" or not database.is_file():
        parser.error("請指定 instance 內既有的 .db 檔")
    if uploads.parent != root or not uploads.is_dir():
        parser.error("請指定 instance 內既有的上傳目錄")

    app = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database.as_posix()}",
        "UPLOAD_FOLDER": str(uploads),
        "DEMO_ACCOUNTS": DEMO_ACCOUNTS,
        "LOCAL_DEMO_MODE": True,
        "SESSION_COOKIE_NAME": f"presentation_{args.port}",
        "STORAGE_BACKEND": "local",
        "DOCUMENT_ANALYSIS_PROVIDER": "rapidocr",
        "REQUIRE_REAL_DOCUMENT_OCR": True,
        "TEMPLATES_AUTO_RELOAD": True,
    })
    print("OCR：RapidOCR（離線）", flush=True)
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
