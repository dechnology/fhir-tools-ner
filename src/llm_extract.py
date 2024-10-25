# llm_extract.py
import os
import sys
import time
import shutil
import subprocess
import xml.etree.ElementTree as ET
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
from colorama import Fore, Style

# 輔助常數
NEWLINE = "\n"
NONE_SYMBOL = "-"



# 初始化 OpenAI 客戶端（建議使用環境變數來存放 API 金鑰）
openai_api_key = os.getenv("OPENAI_API_KEY", "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")
if not openai_api_key:
    raise ValueError("請設定 OPENAI_API_KEY 環境變數")
client = OpenAI(api_key=openai_api_key)


sqe = 100
polishing_txt_path = "../data/input/polishing_example.txt"
file_base_name = "example"

# 讀取內容並拆分
with open(polishing_txt_path, "r") as file:
    content = file.read()

split_content = content.split("\n\n")

id_count_dict = {}
for _ in range(3):
    for i, segment in enumerate(split_content):
        # 顯示預覽
        lines = segment.splitlines()
        print(
            f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
        )
        print(f"{Fore.WHITE}sqe {sqe}: {i+1}/{len(split_content)} 正在透過LLM抓取...{Style.RESET_ALL}", end="", flush=True)
        llm_extract_start_time = time.time()

        # 呼叫 OpenAI API 進行處理
        llm_extract_completion = client.chat.completions.create(
            model="gpt-4o-2024-08-06",

            # 原始prompt
#                 messages=[
#                     {
#                         "role": "system",
#                         "content": (
#                             """將使用者的內容進行切割後執行NER，標示出UMLS Term (SNOMEDCT_US, RXNORM, LNC, ICD10)與字元位置資訊，以JSON輸出： 
# {
#   "result": [
#     {"non-entity": "檢傷內容\n"},
#     {"clue": "Fever (R50.9)\n", "concept": "Fever, unspecified", "vocabulary": "ICD10", "keyword": ["Fever"], "start":123, "end":137 },
#     {"non-entity": "判定依據: "},
#     {"clue": "發燒/畏寒 發燒，看起來有病容", "concept": "Fever with chills (finding)", "vocabulary": "SNOMEDCT_US", "id": "274640006", "keyword": ["Fever", "chills", "finding"], "start":248, "end":263 },
#     {"non-entity": "檢驗結果: "},
#     {"clue": "CRP: 25 mg/L", "concept": "C reactive protein [Mass/volume] in Serum or Plasma", "vocabulary": "LNC", "id": "1988-5", "keyword": ["C reactive protein", "Mass/volume", "Serum", "Plasma"], "value": "25", "unit": "mg/L", "start":420, "end":432 },
#     {"non-entity": "處方籤: "},
#     {"clue": "Kineret 100 MG/0.67 ML", "concept": "Kineret 100 MG in 0.67 ML Prefilled Syringe", "vocabulary": "RXNORM", "id": "727714", "keyword": ["Kineret", "100 MG", "0.67 ML", "Prefilled Syringe"], "start":500, "end":522 }
#   ]
# }
# """
#                         )
#                     },
#                     {"role": "user", "content": segment}
#                 ],

            # 組長的prompt
            messages=[
                {
                    "role": "user",
                    "content": (
                        """你是一個醫學專家，請根據下面文本內容，標示出snomed ct, loinc, rxnorm code id 與其full name, 輸出格式為JSON list並且包含code id, id's code name 與文本內容出現的起始和結束位置。如果沒有code id就不用輸出。
**demonstration**

input:"A 22-year-old man was otherwise healthy and denied any systemic disease. The patient had progressive floaters in his right eye for 3-4 days, and photopsia was noted for 2 days. He visited LMD and RD was diagnosed. He then visited 馬偕hospital and was referred to NTUH. This time, he was admitted for surgical intervention\nOphtho history: OP (-) see above, Trauma (-)\nPast history: DM(-), HTN(-), CAD(-), Asthma (-)\nAllergy: nil\nFamily history: no hereditary ocular disease\nCurrent Medication:\nNTUH:Nil\nOther:nil\n中草藥:nil\n保健食品:nil\nTravel: nil\n身體診查(Physical Examination)\n入院時之身體檢查(Physical Examination at admission)\nBH: 164 cm, BW: 48 kg,\nT: 36.4 °C, P: 77 bpm, R: 17 /min,\nBP: 133 / 96 mmHg,\nPain score: 3 ,\n處方籤: Kineret 100 MG/0.67 ML"

output:
{"entities":[{"source":"SNOMEDCT","code_id":"248536006","code_name":"Photopsia","start_position":98,"end_position":106},{"source":"SNOMEDCT","code_id":"80394007","code_name":"Retinal detachment","start_position":141,"end_position":143},{"source":"SNOMEDCT","code_id":"73211009","code_name":"Asthma","start_position":314,"end_position":320},{"source":"LOINC","code_id":"8310-5","code_name":"Body temperature","start_position":602,"end_position":611},{"source":"LOINC","code_id":"8867-4","code_name":"Heart rate","start_position":617,"end_position":623},{"source":"LOINC","code_id":"9279-1","code_name":"Respiratory rate","start_position":628,"end_position":640},{"source":"LOINC","code_id":"8480-6","code_name":"Systolic blood pressure","start_position":646,"end_position":648},{"source":"LOINC","code_id":"8462-4","code_name":"Diastolic blood pressure","start_position":651,"end_position":653},{"source":"RXNORM","code_id":"349325","code_name":"Anakinra 100 MG/ML [Kineret]","start_position":696,"end_position":715}]}

以下是文本內容：
""" + segment
                    )
                }
            ],
            temperature=0.5,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "llm_extract_response",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                "source": {
                                    "type": "string",
                                    "enum": ["SNOMEDCT", "LOINC", "RXNORM"]
                                },
                                "code_id": {
                                    "type": "string"
                                },
                                "code_name": {
                                    "type": "string"
                                },
                                "start_position": {
                                    "type": "integer",
                                    "minimum": 0
                                },
                                "end_position": {
                                    "type": "integer",
                                    "minimum": 0
                                }
                                },
                                "required": ["source", "code_id", "code_name", "start_position", "end_position"]
                            }
                            }
                        },
                        "required": ["entities"]
                    }
                }
            }
        )

        llm_extract_end_time = time.time()
        print(f"{Fore.WHITE} 完成。({round(llm_extract_end_time - llm_extract_start_time, 2)} sec)\n{Style.RESET_ALL}")
        # 以concept id當key，統計出現次數
        # 1. 對llm_extract_completion.choices[0].message.content進行json解碼
        # 2. 以result中每個entity元素的id這個key進行次數統計，輸出到id_count_dict
        llm_extract_json = json.loads(llm_extract_completion.choices[0].message.content)
        print(llm_extract_json)

        # 原始prompt對應的解析方式
        # for entity in llm_extract_json["result"]:
        #     if "id" in entity:
        #         if entity["id"] in id_count_dict:
        #             id_count_dict[f'{entity["vocabulary"]}{entity["id"]}']["count"] += 1
        #         else:
        #             id_count_dict[f'{entity["vocabulary"]}:{entity["id"]}'] = {"concept":entity["concept"], "count":1}

        # 組長prompt對應的解析方式
        for entity in llm_extract_json["entities"]:
            if f'{entity["source"]}{entity["code_id"]}' in id_count_dict:
                id_count_dict[f'{entity["source"]}{entity["code_id"]}']["count"] += 1
            else:
                id_count_dict[f'{entity["source"]}:{entity["code_id"]}'] = {
                    "source":entity["source"],
                    "code":entity["code_id"],
                    "code_name":entity["code_name"],
                    "count":1,
                    "confidence":0
                }
# 將count轉換為confidence
for key in id_count_dict:
    id_count_dict[key]["confidence"] = id_count_dict[key]["count"] / 3

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
tmp_entities = [{"source":v["source"], "code":v["code"], "code_name":v["code_name"], "confidence":v["confidence"]} for k,v in id_count_dict.items()]
llm_extract_json = {"entities":tmp_entities}

# 3. 輸出id_count_dict結果
llmExtract_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.llmExtract.txt"
with open(llmExtract_txt_path, "w") as file:
    # 原始prompt對應的輸出方式
    # file.write(json.dumps(id_count_dict, indent=4))
    # 組長prompt對應的輸出方式
    file.write(json.dumps(llm_extract_json, indent=4))
