import os
import json
from openai import AsyncOpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def _get_client():
    return AsyncOpenAI(api_key=OPENAI_API_KEY)


def _clean_base64(image_base64: str) -> str:
    if "," in image_base64:
        return image_base64.split(",")[1]
    return image_base64


def _parse_json_response(text: str) -> dict:
    json_str = text.strip()
    if json_str.startswith("```"):
        lines = json_str.split("\n")
        json_str = "\n".join(lines[1:-1]) if len(lines) > 2 else json_str[3:-3]
        json_str = json_str.strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(json_str[start:end])
        raise ValueError(f"JSON parse hatası: {json_str[:200]}")


async def chat_with_vision(
    system_message: str,
    user_text: str,
    images_base64: list[str],
    model: str = "gpt-4o",
) -> str:
    client = _get_client()

    content = [{"type": "text", "text": user_text}]
    for img_b64 in images_base64:
        clean = _clean_base64(img_b64)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{clean}"}
        })

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": content},
        ],
        max_tokens=4096,
    )

    return response.choices[0].message.content


async def chat_with_vision_json(
    system_message: str,
    user_text: str,
    images_base64: list[str],
    model: str = "gpt-4o",
) -> dict:
    text = await chat_with_vision(system_message, user_text, images_base64, model)
    return _parse_json_response(text)
