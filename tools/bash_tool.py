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
            text=True,            # 解码成文本：别把 b'...\n...' 的 repr 喂给模型
            encoding="utf-8",
            errors="replace",
            cwd=ctx.cwd,
        )
    except Exception as e:
        return f"{type(e).__name__}:{e}"
    # 旧实现直接 str(CompletedProcess)，模型看到的是
    # "CompletedProcess(args=[...], stdout=b'...\\n...', stderr=b'...')"：
    # 既不是说明里承诺的「stdout+stderr 合并」，还得自己去解析字节字面量。
    return (f"exit code: {result.returncode}\n"
            f"stdout:\n{result.stdout.rstrip()}\n"
            f"stderr:\n{result.stderr.rstrip()}")

bash_tool=Tool(
    name="bash",
    description="Execute a bash command in the current working directory. Returns the exit code plus stdout and stderr as text.",
    params=BashParams,
    execute=_bash
)


if __name__=="__main__":
    p=BashParams.model_validate(
        {
            "command":"ls -al",
            "timeout":10.0   # 自测专用：Windows 下 bash 冷启动可能超过 1s，别让自测假失败
        }
    )
    ctx=ToolContext(
        cwd=Path(__file__).resolve().parent.parent   # 仓库根目录，换机器也能跑
    )
    res=_bash(p=p,ctx=ctx)
    print(res)