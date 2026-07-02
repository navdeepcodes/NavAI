from google.genai import types

BROWSER_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="open_browser",
            description="Open the default browser."
        ),
        types.FunctionDeclaration(
            name="open_url",
            description="Open a URL in the browser.",
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string"
                    }
                },
                "required": ["url"]
            }
        ),
        types.FunctionDeclaration(
            name="search",
            description="Search Google.",
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string"
                    }
                },
                "required": ["query"]
            }
        )
    ]
)

TOOLS = [BROWSER_TOOL]