from pydantic import BaseModel,Field
import subprocess
from .tools_class import ToolContext,Tool
from pathlib import Path

class BashParams(BaseModel):
    command: str = Field(description="Bash command to execute")
    timeout: float | None = Field(None, description="Timeout in seconds (optional)")

dangerous_command=["rm -rf /"]

def _bash(p:BashParams,ctx:ToolContext)->str:
    for c in dangerous_command:
        if c in p.command:
            return f"Dangerous command: {c}"
    command=["bash","-c",p.command]
    try:
        result=subprocess.run(
            command,
            timeout=p.timeout,
            capture_output=True,
            cwd=ctx.cwd,
        )
    except Exception as e:
        result=f"{type(e).__name__:{e}}"
    return str(result)
            
bash_tool=Tool(
    name="bash",
    description="Execute a bash command in the current working directory. Returns combined stdout and stderr.",
    params=BashParams,
    execute=_bash
)


if __name__=="__main__":
    p=BashParams.model_validate(
        {
            "command":"ls -al",
            "timeout":1.0
        }
    )
    ctx=ToolContext(
        cwd="/mnt/agent-exercise/min-codingAgent"
    )
    res=_bash(p=p,ctx=ctx)
    print(res)