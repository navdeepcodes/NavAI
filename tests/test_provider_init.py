from brain.providers.gemini_provider import GeminiProvider
from brain.providers.groq_provider import GroqProvider
from brain.providers.ollama_provider import OllamaProvider
from brain.providers.openrouter_provider import OpenRouterProvider

providers = [

    GeminiProvider(),

    GroqProvider(),

    OllamaProvider(),

    OpenRouterProvider()

]

print()

for provider in providers:

    print(

        provider.name,

        "OK"

    )
    