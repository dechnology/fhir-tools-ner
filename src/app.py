# 匯入必要的套件
import os
import sys
import time
import shutil
import subprocess
import xml.etree.ElementTree as ET
from elasticsearch import Elasticsearch
import requests
import json
from collections import defaultdict
from pydantic import BaseModel
import pandas as pd
from datetime import datetime
import uuid
from celery import Celery
from celery.result import AsyncResult
import redis
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from pydantic import BaseModel
import re
import concurrent.futures
import traceback
from colorama import Fore, Style
start_time = time.time()
# print(f"{Fore.GREEN}MedCAT package importing...{Style.RESET_ALL}", end="", flush=True)
# from medcat.cat import CAT
import_time = time.time()
# print(f"{Fore.GREEN} done. ({import_time - start_time:.2f} sec){Style.RESET_ALL}")

# 初始化 Elasticsearch 客戶端
umls_client = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "jpDUH1dC"),
    verify_certs=False
)

# 初始化 Flask 應用程式
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, methods=["GET", "POST", "PUT", "DELETE"])
app.config['UPLOAD_FOLDER'] = '../data/input'
app.config['PIPE_FOLDER'] = '../data/pipe_result'

# ===== Queue =====
celery = Celery(
    "app",
    backend='redis://localhost:6379/0',
    broker='redis://localhost:6379/0'
)
celery.conf.update(app.config)
TaskBase = celery.Task

print("celery.main", celery.main)

class ContextTask(TaskBase):
    def __call__(self, *args, **kwargs):
        with app.app_context():
            return TaskBase.__call__(self, *args, **kwargs)

celery.Task = ContextTask

@celery.task(bind=True)
def process_medical_text_task(self, file_id, sqe, type, file_path):
    try:
        process_medical_text(self.request.id, file_id, sqe, type, file_path)
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        # save error msg to file (pipe_result folder)
        with open(f"../data/pipe_result/{file_id}-{sqe}-{type}-{self.request.id}.error.txt", "w") as file:
            file.write("process_medical_text_task error\n")
            file.write(str(e))
            file.write(traceback.format_exc())

# ===== Redis with persistence configuration =====
r = redis.Redis(host='localhost', port=6379, db=0)

# 確保上傳目錄存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 輔助常數
NEWLINE = "\n"
NONE_SYMBOL = "-"

# # 載入 MedCAT 模型與 UMLS 子集字典（在應用程式啟動時載入一次）
# print(f"{Fore.GREEN}MedCAT Model and UMLS Dictionary Subset loading...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)
# model = "mc_modelpack_snomed_int_16_mar_2022_25be3857ba34bdd5.zip"
# cat = CAT.load_model_pack(f'../models/{model}')

# # 因應v1的暴力解法，需要載入字典到pandas進行查詢(這個部分還先不能拿掉)
# print(f"{Fore.GREEN}waiting for UMLS Dictionary Subset...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)
# # Total
# umls_sub_dict = "filtered_data.csv"
# umls_df = pd.read_csv(f"../data/dict/{umls_sub_dict}", sep='|', header=None, keep_default_na=False)
# umls_df.columns = [
#     'CUI', 'LAT', 'TS', 'LUI', 'STT', 'SUI', 'ISPREF', 'AUI', 'SAUI',
#     'SCUI', 'SDUI', 'SAB', 'TTY', 'CODE', 'STR', 'SRL', 'SUPPRESS', 'CVF'
# ]
# print("umls_df")
# print(umls_df.head())

# # # LOINC
# # loinc_sub_dict = "filtered_loinc_1.txt"
# # loinc_df = pd.read_csv(f"../data/dict/{loinc_sub_dict}", sep='|', header=None, keep_default_na=False)
# # loinc_df.columns = [
# #     'CUI', 'TTY', 'CODE', 'STR'
# # ]
# # print("loinc_df")
# # print(loinc_df.head())
# # nan_rows = loinc_df[loinc_df.isna().any(axis=1)]
# # # print(nan_rows)

# # # RxNorm
# # rxnorm_sub_dict = "filtered_rxnorm_1.txt"
# # rxnorm_df = pd.read_csv(f"../data/dict/{rxnorm_sub_dict}", sep='|', header=None, keep_default_na=False)
# # rxnorm_df.columns = [
# #     'CUI', 'TTY', 'CODE', 'STR'
# # ]
# # print("rxnorm_df")
# # print(rxnorm_df.head())
# # nan_rows = rxnorm_df[rxnorm_df.isna().any(axis=1)]
# # # print(nan_rows)

# # # SNOMED CT US Edition
# # snomedctus_sub_dict = "filtered_snomedct_us_1.txt"
# # snomedctus_df = pd.read_csv(f"../data/dict/{snomedctus_sub_dict}", sep='|', header=None, keep_default_na=False)
# # snomedctus_df.columns = [
# #     'CUI', 'TTY', 'CODE', 'STR'
# # ]
# # print("snomedctus_df")
# # print(snomedctus_df.head())
# # nan_rows = snomedctus_df[snomedctus_df.isna().any(axis=1)]
# # # print(nan_rows)
# model_loaded_time = time.time()
# print(f"{Fore.GREEN} done. ({model_loaded_time - import_time:.2f} sec){Style.RESET_ALL}")

# 初始化 OpenAI 客戶端（建議使用環境變數來存放 API 金鑰）
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("請設定 OPENAI_API_KEY 環境變數")
client = OpenAI(api_key=openai_api_key)


