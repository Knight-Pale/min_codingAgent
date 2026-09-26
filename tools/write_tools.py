from .tools_class import Tool,ToolContext,get_Right_path
from pydantic import BaseModel,Field
from pathlib import Path

class WriteParams(BaseModel):
    path:str=Field(description="要写入的文件路径")
    text:str=Field("",description="要写入的文本")

def _write(p:WriteParams,ctx:ToolContext):
    path = get_Right_path(p.path,ctx=ctx)
    if path.is_file():
        return f"Wrong:{path}已存在,如需修改请使用其他工具"
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,"w",encoding="utf-8") as f:
        try :
            f.write(p.text)
        except Exception as e:
            return f"{type(e).__name__}:{e}"
    ctx.readed_file.append(str(path))
    return f"已经成功写入{path}"

write_tool=Tool(
    name="write",
    description="新建一个文件并写入文本。如果文本已经存在并有修改需求，请使用其他工具",
    params=WriteParams,
    execute=_write
)
