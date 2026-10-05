"""Fetch GOV.UK text snapshots with provenance; external sample PDFs remain links."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import urllib.request

from visa_agent.rules import SOURCES
from visa_agent.store import write_json

ROOT = Path(__file__).resolve().parents[1]


class MainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.skip = False
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.active = True
        if tag in {"script", "style"}:
            self.skip = True
    def handle_endtag(self, tag):
        if tag == "main":
            self.active = False
        if tag in {"script", "style"}:
            self.skip = False
    def handle_data(self, data):
        if self.active and not self.skip and data.strip():
            self.parts.append(data.strip())


def main():
    records = []
    for key, url in SOURCES.items():
        if not url.startswith("https://www.gov.uk/"):
            continue
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                raw = response.read()
            parser = MainText()
            parser.feed(raw.decode("utf-8"))
            text = "\n".join(parser.parts)
            if len(text) < 200:
                raise ValueError("No substantive GOV.UK main content extracted")
            path = ROOT / "datasets" / "reference" / f"{key}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            preface = f"Source: {url}\nCrown copyright; Open Government Licence v3.0, excluding third-party material.\n\n"
            path.write_text(preface + text, encoding="utf-8")
            records.append({"id": key, "url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "path": str(path.relative_to(ROOT)), "html_sha256": hashlib.sha256(raw).hexdigest(),
                            "text_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "status": "fetched",
                            "licence": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"})
        except Exception as exc:
            records.append({"id": key, "url": url, "status": "failed", "error": str(exc)})
        print(key, records[-1]["status"], flush=True)
    for id, url, purpose in [
        ("sussex", "https://student.sussex.ac.uk/international/visas/applying/proof", "Bank statement, deposit, bank letter and parental consent examples"),
        ("swansea", "https://www.swansea.ac.uk/media/Guide-to-documents-for-Student-visa-application.pdf", "CAS layout reference; policy may be older than current rules"),
        ("passport", "https://www.gov.uk/government/publications/basic-passport-checks", "Specimen layout/OCR reference, not a foreign applicant's passport"),
    ]:
        records.append({"id": id, "url": url, "purpose": purpose, "status": "link_only",
                        "licence": "Redistribution not established; not bundled", "sha256": None})
    write_json(ROOT / "datasets" / "sources.json", records)


if __name__ == "__main__":
    main()
