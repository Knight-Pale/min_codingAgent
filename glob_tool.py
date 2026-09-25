from tools_class import ToolContext,Tool,get_Right_path
from pydantic import BaseModel,Field
from pathlib import Path

class GlobParams(BaseModel):
    pattern:str=Field(description="glob 通配符模式，用来匹配文件路径（相对于 path 指定的根目录）。"
                                  "支持 *、?、[] 和 ** 递归，例如 '**/*.py' 匹配任意深度的 Python 文件，"
                                  "'src/**/test_*.py' 匹配 src 下所有测试文件，'*.md' 只匹配根目录下的 Markdown 文件。"
                                  "只想按扩展名找文件时用 '**/*.后缀'。不要用 '..' 向上穿越目录")
    path: str =Field(".",description="搜索的根目录，默认为 '.'（即当前工作目录 ctx.cwd）。"
                                     "可传相对路径（基于 ctx.cwd 解析）或绝对路径")
    count: int =Field(description="最多显示多少个文件名，从排序后的匹配结果中截取前 count 个，必须为正整数。"
                                  "匹配到的文件多于 count 时只统计总数、不显示多出的文件名；"
                                  "想先看看一共有多少个匹配文件时可以传一个大一些的值")

def _glob(p:GlobParams,ctx:ToolContext):
    try:
        target_path=get_Right_path(p.path,ctx)
        if not target_path.is_dir():
            return f"Wrong:{p.path}不是一个文件夹"
        matches= sorted(target_path.glob(p.pattern))
        if not matches:
            return "未找到匹配的文件"
        result=[str(f.relative_to(ctx.cwd))for f in matches if f.is_file()]
        if not result:
            return "Nothing"
        tot=len(result)
        result="\n".join(result[:p.count])
        result=result+f"\n共有{tot}个匹配文件，最多返回{p.count}个文件"
        return result
    except Exception as e:
        return f"glob 执行失败:{e}"

glob_tool=Tool(
    name="glob",
    description="按 glob 通配符模式搜索文件路径，返回匹配到的文件列表（路径相对于工作目录显示）。"
                "当你知道文件名或扩展名、但不清楚它具体在哪个目录时，用它快速定位；"
                "拿到具体路径后再用 read 读取文件内容。只在需要定位路径时使用，查看内容请用 read。"
                "仅返回文件，目录会被忽略；结果按路径排序，最多显示 count 个。"
                "常见用法:pattern='**/*.py' 列出工作目录下所有 Python 文件。",
    params=GlobParams,
    execute=_glob
)

if __name__=="__main__":
    p=GlobParams(
        pattern="rag_tools.py",
        path=".",
        count=4
    )
    ctx=ToolContext(
        cwd="/mnt/agent-exercise/min-codingAgent"
    )
    result=_glob(p,ctx=ctx)
    print(result)