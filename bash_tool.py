from pydantic import BaseModel,Field
import subprocess
from pathlib import Path

class BashParams(BaseModel):
    command: str = Field(description="Bash command to execute")
    timeout: float | None = Field(None, description="Timeout in seconds (optional)")

dangerous_command=["rm -rf /"]

def bash_commond(p:BashParams,cwd:Path=None)->str:
    for c in dangerous_command:
        if c in p.command:
            return f"Dangerous command: {c}"
    command=["bash","-c",p.command]
    try:
        result=subprocess.run(
            command,
            timeout=p.timeout,
            capture_output=True
        )
    except Exception as e:
        result=f"{type(e).__name__:{str(e)}}"
    return str(result)
            

if __name__=="__main__":
    p=BashParams.model_validate(
        {
            "command":"ls -al",
            "timeout":1.0
        }
    )
    res=bash_commond(p=p)
    print(res)