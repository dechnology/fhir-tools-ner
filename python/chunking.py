import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import json
from collections import defaultdict
from pydantic import BaseModel
from openai import OpenAI


class JSONStructure(BaseModel):
    chunk_list: list[str]

# 初始化OpenAI客户端
client = OpenAI(api_key="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")

# 建立benchmark，紀錄初始時間
import time
start_time = time.time()

user_context = """denied sore throat, headache, chest pain, dyspnea, abd pain, n/v, dysuria/urinary freq/urinary urgency"""
# user_context handler
print(user_context)
completion = client.beta.chat.completions.parse(
    model="gpt-4o-2024-08-06",
    messages=[
        {"role": "system", "content": """split the user text (chunking) and make each chunk a separate entity. For entities that follow qualifier words, ensure the qualifier word applies to each of the following entities. Finally, abbreviation expansion is required, and mapping all eneities to the original sentence."""},
        {"role": "user", "content": user_context}
    ],
    response_format=JSONStructure,
)

# 获取解析后的结构化数据
parsed_response = completion.choices[0].message.parsed

# 输出结果
print("parsed_response:")
print(parsed_response.json(indent=2))

# 儲存萃取出的結構化資訊到f"../data/{file_name}_v3plus_{index+1}.raw.(standardized).cTAKES.LLM.txt"
# with open(f"../data/{file_name}_v3plus_{index+1}.raw.(standardized).cTAKES.LLM.txt", "w") as file:
#     file.write(parsed_response.model_dump_json(indent=2))
# row_format_time = time.time()
# print(f"Row {index+1} format time: {row_format_time - row_standardized_time} seconds")
# row_end_time = time.time()
# print(f"Row {index+1} total time: {row_end_time - row_start_time} seconds")

end_time = time.time()
print(f"Total time: {end_time - start_time} seconds")
