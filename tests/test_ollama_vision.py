from vision.screenshot import Screenshot
from brain.providers.ollama_provider import OllamaProvider

provider = OllamaProvider()

print("Taking screenshot...")
image = Screenshot().capture()
print(image)

print("Sending to Ollama...")

response = provider.client.chat(
    model=provider.vision_model,
    messages=[
        {
            "role": "user",
            "content": "Describe this screenshot.",
            "images": [image],
        }
    ],
)

print("\n===== RESPONSE =====\n")
print(type(response))
print(response)
print("\n====================\n")

print(response.message.content)