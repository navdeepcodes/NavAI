from core.tool_executor import ToolExecutor
from tools.tool_context import ToolContext

executor = ToolExecutor()

result = executor.execute(

    tool_name="browser",

    action="search",

    context=ToolContext(),

    query="Mike AI Assistant"

)

print(result)