# 封裝從第 1 步開始的邏輯為函式
def process_medical_text(task_id, file_id, sqe, type, file_path):
    global r
    global umls_df, loinc_df, rxnorm_df, snomedctus_df
    
    r.hset(f'sqe:{file_id}-{sqe}-{type}-{task_id}', 'status', 'running')
    sqe_start_time = time.time()

    # 第 1 步：預處理
    # 將每個病患的紀錄儲存為一個文字檔
    file_name = os.path.basename(file_path)
    file_base_name = ".".join(file_name.split(".")[:-2])
    file_ext = file_name[file_name.rfind(".")+1:]

    # 第 2 步：LLM 精煉
    # 讀取內容並拆分
    with open(file_path, "r") as file:
        content = file.read()

    split_content = content.split("\n\n")
    final_content = []
    for paragraph in split_content:
        lines = paragraph.split("\n")
        for i in range(0, len(lines), 10):
            final_content.append("\n".join(lines[i:i+10]))
    split_content = final_content
    standardized_content = ""

    # # 單執行續處理
    # for i, segment in enumerate(split_content):
    #     # 顯示預覽
    #     lines = segment.splitlines()
    #     print(
    #         f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
    #     )
    #     print(f"{Fore.WHITE}file_id {file_id} sqe {sqe}: {i+1}/{len(split_content)} 正在精煉...{Style.RESET_ALL}", end="", flush=True)
    #     seqment_start_time = time.time()

    #     # 呼叫 OpenAI API 進行處理
    #     standardization_completion = client.chat.completions.create(
    #         model="gpt-4o-2024-08-06",
    #         messages=[
    #             {
    #                 "role": "system",
    #                 "content": (
    #                     "將使用者的內容翻譯成英文並執行標準化、精煉、以及縮寫展開（詞展開）。對於狀態詞後的實體，確保狀態詞適用於後續的每個實體。"
    #                 )
    #             },
    #             {"role": "user", "content": segment}
    #         ],
    #         max_completion_tokens=16383
    #     )

    #     seqment_end_time = time.time()
    #     print(f"{Fore.WHITE} 完成。({round(seqment_end_time - seqment_start_time, 2)} sec)\n{Style.RESET_ALL}")
    #     # 合併所有段落
    #     standardized_content += standardization_completion.choices[0].message.content

    # thread 函數定義
    def process_segment(i, segment, client, file_id, sqe):
        lines = segment.splitlines()
        print(
            f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
        )
        print(f"{Fore.WHITE}file_id {file_id} sqe {sqe}: {i+1}/{len(split_content)} 正在精煉...{Style.RESET_ALL}", end="", flush=True)
        segment_start_time = time.time()
        
        # 呼叫 OpenAI API 進行處理
        standardization_completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "將使用者的內容翻譯成英文並執行標準化、精煉、以及縮寫展開（詞展開）。對於狀態詞後的實體，確保狀態詞適用於後續的每個實體。"
                    )
                },
                {"role": "user", "content": segment}
            ],
            max_completion_tokens=16383
        )
        
        segment_end_time = time.time()
        print(f"{Fore.WHITE} 完成。({round(segment_end_time - segment_start_time, 2)} sec)\n{Style.RESET_ALL}")
        
        # 回傳結果
        return standardization_completion.choices[0].message.content

    # thread主函数，使用 ThreadPoolExecutor 平行處理所有段落，並控制最大併發任務數
    def parallel_process_content(split_content, client, file_id, sqe, max_concurrent_tasks=2):
        results = [None] * len(split_content)  # 預留一個與段落數量相同的結果清單
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent_tasks) as executor:
            futures = {
                executor.submit(process_segment, i, segment, client, file_id, sqe): i
                for i, segment in enumerate(split_content)
            }
            for future in concurrent.futures.as_completed(futures):
                index = futures[future]  # 根據 future 找到對應的索引
                results[index] = future.result()  # 按原順序保存結果
        return "".join(results)  # 按順序組裝結果

    # 平行處理所有段落
    standardized_content = parallel_process_content(split_content, client, file_id, sqe, max_concurrent_tasks=10)

    # 儲存標準化後的內容
    polishing_txt_path = f"../data/pipe_result/{file_base_name}.raw.polishing.txt"
    with open(polishing_txt_path, "w") as file:
        file.write(standardized_content)
    preprocess_time = time.time()
    print(f"{Fore.GREEN}file_id {file_id} sqe {sqe} 精煉時間: {round(preprocess_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")
    r.hset(f'sqe:{file_id}-{sqe}-{type}-{task_id}', 'status', 'polished')
    latest_task_id = r.hget(f'latest_sqe:{file_id}-{sqe}-{type}', 'task_id').decode('utf-8')
    if task_id == latest_task_id:
        r.hset(f'latest_sqe:{file_id}-{sqe}-{type}', 'filepath_polish', polishing_txt_path)

    # 第 3 步：語言學擷取（MedCAT）
    # ref_data = ""
    # entities = cat.get_entities(standardized_content)
    # # 儲存實體為 JSON 檔案
    # medcat_json_path = f"../data/pipe_result/{file_base_name}.raw.polishing.MedCAT.json"
    # with open(medcat_json_path, "w") as json_file:
    #     json.dump(entities, json_file, indent=2)
    # linguistic_extraction_time = time.time()
    # print(f"{Fore.GREEN}file_id {file_id} sqe {sqe} 語言學擷取時間: {round(linguistic_extraction_time - preprocess_time, 2)} sec{Style.RESET_ALL}")
    # r.hset(f'sqe:{file_id}-{sqe}-{type}-{task_id}', 'status', 'extracted')

    # 第 4 步：醫學規範化
    # id_count_dict = {}
    output_txt_path = f"../data/pipe_result/{file_base_name}.raw.polishing.output.txt"
    # with open(output_txt_path, "w") as file:
    #     pass
    #     file.write("index|chunk|cui|source|code|string|acc\n")
    #     entity_list = entities['entities']
    #     index_now = 0
    #     for key, entity in entity_list.items():
    #         cui_str = entity.get('cui', NONE_SYMBOL)
    #         sab_str = NONE_SYMBOL
    #         code_str = NONE_SYMBOL
    #         # 從 UMLS 資料集中取得詳細資訊
    #         cui_df = umls_df[umls_df['SCUI'] == cui_str]
    #         preferred_df = cui_df[cui_df['ISPREF'] == 'Y']
    #         if not preferred_df.empty:
    #             target_df = preferred_df[preferred_df['TTY'] == 'PT']
    #             if target_df.empty:
    #                 target_df = preferred_df[preferred_df['TTY'] == 'FN']
    #         else:
    #             target_df = cui_df
    #         if not target_df.empty:
    #             cui_str = target_df.iloc[0]['CUI']
    #             sab_str = target_df.iloc[0]['SAB']
    #             code_str = target_df.iloc[0]['CODE']
    #             str_str = target_df.iloc[0]['STR']
    #         else:
    #             sab_str = "<LOST>"
    #             code_str = "<LOST>"
    #             str_str = "<LOST>"
    #         # 寫入檔案
    #         if entity.get('start') > index_now:
    #             file.write(f"{index_now}|{standardized_content[index_now:entity.get('start')].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")
    #         file.write(f"{entity.get('start')}|{standardized_content[entity.get('start'):entity.get('end')].replace(NEWLINE, '<NEW_LINE>')}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}|{entity.get('acc', NONE_SYMBOL)}{NEWLINE}")
    #         # ref_data += f"{entity.get('start')}|{standardized_content[entity.get('start'):entity.get('end')].replace(NEWLINE, '<NEW_LINE>')}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}|{entity.get('acc', NONE_SYMBOL)}{NEWLINE}"
    #         if f'{sab_str}:{code_str}' in id_count_dict:
    #             id_count_dict[f'{sab_str}:{code_str}']["count"] += 1
    #         else:
    #             id_count_dict[f'{sab_str}:{code_str}'] = {
    #                 "source":sab_str,
    #                 "code":code_str,
    #                 "code_name":str_str,
    #                 "text":standardized_content[entity.get('start'):entity.get('end')],
    #                 "unique":1,
    #                 "count":1,
    #                 "confidence":0
    #             }
    #         index_now = entity.get('end')
    #     # 有可能最後一個entity的end不是content的結尾
    #     if index_now < len(standardized_content):
    #         file.write(f"{index_now}|{standardized_content[index_now:].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")

    # medical_normalization_time = time.time()
    # print(f"{Fore.GREEN}file_id {file_id} sqe {sqe} 醫學規範化時間: {round(medical_normalization_time - linguistic_extraction_time, 2)} sec{Style.RESET_ALL}")
    sqe_end_time = time.time()
    # print(f"{Fore.BLUE}file_id {file_id} sqe {sqe} 總時間: {round(sqe_end_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")
    # r.hset(f'sqe:{file_id}-{sqe}-{type}-{task_id}', 'status', 'normalized')



    # 第 5 步：LLM 抓entity
    id_count_dict_LLM = {}
    # 讀取內容並拆分
    with open(polishing_txt_path, "r") as file:
        content = file.read()

    split_content = content.split("\n\n")
    final_content = []
    for paragraph in split_content:
        lines = paragraph.split("\n")
        for i in range(0, len(lines), 10):
            final_content.append("\n".join(lines[i:i+10]))
    split_content = final_content



    # thread 函數定義
    def process_NER_segment(try_index, i, segment, client, file_id, sqe):
        # 顯示預覽
        lines = segment.splitlines()
        print(f"{Fore.WHITE}file_id {file_id} sqe {sqe}: {i+1}/{len(split_content)} LLM_Try({try_index+1}/{total_retry}) 正在透過LLM抓取以下內容...{Style.RESET_ALL}", end="", flush=True)
        print(
            f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
        )
        llm_extract_start_time = time.time()


        compare_index = 0

        # 呼叫 OpenAI API 進行處理
        llm_extract_completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",

            # 我的prompt
            messages=[
                {
                    "role": "system",
                    "content": (
                        """將使用者的內容進行切割後執行NER，標示出UMLS Term: SNOMED CT International (SNOMEDCT_US), RxNorm (RXNORM), LOINC(LNC)，並附加適合用來對各來源進行搜尋的關鍵詞，結果以JSON輸出
**demonstration**

input:
檢傷內容\nFever (R50.9)\n判定依據: 發燒/畏寒 發燒，看起來有病容\n檢驗結果: CRP: 25 mg/L\n處方籤: Kineret 100 MG/0.67 ML

output:
{
    "result": [
    {
        "type": "non-entity",
        "clue": "檢傷內容\n"
    },
    {
        "type": "SNOMEDCT_US",
        "clue": "Fever (R50.9)\n",
        "concept": "Fever, unspecified",
        "search": {
        "Concept_Name": ["Fever"],
        "Descriptions": ["unspecified"],
        "Attributes": [],
        "Relationships": []
        }
    },
    {
        "type": "non-entity",
        "clue": "判定依據: "
    },
    {
        "type": "SNOMEDCT_US",
        "clue": "發燒/畏寒 發燒，看起來有病容\n",
        "concept": "Fever with chills (finding)",
        "search": {
        "Concept_Name": ["Fever", "chills"],
        "Descriptions": ["finding"],
        "Attributes": [],
        "Relationships": []
        }
    },
    {
        "type": "non-entity",
        "clue": "檢驗結果: "
    },
    {
        "type": "LNC",
        "clue": "CRP: 25 mg/L\n",
        "concept": "C reactive protein [Mass/volume] in Serum or Plasma",
        "search": {
        "Component": ["C reactive protein", "CRP"],
        "Property": ["Mass/volume", "Concentration"],
        "System": ["Serum", "Plasma"],
        "Time_Aspect": ["Point in time", "Pt"],
        "Scale/Method": ["Quantitative", "Qn"]
        },
        "value": "25",
        "unit": "mg/L"
    },
    {
        "type": "non-entity",
        "clue": "處方籤: "
    },
    {
        "type": "RXNORM",
        "clue": "Kineret 100 MG/0.67 ML",
        "concept": "Kineret 100 MG in 0.67 ML Prefilled Syringe",
        "search": {
        "Ingredient": ["Kineret"],
        "Strength/Dose": ["100 MG"],
        "Dosage_Form": ["Prefilled Syringe"],
        "Route_of_Administration": [],
        "Frequency_and_Duration": [],
        "Brand_Name": ["Kineret"]
        }
    }
    ]
}
"""
                    )
                },
                {"role": "user", "content": segment}
            ],
            max_completion_tokens=16383,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "llm_extract_response",
                    "schema": {
                        "type": "object",
                        "name": "NER_Result",
                        "properties": {
                            "result": {
                                "type": "array",
                                "items": {
                                    "anyOf": [
                                        {
                                            "type": "object",
                                            "description": "This span is not an entity",
                                            "properties": {
                                                "type": {
                                                    "type": "string",
                                                    "enum": ["non-entity"]
                                                },
                                                "clue": {
                                                    "type": "string",
                                                    "description": "The text in non-entity span"
                                                }
                                            },
                                            "required": ["type", "clue"],
                                            "additionalProperties": False
                                        },
                                        {
                                            "type": "object",
                                            "description": "This span should been tagged as an SNOMEDCT_US entity",
                                            "properties": {
                                                "type": {
                                                    "type": "string",
                                                    "enum": ["SNOMEDCT_US"]
                                                },
                                                "clue": {
                                                    "description": "The text in SNOMEDCT_US entity span",
                                                    "type": "string"
                                                },
                                                "concept": {
                                                    "description": "The concept string in SNOMEDCT_US source",
                                                    "type": "string"
                                                },
                                                "search": {
                                                    "description": "What keywords are most likely to find a matching concept in SNOMEDCT US Edition",
                                                    "type": "object",
                                                    "properties": {
                                                        "Concept_Name": {
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Concept_Name keyword in SNOMEDCT US Edition",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Descriptions": {
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Descriptions keyword in SNOMEDCT US Edition",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Attributes": {
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Attributes keyword in SNOMEDCT US Edition",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Relationships": {
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Relationships keyword in SNOMEDCT US Edition",
                                                                "type": "string"
                                                            }
                                                        }
                                                    },
                                                    "required": ["Concept_Name", "Descriptions", "Attributes", "Relationships"],
                                                    "additionalProperties": False
                                                }
                                            },
                                            "required": ["type", "clue", "concept", "search"],
                                            "additionalProperties": False
                                        },
                                        {
                                            "type": "object",
                                            "description": "This span should been tagged as an RXNORM entity",
                                            "properties": {
                                                "type": {
                                                    "type": "string",
                                                    "enum": ["RXNORM"]
                                                },
                                                "clue": {
                                                    "description": "The text in RXNORM entity span",
                                                    "type": "string"
                                                },
                                                "concept": {
                                                    "description": "The concept string in RXNORM source",
                                                    "type": "string"
                                                },
                                                "search": {
                                                    "description": "What keywords are most likely to find a matching concept in RXNORM",
                                                    "type": "object",
                                                    "properties": {
                                                        "Ingredient": {
                                                            "description": "List the most important Ingredient in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Ingredient keyword in RXNORM",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Strength/Dose": {
                                                            "description": "List the most important Strength/Dose in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Strength/Dose keyword in RXNORM",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Dosage_Form": {
                                                            "description": "List the most important Dosage_Form in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Dosage_Form keyword in RXNORM",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Route_of_Administration": {
                                                            "description": "List the most important Route_of_Administration in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Route_of_Administration keyword in RXNORM",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Frequency_and_Duration": {
                                                            "description": "List the most important Frequency_and_Duration in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Frequency_and_Duration keyword in RXNORM",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Brand_Name": {
                                                            "description": "List the most important Brand_Name in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Brand_Name keyword in RXNORM",
                                                                "type": "string"
                                                            }
                                                        }
                                                    },
                                                    "required": ["Ingredient", "Strength/Dose", "Dosage_Form", "Route_of_Administration", "Frequency_and_Duration", "Brand_Name"],
                                                    "additionalProperties": False
                                                }
                                            },
                                            "required": ["type", "clue", "concept", "search"],
                                            "additionalProperties": False
                                        },
                                        {
                                            "type": "object",
                                            "description": "This span should been tagged as an LOINC entity",
                                            "properties": {
                                                "type": {
                                                    "type": "string",
                                                    "enum": ["LNC"]
                                                },
                                                "clue": {
                                                    "description": "The text in LOINC entity span",
                                                    "type": "string"
                                                },
                                                "concept": {
                                                    "description": "The concept string in LOINC source",
                                                    "type": "string"
                                                },
                                                "search": {
                                                    "description": "What keywords are most likely to find a matching concept in LOINC",
                                                    "type": "object",
                                                    "properties": {
                                                        "Component": {
                                                            "description": "List the most important Component in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Component keyword in LOINC",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Property": {
                                                            "description": "List the most important Property in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Property keyword in LOINC",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "System": {
                                                            "description": "List the most important System in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "System keyword in LOINC",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Time_Aspect": {
                                                            "description": "List the most important Time_Aspect in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Time_Aspect keyword in LOINC",
                                                                "type": "string"
                                                            }
                                                        },
                                                        "Scale/Method": {
                                                            "description": "List the most important Scale/Method in order of significance",
                                                            "type": "array",
                                                            "items": {
                                                                "description": "Scale/Method keyword in LOINC",
                                                                "type": "string"
                                                            }
                                                        }
                                                    },
                                                    "required": ["Component", "Property", "System", "Time_Aspect", "Scale/Method"],
                                                    "additionalProperties": False
                                                },
                                                "value": {
                                                    "description": "value infomation in LOINC entity span",
                                                    "type": ["string", "null"]
                                                },
                                                "unit": {
                                                    "description": "unit infomation in LOINC entity span",
                                                    "type": ["string", "null"]
                                                }
                                            },
                                            "required": ["type", "clue", "concept", "search", "value", "unit"],
                                            "additionalProperties": False
                                        }
                                    ]
                                }
                            }
                        },
                        "required": ["result"],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            }
        )

        llm_extract_end_time = time.time()
        print(f"{Fore.WHITE} 完成。({round(llm_extract_end_time - llm_extract_start_time, 2)} sec)\n{Style.RESET_ALL}")
        # 以concept id當key，統計出現次數
        # count-1. 對llm_extract_completion.choices[0].message.content進行json解碼
        # count-2. 以result中每個entity元素的id這個key進行次數統計，輸出到id_count_dict
        llm_extract_json = json.loads(llm_extract_completion.choices[0].message.content)
        # print(llm_extract_json)
        # 儲存llm_extract_json為JSON檔案
        llmExtractTemp_txt_path = f"../data/pipe_result/{file_base_name}.raw.polishing.llmExtractTemp_{try_index}_{i}.txt"
        # with open(llmExtractTemp_txt_path, "w") as file:
        #     file.write(json.dumps(llm_extract_json, indent=4))


        # 我的prompt對應的解析方式
        def get_candidate_from_umls_subset_by_search_keywords(source, concept, search, threshold=50):
            try:
                if source == "SNOMEDCT_US":
                    index_route = "snomedct_us"
                elif source == "RXNORM":
                    index_route = "rxnorm"
                elif source == "LNC":
                    index_route = "lnc"
                else:
                    raise ValueError(f"LLM generated source: {source}, which is not supported (extract stage)")
                should = [
                    {
                        "multi_match": {
                            "query": concept,
                            "fields": ["STR"]
                        }
                    }
                ]
                for keyword_type, search_keywords in search.items():
                    print(keyword_type, search_keywords)
                    # 把每一組轉換為should的格式
                    if not search_keywords:
                        continue
                    for keyword in search_keywords:
                        should.append(
                            {
                                "multi_match": {
                                    "query": keyword,
                                    "fields": ["STR"]
                                }
                            }
                        )
                query_body = {
                    "query": {
                        "bool": {
                            "should": should,
                            "minimum_should_match": 1
                        }
                    },
                    "size": 10
                }
                response = umls_client.search(index=index_route, body=query_body)

                return [hit['_source']['STR'] for hit in response['hits']['hits']]
            except Exception as e:
                # save to file
                error_log_path = f"../data/pipe_result/{file_base_name}.raw.polishing.error.log"
                with open(error_log_path, "a") as file:
                    file.write(f"get_candidate_from_umls_subset_by_search_keywords Error: {e}\n")
                    file.write(traceback.format_exc())
        
        questions = []
        no_candidate_span_list = []
        for span_index, entity in enumerate(llm_extract_json["result"]):
            if entity["type"] == "non-entity":
                continue
            # 透過search這個key來搜尋對應字典的concept的code_name和code_id
            candidates = get_candidate_from_umls_subset_by_search_keywords(entity["type"], entity["concept"], entity["search"])
            # print(f"candidates: {candidates}")
            if candidates:
                questions.append({
                    "index": span_index,
                    "source": entity["type"],
                    "term": entity["clue"],
                    "choices": candidates
                })
            else:
                no_candidate_span_list.append(span_index)
        # print(f"questions: {questions}")
        # 儲存questions為JSON檔案
        llmExtractQuestions_txt_path = f"../data/pipe_result/{file_base_name}.raw.polishing.llmExtractQuestions_{try_index}_{i}.txt"
        # with open(llmExtractQuestions_txt_path, "w") as file:
        #     file.write(json.dumps(questions, indent=4))
        
        # 呼叫 OpenAI API 進行選擇
        user_content = json.dumps({"questions": questions})
        # print(f"User Content: {user_content}")
        if questions:
            llm_answer_completion = client.chat.completions.create(
                model="gpt-4o-2024-08-06",

                # 我的prompt
                messages=[
                    {
                        "role": "system",
                        "content": (
                            """選擇一個最能反映概念核心、涵蓋常見情境且不包含多餘修飾詞的UMLS概念描述，以JSON輸出如下格式：
{
    "answers":[
        {
            "index": "<index>",
            "source": "<source>",
            "term": "<term>",
            "choice": "<choice>"
        }
    ]
}
"""
                        )
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                max_completion_tokens=16383,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "llm_answer_response",
                        "schema": {
                            "name": "Best_matching_UMLS_concept",
                            "type": "object",
                            "properties": {
                                "answers": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "index": {
                                                "description": "refers to the index of the entity in the original text",
                                                "type": "integer"
                                            },
                                            "source": {
                                                "type": "string",
                                                "enum": ["SNOMEDCT_US", "RXNORM", "LNC"]
                                            },
                                            "term": {
                                                "type": "string"
                                            },
                                            "choice": {
                                                "type": "string"
                                            }
                                        },
                                        "required": ["index", "source", "term", "choice"],
                                        "additionalProperties": False
                                    }
                                }
                            },
                            "required": ["answers"],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                }
            )
            llm_answer_json = json.loads(llm_answer_completion.choices[0].message.content)
            # print(llm_answer_json)
            # 儲存answers為JSON檔案
            llmExtractAnswers_txt_path = f"../data/pipe_result/{file_base_name}.raw.polishing.llmExtractAnswers_{try_index}_{i}.txt"
            # with open(llmExtractAnswers_txt_path, "w") as file:
            #     file.write(json.dumps(llm_answer_json, indent=4))
            
            if not llm_answer_json["answers"]:
                pass
                # print(f"{Fore.RED}No answers generated for this segment{Style.RESET_ALL}")

            # 依據index欄位值，將llm_answer_json轉為dict，index為key
            llm_answer_dict = {}
            for answer in llm_answer_json["answers"]:
                llm_answer_dict[answer["index"]] = answer
            
            # 將answer的choice查找Elasticsearch，得到的code和正式名稱，寫回llm_extract_json
            try:
                for span_index, entity in enumerate(llm_extract_json["result"]):
                    if entity["type"] == "non-entity":
                        continue
                    if span_index in no_candidate_span_list:
                        # 捨棄沒有候選答案的 entity
                        entity["type"] = "non-entity"
                        continue
                    # print(f"i: {i}")
                    # print(f"span_index: {span_index}")
                    # print(f"entity: {entity}")
                    # print(f"llm_answer_dict: {llm_answer_dict}")
                    # llm_answer_dict[span_index] may not exist
                    if span_index not in llm_answer_dict:
                        # 捨棄沒有候選答案的 entity
                        entity["type"] = "non-entity"
                        continue
                    answer = llm_answer_dict[span_index]
                    llm_extract_json["result"][span_index]["concept"] = answer["choice"]
                    if entity["type"] == "SNOMEDCT_US":
                        index_route = "snomedct_us"
                    elif entity["type"] == "RXNORM":
                        index_route = "rxnorm"
                    elif entity["type"] == "LNC":
                        index_route = "lnc"
                    else:
                        raise ValueError(f'LLM generated type: {entity["type"]}, which is not supported (extract stage)')
                    query_body = {
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "match": {
                                            "STR": answer["choice"]
                                        }
                                    }
                                ]
                            }
                        }
                    }
                    response = umls_client.search(index=index_route, body=query_body)
                    if response['hits']['hits']:
                        code_str = response['hits']['hits'][0]['_source']['CODE']
                        code_name = response['hits']['hits'][0]['_source']['STR']
                        llm_extract_json["result"][span_index]["code"] = code_str
                        llm_extract_json["result"][span_index]["try_index"] = try_index
                        cui = response['hits']['hits'][0]['_source']['CUI']
                        icd10_query_body = {
                            "query": {
                                "bool": {
                                    "must": [
                                        {
                                            "match": {
                                                "CUI": cui
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                        icd10_response = umls_client.search(index="icd10", body=icd10_query_body)
                        # check if icd10_response['hits']['hits'] is not empty
                        if icd10_response['hits']['hits']:
                            icd10_code_str = icd10_response['hits']['hits'][0]['_source']['CODE']
                            icd10_code_name = icd10_response['hits']['hits'][0]['_source']['STR']
                            llm_extract_json["result"][span_index]["icd10"] = {
                                "code": icd10_code_str,
                                "name": icd10_code_name
                            }
                        else:
                            llm_extract_json["result"][span_index]["icd10"] = {
                                "code": "N/A",
                                "name": "N/A"
                            }
                    else:
                        pass
                        # print(f"{Fore.RED}Answer not found for clue: {entity["clue"]}{Style.RESET_ALL}")
            except Exception as e:
                # save to file
                error_log_path = f"../data/pipe_result/{file_base_name}.raw.polishing.error.log"
                with open(error_log_path, "a") as file:
                    file.write(f"將answer的choice查找Elasticsearch，得到的code和正式名稱，寫回llm_extract_json Error: {e}\n")
                    file.write(traceback.format_exc())
            
            return llm_extract_json["result"]

    # thread主函数，使用 ThreadPoolExecutor 平行處理所有段落，並控制最大併發任務數
    def parallel_process_NER_task(split_content, client, file_id, sqe, try_index, max_concurrent_tasks=2):
        try:
            results = [None] * len(split_content)  # 預留一個與段落數量相同的結果清單
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent_tasks) as executor:
                futures = {
                    executor.submit(process_NER_segment, try_index, i, segment, client, file_id, sqe): i
                    for i, segment in enumerate(split_content)
                }
                for future in concurrent.futures.as_completed(futures):
                    index = futures[future]  # 根據 future 找到對應的索引
                    results[index] = future.result()  # 按原順序保存結果

            # 將所有結果合併
            one_try_merged_results = []
            for result in results:
                if result:
                    one_try_merged_results.extend(result)
            return one_try_merged_results
        except Exception as e:
            # save to file
            error_log_path = f"../data/pipe_result/{file_base_name}.raw.polishing.error.log"
            with open(error_log_path, "a") as file:
                file.write(f"parallel_process_NER_task Error: {e}\n")
                file.write(traceback.format_exc())
            return []

    total_retry = 3
    results = []
    for try_index in range(total_retry):
        one_try_merged_results = parallel_process_NER_task(split_content, client, file_id, sqe, try_index, max_concurrent_tasks=20)
        print("try_index", try_index)
        print(one_try_merged_results)
        results.extend(one_try_merged_results)
    print(results)

    # 以source:concept_id當key，統計出現次數
    try:
        for entity in results:
            if entity['type'] == "non-entity":
                continue
            if "code" not in entity:
                continue
            key = f"{entity['type']}:{entity['code']}"
            if key in id_count_dict_LLM:
                id_count_dict_LLM[key]["count"] += 1
                if entity["try_index"] not in id_count_dict_LLM[key]["model_support"]:
                    id_count_dict_LLM[key]["model_support"].append(entity["try_index"])
                    id_count_dict_LLM[key]["unique"] += 1
                    id_count_dict_LLM[key]["model_support"].append(entity["try_index"])
            else:
                id_count_dict_LLM[key] = {
                    "source": entity["type"],
                    "code": entity["code"],
                    "code_name": entity["concept"],
                    "text": entity["clue"],
                    "model_support": [entity["try_index"]],
                    "icd10": entity["icd10"],
                    "unique": 1,
                    "count": 1,
                    "confidence": 0
                }

        # 將count轉換為confidence
        for key in id_count_dict_LLM:
            # # total_retry + 1 是 LLM 次數 + MedCAT模型偵測的1次
            # id_count_dict_LLM[key]["confidence"] = min(id_count_dict_LLM[key]["unique"] / (total_retry + 1), 1.0)
            # total_retry 是 LLM 次數
            id_count_dict_LLM[key]["confidence"] = id_count_dict_LLM[key]["unique"] / total_retry
    
    except Exception as e:
        # save to file
        error_log_path = f"../data/pipe_result/{file_base_name}.raw.polishing.error.log"
        with open(error_log_path, "a") as file:
            file.write(f"以source:concept_id當key，統計出現次數 Error: {e}\n")
            file.write(traceback.format_exc())

    # 為了讓輸出的結果保持為如下的JSON清單形式，需要進行轉換
    # {
    #     "entities": [
    #         {
    #             "source": "SNOMEDCT_US",
    #             "code": "420190008",
    #             "code_name": "Retinal detachment (disorder)",
    #             "confidence": 1.0
    #         },
    #         {
    #             "source": "LOINC",
    #             "code": "8310-5",
    #             "code_name": "Body temperature",
    #             "confidence": 0.66
    #         },
    #         {
    #             "source": "RXNORM",
    #             "code": "448141",
    #             "code_name": "Sennosides",
    #             "confidence": 0.33
    #         }
    #     ]
    # }
    tmp_entities = [{"source":v["source"], "code":v["code"], "code_name":v["code_name"], "text":v["text"], "icd10":v["icd10"], "unique":v["unique"], "confidence":v["confidence"], "count":v["count"]} for k,v in id_count_dict_LLM.items()]
    llm_extract_json = {"entities":tmp_entities}

    # count-3. 輸出id_count_dict結果
    llmExtract_txt_path = f"../data/pipe_result/{file_base_name}.raw.polishing.llmExtract.txt"
    with open(llmExtract_txt_path, "w") as file:
        # 原始prompt對應的輸出方式
        # file.write(json.dumps(id_count_dict_LLM, indent=4))
        # 組長prompt對應的輸出方式
        print(llm_extract_json)
        file.write(json.dumps(llm_extract_json, indent=4))
    llm_extract_time = time.time()
    print(f"{Fore.GREEN}file_id {file_id} sqe {sqe} LLM抓取時間: {round(llm_extract_time - sqe_end_time, 2)} sec{Style.RESET_ALL}")
    r.hset(f'sqe:{file_id}-{sqe}-{type}-{task_id}', 'status', 'llm_extracted')
    latest_task_id = r.hget(f'latest_sqe:{file_id}-{sqe}-{type}', 'task_id').decode('utf-8')
    if task_id == latest_task_id:
        r.hset(f'latest_sqe:{file_id}-{sqe}-{type}', 'filepath_llmExtract', llmExtract_txt_path)

    # 把整份output.txt檔案傳送到指定的API
    # with open(llmExtract_txt_path, "r") as file:
    #     content = file.read()
    #     url = "http://35.229.136.14:8090/contentListener"
    #     if type == "Full":
    #         headers = {
    #             'Content-Type': 'application/json',
    #             'file_id': file_id,
    #             'uid': sqe,
    #             'type': 'A'
    #         }
    #         response = requests.request("POST", url, headers=headers, data=content)
    #         headers = {
    #             'Content-Type': 'application/json',
    #             'file_id': file_id,
    #             'uid': sqe,
    #             'type': 'B'
    #         }
    #         response = requests.request("POST", url, headers=headers, data=content)
    #         headers = {
    #             'Content-Type': 'application/json',
    #             'file_id': file_id,
    #             'uid': sqe,
    #             'type': 'C'
    #         }
    #         response = requests.request("POST", url, headers=headers, data=content)
    #     else:
    #         type_mapping = {
    #             "ER": "A", # 急診病例
    #             "HR": "B", # 住院病例
    #             "LR": "C" # 檢驗紀錄
    #             }
    #         headers = {
    #             'Content-Type': 'application/json',
    #             'file_id': file_id,
    #             'uid': sqe,
    #             'type': type_mapping[type]
    #         }
    #         response = requests.request("POST", url, headers=headers, data=content)

    r.hset(f'sqe:{file_id}-{sqe}-{type}-{task_id}', 'status', 'uploaded')
    # get latest task_id
    latest_task_id = r.hget(f'latest_sqe:{file_id}-{sqe}-{type}', 'task_id').decode('utf-8')
    print(f"latest_task_id: {latest_task_id}")
    print(f"task_id: {task_id}")
    if task_id == latest_task_id:
        print(f'latest_sqe:{file_id}-{sqe}-{type} finished')
        r.hset(f'latest_sqe:{file_id}-{sqe}-{type}', 'filepath_output', output_txt_path)
        r.hset(f'latest_sqe:{file_id}-{sqe}-{type}', 'status', "uploaded")


@app.route('/txt_ner_status', methods=['POST'])
def txt_ner_status():
    global r

    type_mapping = {
        "A": "ER", # 急診病例
        "B": "HR", # 住院病例
        "C": "LR" # 檢驗紀錄
        }

    # 從request中獲取原始數據
    data = request.get_json()

    # 檢查medical_text是否存在或為空
    if not data:
        return jsonify({"error": "請求中沒有內容"}), 400
    if 'sqe' not in data or not data['sqe']:
        return jsonify({"error": "病例序號為空"}), 400
    if 'task_id' not in data or not data['task_id']:
        return jsonify({"error": "任務ID為空"}), 400
    
    
    keys = []
    for tmp_type_str in type_mapping.values():
        keys.extend(r.keys(f'sqe:{data["sqe"]}-{tmp_type_str}-{data["task_id"]}'))
    
    all_data = {}
    for key in keys:
        hash_data = r.hgetall(key)
        if hash_data:
            decoded_data = {k.decode(): v.decode() for k, v in hash_data.items()}
            all_data[key.decode()] = decoded_data

    return jsonify(all_data), 200

# 修改 Flask 應用程式的 txt_ner 路由，呼叫上述函式
@app.route('/txt_ner', methods=['POST'])
def txt_ner():
    global r

    type_mapping = {
        "A": "ER", # 急診病例
        "B": "HR", # 住院病例
        "C": "LR" # 檢驗紀錄
        }

    # 從request中獲取原始數據
    data = request.get_json()

    # 檢查medical_text是否存在或為空
    if not data:
        return jsonify({"error": "請求中沒有內容"}), 400
    if 'file_id' not in data or not data['file_id']:
        return jsonify({"error": "病例檔案ID為空"}), 400
    if 'sqe' not in data or not data['sqe']:
        return jsonify({"error": "病例序號為空"}), 400
    if 'type' in data and data['type'] not in list(type_mapping.keys()):
        return jsonify({"error": "病例種類必須是A、B、C其中一種"}), 400
    if 'text' not in data or not data['text']:
        return jsonify({"error": "請求中沒有醫學文字內容或內容為空"}), 400
    
    # 轉換
    type_str = None
    if 'type' not in data or data['type'] is None:
        type_str = "Full"  # 預設為全文
    else:
        type_str = type_mapping[data['type']]

    # 儲存檔案到指定目錄
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    random_string = uuid.uuid4().hex[:4]
    secure_filename = f'{timestamp}_medical_text_{data["file_id"]}_{data["sqe"]}_{type_str}_{random_string}.raw.txt'
    file_path = os.path.join(app.config['PIPE_FOLDER'], secure_filename)
    with open(file_path, "w") as file:
        file.write(data['text'])

    # 呼叫處理函式
    try:
        # ensure all queued task or running task NOT exist (delete with task.id)
        keys = []
        if type_str == "Full":
            for tmp_type_str in type_mapping.values():
                keys.extend(r.keys(f'sqe:{data["file_id"]}-{data["sqe"]}-{tmp_type_str}-*'))
        else:
            keys.extend(r.keys(f'sqe:{data["file_id"]}-{data["sqe"]}-{type_str}-*'))
        if keys:
            # f'sqe:{data["file_id"]}-{data["sqe"]}-{type_str}-*')中的星號部分就是task.id，終止這些任務
            for key in keys:
                # task_id像這樣：dbf2873c-89f4-4217-8107-4dc7edc08bee
                task_id = "-".join(key.decode().split("-")[-5:])
                print("try to revoke task_id:", task_id)
                task = AsyncResult(task_id, app=celery) 
                task.revoke(terminate=True)
            r.delete(*keys)
            print(f"Deleted {len(keys)} keys.")
        # 呼叫 Celery 任務
        task = process_medical_text_task.delay(data['file_id'], data['sqe'], type_str, file_path)
        # process_medical_text(file_path)
        # TODO: 這裡會有race condition，基本上沒辦法確定最新的task一定會是最新的
        if type_str == "Full":
            for type_str in type_mapping.values():
                r.hset(f'sqe:{data["file_id"]}-{data["sqe"]}-{type_str}-{task.id}', 'status', 'queued')
                r.hset(f'latest_sqe:{data["file_id"]}-{data["sqe"]}-{type_str}', 'task_id', task.id)
                r.hset(f'latest_sqe:{data["file_id"]}-{data["sqe"]}-{type_str}', 'status', 'processing')
        else:
            r.hset(f'sqe:{data["file_id"]}-{data["sqe"]}-{type_str}-{task.id}', 'status', 'queued')
            r.hset(f'latest_sqe:{data["file_id"]}-{data["sqe"]}-{type_str}', 'task_id', task.id)
            r.hset(f'latest_sqe:{data["file_id"]}-{data["sqe"]}-{type_str}', 'filepath_raw', file_path)
            r.hset(f'latest_sqe:{data["file_id"]}-{data["sqe"]}-{type_str}', 'status', 'processing')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "文字內容已接收，正在處理", "task_id": task.id}), 202
    # return jsonify({"message": "檔案處理成功", "filename": secure_filename}), 200


@app.route('/txt_ner_list', methods=['POST'])
def txt_ner_list():
    global r

    keys = r.keys('latest_sqe:*')
    unit_uploaded_keys = []
    for key in keys:
        status = r.hget(key, 'status')
        if status and status.decode('utf-8') == 'uploaded':
            unit_uploaded_keys.append(key.decode('utf-8'))
    
    # unit_uploaded_keys 中應該裝滿了類似這樣的key
    # latest_sqe:UUID-1234-ER
    # latest_sqe:UUID-1234-HR
    # latest_sqe:UUID-1234-LR
    # latest_sqe:UUID-5678-ER
    # latest_sqe:UUID-9012-HR
    # 把集齊ER+HR+LR的紀錄，設定為uploaded，其他維持processing，以JSON回傳
    # 回傳JSON範例：
    # {
    #     "records": [
    #         {
    #             "sqe": UUID-1234,
    #             "status": "uploaded",
    #             "text": "file_content"
    #         },
    #         {
    #             "sqe": UUID-5678,
    #             "status": "processing",
    #             "text": "file_content"
    #         },
    #         {
    #             "sqe": UUID-9012,
    #             "status": "processing",
    #             "text": "file_content"
    #         }
    #     ]
    # }
    # 1. 列出所有非重複的sqe
    # 2. 針對每個非重複的sqe
    #       2-1. 確認 ER, HR, LR 的key是否都存在
    #           2-1-1. 都存在的話，就把準備回傳的status設定為uploaded
    #           2-1-2. 把這三者的text合併成一個text
    #       2-2. 沒有都存在的sqe，status就設定為processing
    # 3. 回傳JSON
    unique_sqe = set()
    for key in unit_uploaded_keys:
        main_part = key.split(":")[-1]
        file_id = main_part[:36]
        sqe = main_part[37:].rsplit('-', 1)[0]
        unique_sqe.add(f'{file_id}-{sqe}')
    records = []
    for u in unique_sqe:
        file_id = u[:36]
        sqe = u[37:]
        status = "processing"
        text = ""
        all_exist = True
        for type_str in ["ER", "HR", "LR"]:
            key = f'latest_sqe:{u}-{type_str}'
            if key not in unit_uploaded_keys:
                all_exist = False
                break
        if all_exist:
            status = "uploaded"
            for type_str in ["ER", "HR", "LR"]:
                key = f'latest_sqe:{u}-{type_str}'
                filepath = r.hget(key, 'filepath_raw')
                if filepath is not None:
                    filepath = filepath.decode('utf-8')
                else:
                    status = "processing"
                    text = ""
                    break
                with open(filepath, "r") as file:
                    text += file.read()
                    text += "\n\n\n\n\n\n\n\n"
        records.append({
            "file_id": f'{file_id}',
            "sqe": f'{sqe}',
            "status": status,
            "text": text
        })
    return jsonify({"records": records}), 200



@app.route('/txt_ner_result', methods=['POST'])
def txt_ner_result():
    global r
    
    # 從request中獲取原始數據
    data = request.get_json()
    # data應該是這樣的JSON：
    # {
    #     "sqe": 1234,
    #     "text": "fever with cough and cold",
    #     "cuis": ["115793008", "110465008"]
    # }

    # response應該是這樣的JSON：
    # {
    #     "text": "fever, fever with chills", # 這裡就是data['text']中的內容，再度回傳確認
    #     "entities": [
    #         {
    #             "entity": 466, # output.txt中的code
    #             "value": "fever", # output.txt中的string
    #             "start_ind": 0, # output.txt中的index
    #             "end_ind": 5, # output.txt中的index + len(string), 但是<NEW_LINE>視為一個字元
    #             "acc": 0.99 # output.txt中的acc
    #         },
    #         {
    #             "entity": 466,
    #             "value": "fever",
    #             "start_ind": 7,
    #             "end_ind": 12,
    #             "acc": 0.99
    #         }
    #     ]
    # }

    # 掠過所有參數檢查，直接進行處理

    # 1. 以sqe為key，搭配 [ER, HR, LR] 三種type，找出最新的output.txt檔案
    # 2. 讀取所有output.txt檔案，找出所有的entity
    # index|chunk|cui|source|code|string|acc
    # 0|**|-|-|-|-|-
    # 2|Admission|C0184666|SNOMEDCT_US|32485007|Hospital admission|0.99
    # 11| |-|-|-|-|-
    # 12|Diagnosis|C0011900|SNOMEDCT_US|439401001|Diagnosis|0.97
    # 21|:**  <NEW_LINE>|-|-|-|-|-
    # 27|Retinal detachment|C0035305|SNOMEDCT_US|42059000|Retinal detachment|0.96
    # 3. 打包成eneities，組成response
    # 4. 回傳response
    file_id = data['file_id']
    sqe = data['sqe']
    entities = []
    base_ind = 0
    for type_str in ["ER", "HR", "LR"]:
        key = f'latest_sqe:{file_id}-{sqe}-{type_str}'
        print(key)
        print(r.hget(key, 'filepath_output'))
        filepath = r.hget(key, 'filepath_output').decode('utf-8')
        last_ind = 0
        last_chunk = ""
        with open(filepath, "r") as file:
            lines = file.readlines()
            for line in lines[1:]:
                parts = line.split("|")
                last_ind = int(parts[0])
                last_chunk = parts[1]
                # 計算<NEW_LINE>的數量
                new_line_count = parts[1].count("<NEW_LINE>")
                cui = parts[2]
                if cui == "-" or parts[4] == "<LOST>":
                    continue
                entity = {
                    "entity": int(parts[4]),
                    "value": parts[5].rstrip('\n'),
                    "start_ind": base_ind + int(parts[0]),
                    "end_ind": base_ind + int(parts[0]) + len(parts[1]) - new_line_count*(len("<NEW_LINE>")-1),
                    "acc": float(parts[6])
                }
                entities.append(entity)
        base_ind = base_ind + last_ind + len(last_chunk) - new_line_count*(len("<NEW_LINE>")-1) + 8 # 8是檔案間的\n
    response = {
        "text": data['text'],
        "entities": entities
    }
    return jsonify(response), 200



@app.route('/txt_llm_result', methods=['POST'])
def txt_llm_result():
    global r
    
    # 從request中獲取原始數據
    data = request.get_json()
    # data應該是這樣的JSON：
    # {
    #     "sqe": 1234,
    # }

    # response應該是這樣的JSON：
    # {
    #     "entities": {
    #        "LNCCBC Group": {
    #            "concept": "Complete Blood Count",
    #            "count": 1
    #        },
    #        "LNC26515-7": {
    #            "concept": "Platelet count",
    #            "count": 1
    #        },
    #        "LNC6690-2": {
    #            "concept": "Leukocyte count",
    #            "count": 1
    #        }
    #     }
    # }

    # 掠過所有參數檢查，直接進行處理

    # 1. 以sqe為key，搭配 [ER, HR, LR] 三種type，找出最新的llmExtract.txt檔案
    # 2. 讀取所有llmExtract.txt檔案，找出所有的entity，進行二次count
    # 3. 打包成eneities，組成response
    # 4. 回傳response
    file_id = data['file_id']
    sqe = data['sqe']
    entities = {}
    for type_str in ["ER", "HR", "LR"]:
        key = f'latest_sqe:{file_id}-{sqe}-{type_str}'
        filepath = r.hget(key, 'filepath_llmExtract').decode('utf-8')
        with open(filepath, "r") as file:
            type_entities_json = json.load(file)
            # 原始
            # for entity_id, entity in type_entities_json.items():
            #     if entity_id in entities:
            #         entities[entity_id]["count"] += entity["count"]
            #     else:
            #         entities[entity_id] = entity
            # 組長
            for entity in type_entities_json["entities"]:
                if f'{entity["source"]}:{entity["code"]}' in entities:
                    entities[f'{entity["source"]}:{entity["code"]}']["count"] += entity["count"]
                else:
                    entities[f'{entity["source"]}:{entity["code"]}'] = entity
    
    # 如同上述的response範例
    response = {
        "entities": list(entities.values())
    }
    return jsonify(response), 200



@app.route('/get_confirmed_status', methods=['POST'])
def get_confirmed_status():
    global r
    
    # 從request中獲取原始數據
    data = request.get_json()
    # data應該是這樣的JSON：
    # {
    #     "file_id": "b8c525f6-7ed1-4e7c-95ad-872046af4f60"
    #     "sqe": "1234"
    # }

    # response應該是這樣的JSON：
    # {
    #     "is_confirmed": true
    # }

    # 掠過所有參數檢查，直接進行處理

    # 1. 如果pipe_result中不存在file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json，就建立新的（初始狀態）
    # 2. 讀取file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json，修改is_confirmed的值
    # 3. 寫回file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json
    is_confirmed = None
    if not os.path.exists(f'../data/pipe_result/file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json'):
        with open(f'../data/pipe_result/file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json', "w") as file:
            json.dump({"is_confirmed": None}, file)
    else:
        with open(f'../data/pipe_result/file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json', "r") as file:
            info = json.load(file)
        is_confirmed = info["is_confirmed"]
    
    # 如同上述的response範例
    response = {
        "file_id": data["file_id"],
        "sqe": data["sqe"],
        "is_confirmed": is_confirmed
    }
    return jsonify(response), 200



@app.route('/set_confirmed_status', methods=['POST'])
def set_confirmed_status():
    global r
    
    # 從request中獲取原始數據
    data = request.get_json()
    # data應該是這樣的JSON：
    # {
    #     "file_id": "b8c525f6-7ed1-4e7c-95ad-872046af4f60"
    #     "sqe": "1234",
    #     "is_confirmed": true
    # }

    # response應該是這樣的JSON：
    # {
    #     "is_confirmed": true
    # }

    # 掠過所有參數檢查，直接進行處理

    # 1. 如果pipe_result中不存在sqe_{sqe}_info.json，就建立新的（初始狀態）
    # 2. 讀取sqe_{sqe}_info.json，修改is_confirmed的值
    # 3. 寫回sqe_{sqe}_info.json
    # 1.
    if not os.path.exists(f'../data/pipe_result/file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json'):
        with open(f'../data/pipe_result/file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json', "w") as file:
            json.dump({"is_confirmed": data["is_confirmed"]}, file)
    else:
        with open(f'../data/pipe_result/file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json', "r") as file:
            info = json.load(file)
        info["is_confirmed"] = data["is_confirmed"]
        with open(f'../data/pipe_result/file_id_{data["file_id"]}_sqe_{data["sqe"]}_info.json', "w") as file:
            json.dump(info, file)
    
    # 如同上述的response範例
    response = {
        "file_id": data["file_id"],
        "sqe": data["sqe"],
        "is_confirmed": data['is_confirmed']
    }
    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=62593, debug=True, use_reloader=False)
