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
    with open(f"../data/{file_name}_v1_{index+1}.raw.txt", "w") as file:
        file.write(f"==========sqe==========\n\n{row['sqe']}\n\n==========急診去辨識病歷==========\n\n{row['急診去辨識病歷']}\n\n==========住院去辨識病歷==========\n\n{row['住院去辨識病歷']}\n\n==========檢驗紀錄==========\n\n{row['檢驗紀錄']}")


    # 從f"../data/{file_name}.{index+1}.pipe.txt"讀取content
    content = ""
    with open(f"../data/{file_name}_v1_{index+1}.raw.txt", "r") as file:
        content = file.read()
        # print("split_content:")
        # print(content)

    # 调用API进行标准化转换
    standardization_completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": "You are an expert in clinical text standardization. Convert the following unstructured medical text into standardized English format."},
            {"role": "user", "content": content}
        ]
    )

    # 获取标准化后的文本
    standardized_content = standardization_completion.choices[0].message.content

    # 儲存標準化後的文本到f"../data/{file_name}.{index+1}.pipe.1.standardized.txt"
    with open(f"../data/{file_name}.{index+1}.pipe.1.standardized.txt", "w") as file:
        file.write(standardized_content)
    row_standardized_time = time.time()
    print(f"Row {index+1} standardized time: {row_standardized_time - row_start_time} seconds")

    # 输出标准化后的文本（可选）
    # print("Standardized Content:")
    # print(standardized_content)

    # 清空目錄
    input_dir = "/Users/yangnoahlin/Downloads/apache-ctakes-4.0.0.1/data/input"
    output_dir = "/Users/yangnoahlin/Downloads/apache-ctakes-4.0.0.1/data/output"
    if os.path.exists(input_dir):
        shutil.rmtree(input_dir)
    os.makedirs(input_dir)

    # 移动指定文件到输入目录
    source_file = f"../data/{file_name}.{index+1}.pipe.1.standardized.txt"
    destination_file = os.path.join(input_dir, f"{file_name}.{index+1}.pipe.1.standardized.txt")
    shutil.copy2(source_file, destination_file)

    # 调用外部程序
    result = subprocess.run([
        "/Users/yangnoahlin/Downloads/apache-ctakes-4.0.0.1/bin/runClinicalPipeline.sh",
        "--key", "08b35fd3-57c5-4548-9463-b876602ed823",
        "--inputDir", input_dir,
        "--xmiOut", output_dir
        ], capture_output=True, text=True)
    
    cTAKES_output_file = f"{output_dir}/{file_name}.{index+1}.pipe.1.standardized.txt.xmi"
    if result.returncode == 0:
        print("cTAKES Pipeline executed successfully")
        print(result.stdout)
    else:
        print("cTAKES Pipeline failed with return code", result.returncode)
        print(result.stderr)
        print("create a empty file to ensure the program can continue")
        with open(cTAKES_output_file, "w") as file:
            file.write("")
    
    # create a new file named f"../data/{file_name}.{index+1}.pipe.2.cTAKES.txt" and write the content of source_file and cTAKES_output_file into it
    standardized_with_cTAKES_file = f"../data/{file_name}.{index+1}.pipe.2.cTAKES.txt"
    standardized_with_cTAKES_content = ""
    with open(standardized_with_cTAKES_file, "w") as file:
        with open(source_file, "r") as source:
            file.write(f"{source.read()}\n\n==========cTAKES detection result==========\n\n")
        with open(cTAKES_output_file, "r") as cTAKES_output:
            file.write(cTAKES_output.read())
        standardized_with_cTAKES_content = file.read()

    
    row_run_cTAKES_time = time.time()
    print(f"Row {index+1} run cTAKES time: {row_run_cTAKES_time - row_standardized_time} seconds")

    # 调用API并传递模型
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": """
             You are an expert in structured medical data extraction, specializing in SNOMED_CT, RxNorm, and LOINC.
             Your task is to analyze standardized medical text and cTAKES detection results.
             You should identify and extract the relevant LOINC codes wherever applicable.
             Additionally, ensure that corresponding SNOMED_CT and RxNorm codes are accurately identified and supplemented.
             Convert the information into the given structured format:
            
            - `SNOMED_CT`: A list of dictionaries, each containing the following keys:
                - `id`: The unique SNOMED CT code.
                - `fsn`: The fully specified name (FSN) of the concept.
                - `text`: The raw text you found in the original content.

            - `LOINC`: A list of dictionaries, each containing the following keys:
                - `id`: The unique LOINC code.
                - `fsn`: The fully specified name (FSN) of the test or measurement.
                - `text`: The raw text you found in the original content.

            - `RxNorm`: A list of dictionaries, each containing the following keys:
                - `id`: The unique RxNorm code.
                - `fsn`: The fully specified name (FSN) of the drug.
                - `text`: The raw text you found in the original content.
            """},
            {"role": "user", "content": standardized_with_cTAKES_content}
        ],
        response_format=JSONStructure,
    )

    # 获取解析后的结构化数据
    parsed_response = completion.choices[0].message.parsed

    # 输出结果
    # print("parsed_response:")
    # print(parsed_response.model_dump_json(indent=2))

    # 儲存萃取出的結構化資訊到f"../data/{file_name}.{index+1}.pipe.3.LLM.txt"
    with open(f"../data/{file_name}.{index+1}.pipe.3.LLM.txt", "w") as file:
        file.write(parsed_response.model_dump_json(indent=2))
    row_format_time = time.time()
    print(f"Row {index+1} format time: {row_format_time - row_standardized_time} seconds")
    row_end_time = time.time()
    print(f"Row {index+1} total time: {row_end_time - row_start_time} seconds")

end_time = time.time()
print(f"Total time: {end_time - start_time} seconds")