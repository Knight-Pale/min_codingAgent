from dotenv import load_dotenv
from openai import OpenAI
import os
load_dotenv()

def get_client():
    client=OpenAI(
        base_url=os.environ["base_url"],
        api_key=os.environ["DEEPSEEK_API_KEY"]
    )
    return client