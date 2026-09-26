import os,textwrap
import chromadb
from dotenv import load_dotenv
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from pydantic import BaseModel,ConfigDict,Field,model_validator
from typing import Literal
from .tools_class import Tool,ToolContext

load_dotenv()
DB_DIR="/mnt/agent-exercise/min-codingAgent/chroma-data"

class Metadata(BaseModel):
    model_config=ConfigDict(extra="forbid")   # 多传字段直接报错，而不是静默丢掉
    docs_name:str=Field(description="文本片段所属文档的名字")
    docs_path:str=Field(description="文本片段所属文档的路径")
    source_type:Literal["md","txt","pdf","docx","odt"]=Field(description="文本文档所属的类型")

    def to_chroma(self)->dict:
        return self.model_dump(exclude_none=True)   # None 存不进 chroma，只能省略 key

class Documents(BaseModel):
    ids:list[str]=Field(description="文本片段对应的id，必须是字符串")
    docs:list[str]=Field(description="文本片段,与前面的id号一一对应")
    meta:list[Metadata]=Field(description="文本片段的元数据，不参与向量化")

    @model_validator(mode="after")
    def _same_length(self):
        if not len(self.ids)==len(self.docs)==len(self.meta):
            raise ValueError(f"ids/docs/meta 长度必须一致: {len(self.ids)}/{len(self.docs)}/{len(self.meta)}")
        return self

class RagAddParams(BaseModel):
    documents:Documents=Field(description="需要入库的文本数组")
    col_name:str =Field(description="用于存储目标库的名字")
class RagQueryParams(BaseModel):
    query:str=Field(description="用于检索的问题")
    col_name:str =Field(description="检索的目标库的名字")
    k:int=Field(4,ge=1,le=20,description="需要返回的文本个数")
class RagListParams(BaseModel):
    pass   # 无入参：只读地列出所有库

_client=None
_cols={}   # 按库名缓存。之前是单个全局 _col，只有第一次调用的 col_name 生效，
           # 之后所有读写都被静默路由到那个库：写会污染别人的库，查会返回错误库的结果。

def _get_embeddings():
    # api_key 不会被 chroma 持久化，它只记环境变量名。直接传 api_key 会让配置存不下来，
    # 于是别的进程打开这个 collection 时会静默回退到内置 ONNX 模型（384 维），检索全错。
    return OpenAIEmbeddingFunction(
        api_key_env_var="EMBEDDING_KEY",
        api_base=os.environ["EMBEDDING_URL"],
        model_name="BAAI/bge-m3"
    )

def _client_or_init():
    global _client
    if _client is None:
        _client=chromadb.PersistentClient(path=DB_DIR)
    return _client

_cache_warned=False
def _reset_cache():
    """丢掉进程内缓存，强制下次访问重新从磁盘读。

    chromadb 用 SharedSystemClient 按路径缓存底层 System：别的进程删库/重建后，
    进程内即使重新 PersistentClient 也只会拿到陈旧状态（表现是 rag_list 报出一个
    已不存在的库、rag_add 报 readonly database）。清掉缓存才能在不重启的情况下
    看到磁盘真相。实测开销约 0.2ms，每个工具入口调一次可以接受。
    """
    global _client,_cache_warned
    _client=None
    _cols.clear()
    try:
        from chromadb.api.shared_system_client import SharedSystemClient
        SharedSystemClient.clear_system_cache()
    except Exception as e:
        # 私有 API，换 chromadb 版本后可能消失。退化行为＝只清本模块缓存（即修复前
        # 的状态），所以这里必须出个声，避免「陈旧数据」这个 bug 悄无声息地回来。
        if not _cache_warned:
            _cache_warned=True
            print(f"[rag_tools] 警告: 无法清理 chromadb 系统缓存({type(e).__name__}: {e})，"
                  f"若其他进程改动过向量库，本进程可能读到陈旧数据。")

def get_col(col_name:str):
    cl=_client_or_init()
    if col_name not in _cols:
        _cols[col_name]=cl.get_or_create_collection(name=col_name,embedding_function=_get_embeddings())
    return _cols[col_name]

def list_cols()->list[str]:
    return sorted(c.name for c in _client_or_init().list_collections())

def rag_list()->list[tuple[str,int]]:
    # 逐个取 count：某个库的嵌入配置缺失时不该拖垮整份列表，用 -1 表示数量取不到
    out=[]
    for name in list_cols():
        try:
            out.append((name,get_col(name).count()))
        except Exception:
            out.append((name,-1))
    return out

def rag_add(doc:Documents,col_name:str)->int:
    # 用 upsert 而不是 add：add 对已存在的 id 既不报错也不更新，是静默忽略
    get_col(col_name=col_name).upsert(
        ids=doc.ids,
        documents=doc.docs,
        metadatas=[me.to_chroma() for me in doc.meta]
    )
    return len(doc.ids)

