from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from app.config import Settings
from app.models import Recommendation


def enrich_reasons(rows: list[Recommendation], settings: Settings) -> list[Recommendation]:
    providers = _provider_order(settings)
    if not providers or settings.ai_max_rows <= 0:
        return rows

    target_rows = rows[: settings.ai_max_rows]
    generated = {}
    for provider in providers:
        try:
            generated = _generate_reason_map(target_rows, settings, provider)
        except Exception:
            continue
        if generated:
            break
    if not generated:
        return rows

    enriched = []
    for row in rows:
        reason = generated.get(row.id)
        if reason and isinstance(reason, str) and len(reason.strip()) >= 20:
            enriched.append(row.model_copy(update={"reason": _clean_reason(reason)}))
        else:
            enriched.append(row)
    return enriched


def _generate_reason_map(
    rows: list[Recommendation], settings: Settings, provider: str
) -> dict[str, str]:
    facts = [
        {
            "id": row.id,
            "sku": row.sku,
            "product_name": row.product_name,
            "supplier": row.supplier,
            "stock_qty": row.stock_qty,
            "in_transit_qty": row.in_transit_qty,
            "recommended_order_qty": row.recommended_order_qty,
            "avg_daily_demand": row.avg_daily_demand,
            "coverage_days": row.coverage_days,
            "lead_time_days": row.lead_time_days,
            "moq": row.moq,
            "unit": row.unit,
            "urgency": row.urgency,
        }
        for row in rows
    ]
    system_prompt = (
        "Ты пишешь короткие объяснения закупочных рекомендаций на русском. "
        "Используй только переданные факты, не придумывай цены, клиентов или поставки. "
        "Верни только JSON object, где ключ - id строки, значение - 1-2 конкретных предложения."
    )
    user_prompt = json.dumps({"rows": facts}, ensure_ascii=False)
    if provider == "openai":
        text = _call_openai(system_prompt, user_prompt, settings)
    else:
        text = _call_nvidia(system_prompt, user_prompt, settings)
    parsed = _parse_json_object(text)
    return {str(key): str(value) for key, value in parsed.items()}


def _call_openai(system_prompt: str, user_prompt: str, settings: Settings) -> str:
    payload = {
        "model": settings.openai_model,
        "instructions": system_prompt,
        "input": user_prompt,
        "max_output_tokens": 900,
    }
    data = _post_json(
        "https://api.openai.com/v1/responses",
        payload,
        {"Authorization": f"Bearer {settings.openai_api_key}"},
    )
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _call_nvidia(system_prompt: str, user_prompt: str, settings: Settings) -> str:
    payload = {
        "model": settings.nvidia_model,
        "temperature": 0.2,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = _post_json(
        f"{settings.nvidia_base_url.rstrip('/')}/chat/completions",
        payload,
        {"Authorization": f"Bearer {settings.nvidia_api_key}"},
    )
    return data["choices"][0]["message"]["content"]


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI provider HTTP {error.code}: {detail[:400]}") from error


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {}
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}


def _clean_reason(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _provider_order(settings: Settings) -> list[str]:
    if settings.ai_provider == "openai":
        return ["openai"] if settings.openai_api_key else []
    if settings.ai_provider == "nvidia":
        return ["nvidia"] if settings.nvidia_api_key else []
    if settings.ai_provider == "auto":
        providers = []
        if settings.openai_api_key:
            providers.append("openai")
        if settings.nvidia_api_key:
            providers.append("nvidia")
        return providers
    return []
