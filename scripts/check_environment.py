"""Real plain-reply/structured-tool probes, charged to the persistent usage ledger."""
import asyncio
from dataclasses import asdict
import importlib.metadata
import os
from pathlib import Path
import uuid

import httpx2 as httpx
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from visa_agent.agent import LiveBudget
from visa_agent.store import write_json
from visa_agent.config import load_environment


class Receipt(BaseModel):
    code: str


async def main():
    load_environment()
    model_name = os.getenv("VISA_MODEL", "deepseek-flash")
    key = os.getenv("VISA_API_KEY") or os.environ["DEEPSEEK_API_KEY"]
    budget = LiveBudget(Path(os.getenv("VISA_DATA_DIR", "data")) / "live-budget.sqlite3")
    before = budget.count()
    async def count(request):
        if request.method == "POST":
            budget.reserve(model_name)
    report = {"model": model_name, "packages": {p: importlib.metadata.version(p) for p in
                                               ("pydantic-ai-slim", "openai", "rapidocr", "pypdf", "pypdfium2")}}
    async with httpx.AsyncClient(event_hooks={"request": [count]}, timeout=90) as http:
        sdk = AsyncOpenAI(api_key=key, base_url=os.getenv("VISA_BASE_URL", "https://api.deepseek.com"),
                          max_retries=0, http_client=http)
        model = OpenAIChatModel(model_name, provider=OpenAIProvider(openai_client=sdk))
        settings = {"extra_body": {"thinking": {"type": "disabled"}}} if model_name.startswith("deepseek") else {}
        plain = await Agent(model, model_settings=settings).run("Reply with exactly: READY", usage_limits=UsageLimits(request_limit=1))
        report["plain_reply"] = {"passed": plain.output.strip() == "READY", "output": plain.output,
                                 "usage": asdict(plain.usage)}
        write_json(Path("output/compatibility.json"), report)
        code = uuid.uuid4().hex[:12]
        calls = []
        agent = Agent(model, output_type=Receipt, model_settings=settings,
                      instructions="Call get_probe_code exactly once, then return its code.")
        @agent.tool_plain
        def get_probe_code() -> str:
            """Return the locally generated probe code."""
            calls.append("get_probe_code")
            return code
        result = await agent.run("Run the compatibility check.", usage_limits=UsageLimits(request_limit=3))
        report["structured_tool_call"] = {"passed": result.output.code == code and len(calls) == 1,
                                           "tool_calls": calls, "output": result.output.model_dump(),
                                           "usage": asdict(result.usage)}
    report["http_requests"] = budget.count() - before
    report["passed"] = report["plain_reply"]["passed"] and report["structured_tool_call"]["passed"]
    write_json(Path("output/compatibility.json"), report)
    print(report)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