def rag_query(query:str,k:int,col_name:str)->str:
    col=get_col(col_name=col_name)
    if col.count()==0:
        return "文档索引为空，请先入库。"
    res=col.query(query_texts=[query],n_results=k)
    hits=[]
    for doc,meta,dist in zip(res["documents"][0],res["metadatas"][0],res["distances"][0]):
        where=meta.get("docs_path") or meta.get("docs_name") or "?"
        hits.append(f"[{len(hits)+1}] {where} | dist={dist:.3f}\n{doc.strip()[:1200]}")
    return "\n\n".join(hits) or "没有找到相关内容。"

def rag_add_f(d:RagAddParams,ctx:ToolContext)->str:
    try:
        _reset_cache()   # 先对齐磁盘，否则可能在已被删除的目录上写入
        rag_add(d.documents,d.col_name)
        return f"已入库 {len(d.documents.ids)} 个片段，[{d.col_name}] 当前共 {get_col(d.col_name).count()} 个。"
    except Exception as e:
        return f"Add failed: {type(e).__name__}: {e}"

def rag_query_f(q:RagQueryParams,ctx:ToolContext)->str:
    try:
        _reset_cache()   # 先对齐磁盘，否则库名校验会基于陈旧列表、查询会打在已删的 collection 上
        # 库名拼错时，get_or_create 会静默建一个空库并只回“索引为空”，
        # 看上去像“没搜到”，实际是查错了地方。这里直接报错并列出可用库名。
        names=list_cols()
        if q.col_name not in names:
            return f"向量库 [{q.col_name}] 不存在，当前可用库名: {', '.join(names) if names else '(无)'}。请用上述库名重试。"
        return rag_query(q.query,q.k,col_name=q.col_name)
    except Exception as e:
        return f"Query error:{type(e).__name__}:{e}"

def rag_list_f(p:RagListParams,ctx:ToolContext)->str:
    try:
        _reset_cache()   # 这个工具是「磁盘上到底有什么」的权威答案，绝不能报陈旧数据
        cols=rag_list()
        if not cols:
            return "当前没有任何向量库，请先用 rag_add 入库。"
        lines=[f"- {name}：{'数量未知' if cnt<0 else f'{cnt} 个片段'}" for name,cnt in cols]
        return f"当前共有 {len(cols)} 个向量库：\n"+"\n".join(lines)
    except Exception as e:
        return f"List failed: {type(e).__name__}: {e}"

ragAdd_tool=Tool(
    name="rag_add",
    description="把文本片段写入本地向量库，需要提供向量库的名字，供 rag_query 检索。每个片段需要 id（字符串）、正文，以及 docs_name/docs_path/source_type 元数据。",
    params=RagAddParams,
    execute=rag_add_f
)
ragQuery_tool=Tool(
    name="rag_query",
    description="按语义检索本地文档库，需要提供向量库的名字，返回最相关的若干片段，含出处和距离（dist 越小越相关）。需要看完整上下文时再用 read 工具读原文件。",
    params=RagQueryParams,
    execute=rag_query_f
)
ragList_tool=Tool(
    name="rag_list",
    description="列出当前所有已存在的向量库（collection）及其片段数量。不确定库名、或想确认 rag_add 是否写进了正确的库时用它。",
    params=RagListParams,
    execute=rag_list_f
)


if __name__=="__main__":
    # 用临时库做冒烟测试，避免把调试数据写进真实的文档库
    DEMO_COL="rag_smoketest_demo"
    docs=Documents(
        ids=["1","2"],
        docs=[
            textwrap.dedent("""
            ### Definition:

            对于关系的不完全，我们想通过添加部分关系使得关系R变成满足某些性质，这个过程就是闭包。
            这个过程的合理性在于添加新的关系序偶对并不会影响原有的关系，保留了原有的语义，同时这些新的序偶对引入了新的语义，利于我们推导性质。
            但是注意不能添加过多的边，会使原先的语义稀释。我们会添加尽量少的边。

            关系的某些好性质:
            - reflexive:自反特性
            - symmetric:对称性
            - transitive:传递性
            """).strip(),
            textwrap.dedent("""
            Equivalence Relations 等价关系

            Definition 1:同时拥有三种性质的集合
            Definition 2: 任意一点a，对与a相连的任意一点b，a,b的关系完全等价（a,b交换仍是原图）

            等价类
            我理解的就是一个内部全部存在等价关系的集合
            在两个等价类之间的元素是不会产生任何联系的，我们可以看作集合A被R干净地分为了n个子集
            """).strip()
        ],
        meta=[
            Metadata(docs_name="离散数学笔记",docs_path="note/relations.md",source_type="md"),
            Metadata(docs_name="离散数学笔记",docs_path="note/relations.md",source_type="md")
        ]
    )
    print(rag_add_f(RagAddParams(documents=docs,col_name=DEMO_COL),ToolContext(cwd=".")))
    print(rag_query_f(RagQueryParams(query="关系集合有哪些好性质",k=2,col_name=DEMO_COL),ToolContext(cwd=".")))
    # 测完清掉，不留残余
    if _client is not None and DEMO_COL in _cols:
        _client.delete_collection(DEMO_COL)
        _cols.pop(DEMO_COL,None)
        print(f"已清理临时库 {DEMO_COL}")
