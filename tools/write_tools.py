from .tools_class import Tool,ToolContext,get_Right_path
from pydantic import BaseModel,Field

class WriteParams(BaseModel):
    path:str=Field(description="要写入的文件路径")
    text:str=Field("",description="要写入的文本")

def _write(p:WriteParams,ctx:ToolContext):
    path = get_Right_path(p.path,ctx=ctx)
    if path.is_dir():
        return f"Wrong:{path}是一个目录,不是文件"
    if path.is_file():
        return f"Wrong:{path}已存在,如需修改请使用其他工具"
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with open(path,"w",encoding="utf-8") as f:
            f.write(p.text)
    except OSError as e:
        # 父路径被同名文件占住、目录没有写权限等，都返回可读的错误串
        return f"Wrong:写入{path}失败:{type(e).__name__}:{e}"
    ctx.readed_file.append(str(path))
    return f"已经成功写入{path}"

write_tool=Tool(
    name="write",
    description="新建一个文件并写入文本。如果文本已经存在并有修改需求，请使用其他工具",
    params=WriteParams,
    execute=_write
)
