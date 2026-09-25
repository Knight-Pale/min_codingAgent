from dataclasses import dataclass,field
from pathlib import Path
from typing import Callable
from pydantic import BaseModel
@dataclass
class ToolContext:
    cwd:Path
    readed_file:list[str]=field(default_factory=list)

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

def truncated_for_text(maxLines:int,text:list[str]):
    pass

def get_Right_path(path:str,ctx:ToolContext)->Path:
    raw=Path(path)
    path=raw if raw.is_absolute() else (ctx.cwd/raw).resolve()
    return path