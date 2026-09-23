from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from pydantic import BaseModel
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