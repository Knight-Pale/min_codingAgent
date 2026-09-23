from dataclasses import dataclass
from pydantic import BaseModel,Field
from pathlib import Path
from typing import Callable
from colorama import Fore,init
import json
from bash_tool import bash_tool
from read_tools import read_tool
from tools_class import ToolContext



TOOL_TABLE={read_tool.name:read_tool,bash_tool.name:bash_tool}
TOOLS=[t.declaration() for t in TOOL_TABLE.values()]

def tools_calls(calls:dict,messages:list,ctx:ToolContext)->dict:
    for _,c in calls.items():
        tool=TOOL_TABLE.get(c['name'])
         
        try:
            if  not tool:
                result=f"Unknown tool :{c['name']}"
            else :
                check_bash=p_which_tool_use(c)
                params=tool.params.model_validate(json.loads(c["arguments"] or "{}"))
                if check_bash is True:
                    result=tool.execute(params,ctx)
                else :
                    result=f"User rejected run this command:{params},you should ask user the reason"
        except Exception as e:
            result=f"{type(e).__name__}:{e}"
        messages.append(
            {
                "role":"tool",
                "tool_call_id":c["id"],
                "content":str(result)
            }
        )
def p_which_tool_use(tool):
    print("\n----------------------")
    print("Tool Use: ",tool['name'])
    print("----------------------\n")
    if tool['name']=='bash':
        t=TOOL_TABLE.get("bash")
        params=t.params.model_validate(json.loads(tool["arguments"] or "{}"))
        print(Fore.RED+"\n即将执行以下指令:\n",params.command,"\n")
        print("------------------\n")
        query=input("如果希望不执行这个指令请输入no\n")
        print("------------------\n")
        if "no" in query or "q" in query or "exit" in query:
            return False

    return True