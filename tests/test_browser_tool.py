from tools.browser import BrowserTool
from tools.tool_context import ToolContext

tool = BrowserTool()

result = tool.execute(

    action="open_browser",

    context=ToolContext()

)

print(result)