import anthropic
import os

key = os.environ.get("ANTHROPIC_API_KEY", "NOT SET")
print(f"Key starts with: {key[:30]}...")
print(f"Key length: {len(key)}")

try:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=10,
        messages=[{"role": "user", "content": "Say hi"}]
    )
    print("API call SUCCESS:", msg.content[0].text)
except Exception as e:
    print("API call FAILED:", e)
