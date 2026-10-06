"""One real native-PDF compatibility request, charged to the existing bounded experiment."""

import base64
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from visa_agent.agent import LiveBudget
from visa_agent.store import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["openai", "deepseek"], default="openai")
    args = parser.parse_args()
    out = Path("output/customer-service-v1")
    receipt = out / ("native-pdf-probe.json" if args.format == "openai" else "native-pdf-probe-flat.json")
    if receipt.exists():
        raise ValueError("Probe already recorded; do not overwrite it")
    file = Path("external-materials/public-samples/06-deposit-certificate-Warwick.pdf")
    model = os.getenv("VISA_MODEL", "deepseek-flash")
    key = os.getenv("VISA_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    budget = LiveBudget(out / "live-budget.sqlite3", 36)
    payload = {"model": model, "thinking": {"type": "disabled"}, "max_tokens": 300,
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": "Read only visible content in this public redacted sample. Is a complete holder name readable? Do not reconstruct hidden text. State what you can actually see."},
                   {"type": "file", "file": {"filename": file.name,
                    "file_data": "data:application/pdf;base64," + base64.b64encode(file.read_bytes()).decode()}}]}]}
    if args.format == "deepseek":
        block = payload["messages"][0]["content"][1]
        payload["messages"][0]["content"][1] = {"type": "file", **block["file"]}
    req = urllib.request.Request(os.getenv("VISA_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    record = {"model": model, "input": str(file), "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
              "transport": "native_pdf_file_data", "format": args.format, "requests": 1}
    started = time.monotonic()
    budget.reserve(model)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = json.load(response)
            record.update(status=response.status, response_model=body.get("model"), usage=body.get("usage"),
                          messages=[{k: v for k, v in choice["message"].items() if k in {"role", "content", "tool_calls"}}
                                    for choice in body.get("choices", [])])
    except urllib.error.HTTPError as exc:
        record.update(status=exc.code, error=exc.read().decode()[:2000])
    except Exception as exc:
        record.update(error=type(exc).__name__ + ": " + str(exc))
    record.update(seconds=round(time.monotonic() - started, 3), ledger_requests=budget.count())
    write_json(receipt, record)
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
