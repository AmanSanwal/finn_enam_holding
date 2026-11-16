"""web/app.html is the page body (the artifact host adds its own document skeleton);
web/index.html wraps it in a full document for any static host or the FastAPI server."""
from pathlib import Path

web = Path(__file__).resolve().parents[1] / "web"
body = (web / "app.html").read_text()
(web / "index.html").write_text(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<meta name="theme-color" content="#0f1724">\n</head>\n<body>\n' + body + "</body>\n</html>\n")
print("wrote web/index.html")
