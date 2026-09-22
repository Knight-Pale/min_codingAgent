from get_client import get_client
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from tools import read_tool,ToolContext
import os
import json

load_dotenv()
TOOL_TABLE={read_tool.name:read_tool}
TOOLS=[t.declaration() for t in TOOL_TABLE.values()]

def agent_loop(messages:list,client:OpenAI,ctx:ToolContext):
    while True:
        resp=client.chat.completions.create(
            model=os.environ['Model'],
            messages=messages,
            tools=TOOLS,
            stream=True
        )
        reply =[]
        calls={}
        for chunk in resp:
            if not chunk.choices:
                continue
            delta=chunk.choices[0].delta
            if delta.content:
                print(delta.content,end="")
                reply.append(delta.content)

            for tc in delta.tool_calls or []:
                slot=calls.setdefault(tc.index,{"id":"","name":"","arguments":""})
                if tc.id:
                    slot["id"]=tc.id
                if tc.function.name:
                    slot["name"]=tc.function.name
                if tc.function.arguments:
                    slot["arguments"]+=tc.function.arguments

        text="".join(reply) or None
        assistant_msg={"role":"assistant","content":text}
        if calls:
            assistant_msg["tool_calls"]=[
                {
                    "id":c["id"],
                    "type":"function",
                    "function":{
                        "name":c["name"],
                        "arguments":c["arguments"]
                    }
                }for _,c in sorted(calls.items())
            ]
        messages.append(assistant_msg)

        if not calls:
            return

        for _,c in sorted(calls.items()):
            tool = TOOL_TABLE.get(c["name"])
            try:
                if tool is None:
                    result=f"Unknown tool:{c['name']}"
                else:
                    params=tool.params.model_validate(json.loads(c["arguments"] or "{}"))
                    result=tool.execute(params,ctx)
            except Exception as e:
                result=f"{type(e).__name__}:{e}"
            messages.append(
                {
                    "role":"tool",
                    "tool_call_id":c["id"],
                    "content":str(result)
                }
            )


if __name__=="__main__":
    client =get_client()
    ctx=ToolContext(cwd=Path.cwd())
    messages=[]
    while True:
        print("--------------------------------------------")
        query=input()
        print("--------------------------------------------")
        if query=="exit" or query == "q":
            break
        messages.append(
            {
                "role":"user",
                "content":query
            }
        )
        agent_loop(messages=messages,client=client,ctx=ctx)
        


        
