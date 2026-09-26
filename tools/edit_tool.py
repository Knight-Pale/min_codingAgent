from .tools_class import ToolContext,Tool,get_Right_path
from pydantic import BaseModel,Field

class EditParams(BaseModel):
    path:str=Field(description="需要修改的文件路径")
    old_str:str=Field(description="用来匹配位置的旧文本")
    new_str:str=Field(description="用来替换的新文本")

def _edit(p:EditParams,ctx:ToolContext):
    path=get_Right_path(p.path,ctx)
    if not str(path) in ctx.readed_file:
        return f"Wrong:{path}没有在已读列表中,请先使用read工具进行阅读"
    text=path.read_text(encoding="utf-8")
    count=text.count(p.old_str)
    if count <=0:
        return f"Wrong:未找到旧文本{p.old_str},请重新读取文本，确保内容一致"
    elif count>1:
        return f"Wrong:存在多处与旧文本匹配的片段,请扩大匹配片段，确保替换的唯一性"
    path.write_text(text.replace(p.old_str,p.new_str,1),encoding="utf-8")
    return f"已成功替换{path}的文本"

edit_tool=Tool(
    name="edit",
    description="在文件中做一次精确的字符串替换。old_str 必须在文件中恰好出现一次",
    params=EditParams,
    execute=_edit
)

