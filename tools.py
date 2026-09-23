from dataclasses import dataclass
from pydantic import BaseModel,Field
from pathlib import Path
from typing import Callable
from bash_tool import bash_commond,BashParams
from colorama import Fore,init
import json
@dataclass
class ToolContext:
    cwd:Path

@dataclass
class Tool:
    name:str
    description:str
    params:type[BaseModel]
    execute: Callable[[BaseModel,"ToolContext"],str]

    def declaration(self)->dict:
        schema=self.params.model_json_schema()
        schema.pop("title",None)
        return {
            "type":"function",
            "function":{
                "name":self.name,
                "description":self.description,
                "parameters":schema,
            },
        }

class ReadParams(BaseModel):
    path:str=Field(description="Path to the file to read (relative or absolute)")
    offset: int = Field(1, ge=1, description="Line number to start reading from (1-indexed)")
    limit: int | None = Field(None, ge=1, description="Maximum number of lines to read")


MAX_LINES=2000
MAX_BYTES=200*1024
def _read(p:ReadParams,ctx:ToolContext)->str:

    raw=Path(p.path)
    path=raw if raw.is_absolute() else (ctx.cwd/raw).resolve()

    lines:list[str]=[]
    used=0
    truncated=False
    total_lines=0
    cap=p.limit if p.limit is not None else MAX_LINES

    with open(path,encoding="utf-8",errors="replace") as f:
        for i,line in enumerate(f,start=1):
            total_lines=i
            if i<p.offset:
                continue
            line=line.rstrip("\n")
            used+=len(line.encode("utf-8"))+1
            if used>=MAX_BYTES or len(lines)>=cap:
                truncated=True
                break
            lines.append(line)

    if not lines:
        if truncated:
            return (f"Line {p.offset} alone exceeds the {MAX_BYTES//1024}KB limit. "
                    f"Use bash instead, e.g.: sed -n '{p.offset}p' {p.path} | head -c {MAX_BYTES}")
        return f"Offset {p.offset} is beyond end of file ({total_lines} lines total)."

    out="\n".join(lines)
    if truncated:
        shown_end=p.offset+len(lines)-1
        out+=f"\n\n[Showing lines {p.offset}-{shown_end}. Use offset={shown_end+1} to continue.]"
    return out

def _bash(p:BaseModel,ctx:ToolContext):
    return bash_commond(p,ctx.cwd)

read_tool = Tool(
    name="read",
    description="Read the contents of a file. Output is truncated for very large files; use offset/limit to page through.",
    params=ReadParams,
    execute=_read,
)
bash_tool=Tool(
    name="bash",
    description="Execute a bash command in the current working directory. Returns combined stdout and stderr.Please get user's agreement before you using it ",
    params=BashParams,
    execute=_bash
)
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