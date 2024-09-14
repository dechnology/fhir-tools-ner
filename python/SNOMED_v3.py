import os
import shutil
import subprocess
from pydantic import BaseModel
from openai import OpenAI

# 定义Pydantic模型结构
class SNOMED_CT(BaseModel):
    id: str
    fsn: str
    text: str

class LOINC(BaseModel):
    id: str
    fsn: str
    text: str

class RxNorm(BaseModel):
    id: str
    fsn: str
    text: str

class JSONStructure(BaseModel):
    SNOMED_CT: list[SNOMED_CT]
    LOINC: list[LOINC]
    RxNorm: list[RxNorm]

# 初始化OpenAI客户端
client = OpenAI(api_key="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")

# 建立benchmark，紀錄初始時間
import time
start_time = time.time()

# 開啟一個xlsx檔案，裡面每個row都是一個病人的病歷
import pandas as pd
file_name = "Testing EMR"
df = pd.read_excel(f"../data/raw/{file_name}.xlsx")
# 依序處理每個病人的病歷
# 每個row分別有四個欄位：seq, 急診去辨識病歷, 住院去辨識病歷, 檢驗紀錄
# 我們要把他重新拼裝為一個以seq為檔名的txt檔案，並以＝＝＝＝＝<欄位名稱>＝＝＝＝＝\n\n<欄位內容>的形式存起來
for index, row in df.iterrows():
    row_start_time = time.time()
    with open(f"../data/{file_name}_v3_{index+1}.raw.txt", "w") as file:
        file.write(f"==========sqe==========\n\n{row['sqe']}\n\n==========急診去辨識病歷==========\n\n{row['急診去辨識病歷']}\n\n==========住院去辨識病歷==========\n\n{row['住院去辨識病歷']}\n\n==========檢驗紀錄==========\n\n{row['檢驗紀錄']}")


    # 從f"../data/{file_name}.{index+1}.pipe.txt"讀取content
    content = ""
    with open(f"../data/{file_name}_v3_{index+1}.raw.txt", "r") as file:
        content = file.read()
        # print("split_content:")
        # print(content)

    # 调用API并传递模型
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": """
             You are an expert in structured medical data extraction in "急診去辨識病歷", "住院去辨識病歷" and "檢驗紀錄", specializing in SNOMED_CT, RxNorm, and LOINC.
             Your task is to analyze medical text and should identify and extract the relevant SNOMED_CT, RxNorm, and LOINC codes wherever applicable.
             Convert the information into the given structured format and NOT to deduplicate the information:
            
            - `SNOMED_CT`: A list of dictionaries, each containing the following keys:
                - `id`: The unique SNOMED CT code from dictionary.
                - `fsn`: The fully specified name (FSN) of the concept.
                - `text`: The raw text you found in the original content (copy the raw text chunk to here).

            - `LOINC`: A list of dictionaries, each containing the following keys:
                - `id`: The unique LOINC code from dictionary.
                - `fsn`: The fully specified name (FSN) of the test or measurement.
                - `text`: The raw text you found in the original content (copy the raw text chunk to here).

            - `RxNorm`: A list of dictionaries, each containing the following keys:
                - `id`: The unique RxNorm code from dictionary.
                - `fsn`: The fully specified name (FSN) of the drug.
                - `text`: The raw text you found in the original content (copy the raw text chunk to here).
            """},
            {"role": "user", "content": content}
        ],
        response_format=JSONStructure,
    )

    # 获取解析后的结构化数据
    parsed_response = completion.choices[0].message.parsed

    # 输出结果
    # print("parsed_response:")
    # print(parsed_response.model_dump_json(indent=2))

    # 儲存萃取出的結構化資訊到f"../data/{file_name}.{index+1}.raw.LLM.txt"
    with open(f"../data/{file_name}_v3_{index+1}.raw.LLM.txt", "w") as file:
        file.write(parsed_response.model_dump_json(indent=2))
    row_format_time = time.time()
    print(f"Row {index+1} format time: {row_format_time - start_time} seconds")
    row_end_time = time.time()
    print(f"Row {index+1} total time: {row_end_time - row_start_time} seconds")

end_time = time.time()
print(f"Total time: {end_time - start_time} seconds")