import os,textwrap
import chromadb
from dotenv import load_dotenv
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from pydantic import BaseModel,ConfigDict,Field,model_validator
from typing import Literal
from .tools_class import Tool,ToolContext

load_dotenv()
DB_DIR="/mnt/agent-exercise/min-codingAgent/chroma-data"
COLLECTION="docs__BgeM3V2"

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
class RagQueryParams(BaseModel):
    query:str=Field(description="用于检索的问题")
    k:int=Field(4,ge=1,le=20,description="需要返回的文本个数")

_col=None

def get_col():
    global _col
    if _col is None:
        # api_key 不会被 chroma 持久化，它只记环境变量名。直接传 api_key 会让配置存不下来，
        # 于是别的进程打开这个 collection 时会静默回退到内置 ONNX 模型（384 维），检索全错。
        embeddings=OpenAIEmbeddingFunction(
            api_key_env_var="EMBEDDING_KEY",
            api_base=os.environ["EMBEDDING_URL"],
            model_name="BAAI/bge-m3"
        )
        client=chromadb.PersistentClient(path=DB_DIR)
        _col=client.get_or_create_collection(name=COLLECTION,embedding_function=embeddings)
    return _col

def rag_add(doc:Documents)->int:
    # 用 upsert 而不是 add：add 对已存在的 id 既不报错也不更新，是静默忽略
    get_col().upsert(
        ids=doc.ids,
        documents=doc.docs,
        metadatas=[me.to_chroma() for me in doc.meta]
    )
    return len(doc.ids)

def rag_query(query:str,k:int)->str:
    col=get_col()
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
        rag_add(d.documents)
        return f"已入库 {len(d.documents.ids)} 个片段，当前共 {get_col().count()} 个。"
    except Exception as e:
        return f"Add failed: {type(e).__name__}: {e}"

def rag_query_f(q:RagQueryParams,ctx:ToolContext)->str:
    try:
        return rag_query(q.query,q.k)
    except Exception as e:
        return f"Query error:{type(e).__name__}:{e}"

ragAdd_tool=Tool(
    name="rag_add",
    description="把文本片段写入本地向量库，供 rag_query 检索。每个片段需要 id（字符串）、正文，以及 docs_name/docs_path/source_type 元数据。",
    params=RagAddParams,
    execute=rag_add_f
)
ragQuery_tool=Tool(
    name="rag_query",
    description="按语义检索本地文档库，返回最相关的若干片段，含出处和距离（dist 越小越相关）。需要看完整上下文时再用 read 工具读原文件。",
    params=RagQueryParams,
    execute=rag_query_f
)

if __name__=="__main__":
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
    print(rag_add_f(RagAddParams(documents=docs),ToolContext(cwd=".")))
    print(rag_query_f(RagQueryParams(query="关系集合有哪些好性质",k=2),ToolContext(cwd=".")))
