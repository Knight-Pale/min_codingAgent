from get_client import get_client
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from tools import TOOLS,tools_calls
from tools_class import ToolContext
import os
import json
from colorama import init,Fore

load_dotenv()

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
                print(Fore.BLUE+delta.content,end="")
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
        tools_calls(calls=calls,messages=messages,ctx=ctx)

def user_input()->str:
    try:
            query=input().strip()
    except (EOFError,KeyboardInterrupt):     # Ctrl-D / Ctrl-C
            return "exit"
    return query
        


if __name__=="__main__":
    init(autoreset=True)
    client =get_client()
    ctx=ToolContext(cwd=Path.cwd())
    messages=[]
    while True:
        print("\n--------------------------------------------")
        query = user_input()
        print("--------------------------------------------\n")
        if query.lower() in ("exit","q"):
            break
        if not query:                            # 空输入不要发给模型
            continue
        messages.append(
            {
                "role":"user",
                "content":query
            }
        )
        agent_loop(messages=messages,client=client,ctx=ctx)
        


        
