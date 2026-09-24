import os,chromadb
from dotenv import load_dotenv
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from pydantic import BaseModel,Field
from typing import Literal
from tools_class import Tool,ToolContext
class Metadata(BaseModel):
    docs_name:str =Field(description="文本片段所属文档的名字")
    docs_path:str =Field(description="文本片段所属文档的路径")
    source_type: Literal["md", "txt", "pdf", "docx", "odt"]=Field(description="文本文档所属的类型")

    def to_chroma(self):
        return self.model_dump(exclude=True)

class Documents(BaseModel):
    ids:list[str|int]=Field(description="文本片段对应的id号")
    docs:list[str]=Field(description="文本片段,与前面的id号一一对应")
    meta:list[Metadata]=Field(description="文本片段的元数据，不参与向量化")

class RagAddParams(BaseModel):
    documents:Documents=Field(description="需要入库的文本数组")
class RagQueryParams(BaseModel):
    query:str=Field(description="用于检索的问题")
    k:int=Field(description="需要返回的文本个数")


load_dotenv()
DB_DIR="/mnt/agent-exercise/min-codingAgent/chroma-data"
embeddings=OpenAIEmbeddingFunction(
    api_key = os.environ["EMBEDDING_KEY"],
    api_base = os.environ["EMBEDDING_URL"],
    model_name="BAAI/bge-m3"
)
client=chromadb.PersistentClient(path=DB_DIR)
col=client.get_or_create_collection(
    name="docs__BgeM3V1",
    embedding_function=embeddings
)

def rag_add_f(d:RagAddParams,ctx:ToolContext):
    try:
        rag_add(d.documents)
    except Exception as e:
        return f"Add failed: {type(e).__name__}:{e}"
def rag_query_f(q:RagQueryParams,ctx:ToolContext):
    try:
        rag_query(q.query,q.k)
    except Exception as e:
        return f"Query error:{type(e).__name__}:{e}"

def rag_add(doc:Documents):
    col.add(
        ids=doc.ids,
        documents=doc.docs,
        metadatas=[me.to_chroma() for me in doc.meta]
    )
    pass
def rag_query(query:str,k:int):
    result=col.query(
        query_texts=[query],
        n_results=k
    )
    return result
ragAdd_tool=Tool(
    name="rag_add",
    description="",
    params=RagAddParams,
    execute=rag_add_f
)
ragQuery_tool=Tool(
    name="rag_query",
    description="",
    params=RagQueryParams,
    execute=rag_query_f
)

if __name__:
    docs=Documents(
        ids=["1","2"],
        docs=["""
        ### Definition:

    对于关系的不完全，我们想通过添加部分关系使得关系R变成满足某些性质，这个过程就是闭包。
    这个过程的合理性在于添加新的关系序偶对并不会影响原有的关系，保留了原有的语义，同时这些新的序偶对引入了新的语义，利于我们推导性质。
    但是注意不能添加过多的边，会使原先的语义稀释。我们会添加尽量少的边。

    关系的某些好性质:
    - reflexive:自反特性
    - symmetric:对称性
    - transitive:传递性
        """,
        """
Equivalence Relations 等价关系

Definition 1:同时拥有三种性质的集合
Definition 2: 任意一点a，对与a相连的任意一点b，a,b的关系完全等价（a,b交换仍是原图）

等价类
我理解的就是一个内部全部存在等价关系的集合
在两个等价类之间的元素是不会产生任何联系的，我们可以看作集合A被R干净地分为了n个子集
        """
        ],
        meta=[{"source_type":"md"},{"source_type":"md"}]
    )
    #rag_add(docs)
    res=rag_query("关系集合有哪些好性质",2)
    print(res["documents"])