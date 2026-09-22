from dataclasses import dataclass
from pydantic import BaseModel,Field
from pathlib import Path
from typing import Callable
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

read_tool = Tool(
    name="read",
    description="Read the contents of a file. Output is truncated for very large files; use offset/limit to page through.",
    params=ReadParams,
    execute=_read,
)
