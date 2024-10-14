# 匯入必要的套件
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
start_time = time.time()
print(f"{Fore.GREEN}MedCAT package importing...{Style.RESET_ALL}", end="", flush=True)
from medcat.cat import CAT
import_time = time.time()
print(f"{Fore.GREEN} done. ({import_time - start_time:.2f} sec){Style.RESET_ALL}")

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

@celery.task
def process_medical_records_task(file_path, sqe_list=None):
    process_medical_records(file_path, sqe_list)

@celery.task(bind=True)
def process_medical_text_task(self, sqe, type, file_path):
    process_medical_text(self.request.id, sqe, type, file_path)

# ===== Redis with persistence configuration =====
r = redis.Redis(host='localhost', port=6379, db=0)

# 確保上傳目錄存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 輔助常數
NEWLINE = "\n"
NONE_SYMBOL = "-"

# 載入 MedCAT 模型與 UMLS 子集字典（在應用程式啟動時載入一次）
print(f"{Fore.GREEN}MedCAT Model and UMLS Dictionary Subset loading...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)
model = "mc_modelpack_snomed_int_16_mar_2022_25be3857ba34bdd5.zip"
cat = CAT.load_model_pack(f'../models/{model}')
print(f"{Fore.GREEN}waiting for UMLS Dictionary Subset...{NEWLINE}{Style.RESET_ALL}", end="", flush=True)

umls_sub_dict = "filtered_data.csv"
umls_df = pd.read_csv(f"../data/dict/{umls_sub_dict}", sep='|', header=None)
umls_df.columns = [
    'CUI', 'LAT', 'TS', 'LUI', 'STT', 'SUI', 'ISPREF', 'AUI', 'SAUI',
    'SCUI', 'SDUI', 'SAB', 'TTY', 'CODE', 'STR', 'SRL', 'SUPPRESS', 'CVF'
]
print(umls_df.head())
model_loaded_time = time.time()
print(f"{Fore.GREEN} done. ({model_loaded_time - import_time:.2f} sec){Style.RESET_ALL}")

# 定義 Pydantic 模型結構（若需要，可以保留）
class SNOMED_CT(BaseModel):
    raw_text_as_clues: list[str]
    implies_concepts_FSN: list[str]
    id: str

class LOINC(BaseModel):
    raw_text_as_clues: list[str]
    implies_concepts_FSN: list[str]
    id: str

class RxNorm(BaseModel):
    raw_text_as_clues: list[str]
    implies_concepts_FSN: list[str]
    id: str

class JSONStructure(BaseModel):
    SNOMED_CT: list[SNOMED_CT]
    LOINC: list[LOINC]
    RxNorm: list[RxNorm]

# 初始化 OpenAI 客戶端（建議使用環境變數來存放 API 金鑰）
openai_api_key = os.getenv("OPENAI_API_KEY", "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")
if not openai_api_key:
    raise ValueError("請設定 OPENAI_API_KEY 環境變數")
client = OpenAI(api_key=openai_api_key)


# 封裝從第 1 步開始的邏輯為函式
def process_medical_records(file_path, sqe_list=None):
    global r
    
    """
    處理醫學紀錄的主要函式。

    參數：
    - file_path: 上傳的檔案路徑
    - sqe_list: 選填，指定要處理的行序號列表
    """
    start_time = time.time()
    # 取得檔案名稱和副檔名
    file_name = os.path.basename(file_path)
    file_base_name = file_name[:file_name.rfind(".")]
    file_ext = file_name[file_name.rfind(".")+1:]

    # 讀取 Excel 檔案
    df = pd.read_excel(file_path)
    print(df.head())

    # 逐行處理每個病患的紀錄
    for index, row in df.iterrows():
        if sqe_list and index not in sqe_list:
            continue  # 如果有提供 sqe_list，則只處理指定的行

        sqe_start_time = time.time()
        sqe = row['sqe']

        # 第 1 步：預處理
        # 將每個病患的紀錄儲存為一個文字檔
        raw_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.txt"
        with open(raw_txt_path, "w") as file:
            print(row)
            file.write(
                f"**********急診去辨識病歷**********\n\n{row['急診去辨識病歷']}\n\n"
                f"**********住院去辨識病歷**********\n\n{row['住院去辨識病歷']}\n\n"
                f"**********檢驗紀錄**********\n\n{row['檢驗紀錄']}"
            )
        print("Step1 done")

        # 第 2 步：LLM 精煉
        # 讀取內容並拆分
        with open(raw_txt_path, "r") as file:
            content = file.read()

        split_content = content.split("\n\n")
        standardized_content = ""

        for i, segment in enumerate(split_content):
            # 顯示預覽
            lines = segment.splitlines()
            print(
                f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
            )
            print(f"{Fore.WHITE}sqe {sqe}: {i+1}/{len(split_content)} 正在精煉...{Style.RESET_ALL}", end="", flush=True)
            seqment_start_time = time.time()

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
                ]
            )

            seqment_end_time = time.time()
            print(f"{Fore.WHITE} 完成。({round(seqment_end_time - seqment_start_time, 2)} sec)\n{Style.RESET_ALL}")
            # 合併所有段落
            standardized_content += standardization_completion.choices[0].message.content

        # 儲存標準化後的內容
        polishing_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.txt"
        with open(polishing_txt_path, "w") as file:
            file.write(standardized_content)
        preprocess_time = time.time()
        print(f"{Fore.GREEN}sqe {sqe} 精煉時間: {round(preprocess_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")

        # 第 3 步：語言學擷取（MedCAT）
        entities = cat.get_entities(standardized_content)
        print(1)
        # 儲存實體為 JSON 檔案
        medcat_json_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.MedCAT.json"
        print(2)
        with open(medcat_json_path, "w") as json_file:
            print(3)
            json.dump(entities, json_file, indent=2)
        print(4)
        linguistic_extraction_time = time.time()
        print(f"{Fore.GREEN}sqe {sqe} 語言學擷取時間: {round(linguistic_extraction_time - preprocess_time, 2)} sec{Style.RESET_ALL}")

        # 第 4 步：醫學規範化
        output_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.output.txt"
        with open(output_txt_path, "w") as file:
            file.write("index|chunk|cui|source|code|string\n")
            entity_list = entities['entities']
            index_now = 0
            for key, entity in entity_list.items():
                cui_str = entity.get('cui', NONE_SYMBOL)
                sab_str = NONE_SYMBOL
                code_str = NONE_SYMBOL
                # 從 UMLS 資料集中取得詳細資訊
                cui_df = umls_df[umls_df['SCUI'] == cui_str]
                preferred_df = cui_df[cui_df['ISPREF'] == 'Y']
                if not preferred_df.empty:
                    target_df = preferred_df[preferred_df['TTY'] == 'PT']
                    if target_df.empty:
                        target_df = preferred_df[preferred_df['TTY'] == 'FN']
                else:
                    target_df = cui_df
                if not target_df.empty:
                    cui_str = target_df.iloc[0]['CUI']
                    sab_str = target_df.iloc[0]['SAB']
                    code_str = target_df.iloc[0]['CODE']
                else:
                    sab_str = "<LOST>"
                    code_str = "<LOST>"
                # 寫入檔案
                if entity.get('start') > index_now:
                    file.write(f"{index_now}|{standardized_content[index_now:entity.get('start')].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")
                file.write(f"{entity.get('start')}|{standardized_content[entity.get('start'):entity.get('end')].replace(NEWLINE, '<NEW_LINE>')}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}{NEWLINE}")
                index_now = entity.get('end')

        medical_normalization_time = time.time()
        print(f"{Fore.GREEN}sqe {sqe} 醫學規範化時間: {round(medical_normalization_time - linguistic_extraction_time, 2)} sec{Style.RESET_ALL}")
        sqe_end_time = time.time()
        print(f"{Fore.BLUE}sqe {sqe} 總時間: {round(sqe_end_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")

        # 把整份output.txt檔案傳送到指定的API
        with open(output_txt_path, "r") as file:
            content = file.read()
            url = "http://35.229.136.14:8090/contentListener"
            headers = {
                'Content-Type': 'application/json'
            }
            response = requests.request("POST", url, headers=headers, data=content)

        # 如果只想處理一筆記錄，可以在此處加入 break
        # break

    end_time = time.time()
    print(f"總處理時間: {round(end_time - start_time, 2)} sec")


# 封裝從第 1 步開始的邏輯為函式
def process_medical_text(task_id, sqe, type, file_path):
    global r
    
    r.hset(f'sqe:{sqe}-{type}-{task_id}', 'status', 'running')
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
    standardized_content = ""

    for i, segment in enumerate(split_content):
        # 顯示預覽
        lines = segment.splitlines()
        print(
            f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
        )
        print(f"{Fore.WHITE}sqe {sqe}: {i+1}/{len(split_content)} 正在精煉...{Style.RESET_ALL}", end="", flush=True)
        seqment_start_time = time.time()

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
            ]
        )

        seqment_end_time = time.time()
        print(f"{Fore.WHITE} 完成。({round(seqment_end_time - seqment_start_time, 2)} sec)\n{Style.RESET_ALL}")
        # 合併所有段落
        standardized_content += standardization_completion.choices[0].message.content

    # 儲存標準化後的內容
    polishing_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.txt"
    with open(polishing_txt_path, "w") as file:
        file.write(standardized_content)
    preprocess_time = time.time()
    print(f"{Fore.GREEN}sqe {sqe} 精煉時間: {round(preprocess_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")
    r.hset(f'sqe:{sqe}-{type}-{task_id}', 'status', 'polished')
    latest_task_id = r.hget(f'latest_sqe:{sqe}-{type}', 'task_id').decode('utf-8')
    if task_id == latest_task_id:
        r.hset(f'latest_sqe:{sqe}-{type}', 'filepath_polish', polishing_txt_path)

    # 第 3 步：語言學擷取（MedCAT）
    entities = cat.get_entities(standardized_content)
    # 儲存實體為 JSON 檔案
    medcat_json_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.MedCAT.json"
    with open(medcat_json_path, "w") as json_file:
        json.dump(entities, json_file, indent=2)
    linguistic_extraction_time = time.time()
    print(f"{Fore.GREEN}sqe {sqe} 語言學擷取時間: {round(linguistic_extraction_time - preprocess_time, 2)} sec{Style.RESET_ALL}")
    r.hset(f'sqe:{sqe}-{type}-{task_id}', 'status', 'extracted')

    # 第 4 步：醫學規範化
    output_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.output.txt"
    with open(output_txt_path, "w") as file:
        file.write("index|chunk|cui|source|code|string|acc\n")
        entity_list = entities['entities']
        index_now = 0
        for key, entity in entity_list.items():
            cui_str = entity.get('cui', NONE_SYMBOL)
            sab_str = NONE_SYMBOL
            code_str = NONE_SYMBOL
            # 從 UMLS 資料集中取得詳細資訊
            cui_df = umls_df[umls_df['SCUI'] == cui_str]
            preferred_df = cui_df[cui_df['ISPREF'] == 'Y']
            if not preferred_df.empty:
                target_df = preferred_df[preferred_df['TTY'] == 'PT']
                if target_df.empty:
                    target_df = preferred_df[preferred_df['TTY'] == 'FN']
            else:
                target_df = cui_df
            if not target_df.empty:
                cui_str = target_df.iloc[0]['CUI']
                sab_str = target_df.iloc[0]['SAB']
                code_str = target_df.iloc[0]['CODE']
            else:
                sab_str = "<LOST>"
                code_str = "<LOST>"
            # 寫入檔案
            if entity.get('start') > index_now:
                file.write(f"{index_now}|{standardized_content[index_now:entity.get('start')].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")
            file.write(f"{entity.get('start')}|{standardized_content[entity.get('start'):entity.get('end')].replace(NEWLINE, '<NEW_LINE>')}|{cui_str}|{sab_str}|{code_str}|{entity.get('pretty_name', NONE_SYMBOL)}|{entity.get('acc', NONE_SYMBOL)}{NEWLINE}")
            index_now = entity.get('end')
        # 有可能最後一個entity的end不是content的結尾
        if index_now < len(standardized_content):
            file.write(f"{index_now}|{standardized_content[index_now:].replace(NEWLINE, '<NEW_LINE>')}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}|{NONE_SYMBOL}{NEWLINE}")

    medical_normalization_time = time.time()
    print(f"{Fore.GREEN}sqe {sqe} 醫學規範化時間: {round(medical_normalization_time - linguistic_extraction_time, 2)} sec{Style.RESET_ALL}")
    sqe_end_time = time.time()
    print(f"{Fore.BLUE}sqe {sqe} 總時間: {round(sqe_end_time - sqe_start_time, 2)} sec{Style.RESET_ALL}")
    r.hset(f'sqe:{sqe}-{type}-{task_id}', 'status', 'normalized')



    # 第 5 步：LLM 抓entity
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

    id_count_dict = {}
    total_retry = 3
    for try_index in range(total_retry):
        for i, segment in enumerate(split_content):
            # 顯示預覽
            lines = segment.splitlines()
            print(
                f"{Fore.YELLOW}{NEWLINE.join(lines[:5])}{f' [... {len(lines)} 行]' if len(lines) > 5 else ''}{Style.RESET_ALL}"
            )
            print(f"{Fore.WHITE}LLM_Try({try_index+1}/{total_retry}) sqe {sqe}: {i+1}/{len(split_content)} 正在透過LLM抓取...{Style.RESET_ALL}", end="", flush=True)
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
                max_completion_tokens=16383,
                response_format={"type": "json_object"}
            )

            llm_extract_end_time = time.time()
            print(f"{Fore.WHITE} 完成。({round(llm_extract_end_time - llm_extract_start_time, 2)} sec)\n{Style.RESET_ALL}")
            # 以concept id當key，統計出現次數
            # 1. 對llm_extract_completion.choices[0].message.content進行json解碼
            # 2. 以result中每個entity元素的id這個key進行次數統計，輸出到id_count_dict
            llm_extract_json = json.loads(llm_extract_completion.choices[0].message.content)
            # print(llm_extract_json)

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
        id_count_dict[key]["confidence"] = id_count_dict[key]["count"] / total_retry

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
    tmp_entities = [{"source":v["source"], "code":v["code"], "code_name":v["code_name"], "confidence":v["confidence"], "count":v["count"]} for k,v in id_count_dict.items()]
    llm_extract_json = {"entities":tmp_entities}

    # 3. 輸出id_count_dict結果
    llmExtract_txt_path = f"../data/pipe_result/{file_base_name}_{sqe}.raw.polishing.llmExtract.txt"
    with open(llmExtract_txt_path, "w") as file:
        # 原始prompt對應的輸出方式
        # file.write(json.dumps(id_count_dict, indent=4))
        # 組長prompt對應的輸出方式
        file.write(json.dumps(llm_extract_json, indent=4))
    llm_extract_time = time.time()
    print(f"{Fore.GREEN}sqe {sqe} LLM抓取時間: {round(llm_extract_time - sqe_end_time, 2)} sec{Style.RESET_ALL}")
    r.hset(f'sqe:{sqe}-{type}-{task_id}', 'status', 'llm_extracted')
    latest_task_id = r.hget(f'latest_sqe:{sqe}-{type}', 'task_id').decode('utf-8')
    if task_id == latest_task_id:
        r.hset(f'latest_sqe:{sqe}-{type}', 'filepath_llmExtract', llmExtract_txt_path)

    # 把整份output.txt檔案傳送到指定的API
    with open(llmExtract_txt_path, "r") as file:
        content = file.read()
        url = "http://35.229.136.14:8090/contentListener"
        if type == "Full":
            headers = {
                'Content-Type': 'application/json',
                'uid': sqe,
                'type': 'A'
            }
            response = requests.request("POST", url, headers=headers, data=content)
            headers = {
                'Content-Type': 'application/json',
                'uid': sqe,
                'type': 'B'
            }
            response = requests.request("POST", url, headers=headers, data=content)
            headers = {
                'Content-Type': 'application/json',
                'uid': sqe,
                'type': 'C'
            }
            response = requests.request("POST", url, headers=headers, data=content)
        else:
            type_mapping = {
                "ER": "A", # 急診病例
                "HR": "B", # 住院病例
                "LR": "C" # 檢驗紀錄
                }
            headers = {
                'Content-Type': 'application/json',
                'uid': sqe,
                'type': type_mapping[type]
            }
            response = requests.request("POST", url, headers=headers, data=content)

    r.hset(f'sqe:{sqe}-{type}-{task_id}', 'status', 'uploaded')
    # get latest task_id
    latest_task_id = r.hget(f'latest_sqe:{sqe}-{type}', 'task_id').decode('utf-8')
    if task_id == latest_task_id:
        r.hset(f'latest_sqe:{sqe}-{type}', 'filepath_output', output_txt_path)
        r.hset(f'latest_sqe:{sqe}-{type}', 'status', "uploaded")


# 修改 Flask 應用程式的 xml_ner 路由，呼叫上述函式
@app.route('/xlsx_ner', methods=['POST'])
def xlsx_ner():
    global r
    
    if 'file' not in request.files:
        return jsonify({"error": "請求中沒有檔案部分"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "未選擇檔案"}), 400

    # 儲存檔案到指定目錄
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    random_string = uuid.uuid4().hex
    secure_filename = f"{timestamp}_{file.filename}_{random_string}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename)
    file.save(file_path)

    # 呼叫處理函式
    try:
        # 呼叫 Celery 任務
        task = process_medical_records_task.delay(file_path)
        # process_medical_records(file_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "檔案已接收，正在處理", "task_id": task.id}), 202
    # return jsonify({"message": "檔案處理成功", "filename": secure_filename}), 200


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
    random_string = uuid.uuid4().hex
    secure_filename = f'{timestamp}_medical_text_{data["sqe"]}_{type_str}_{random_string}.raw.txt'
    file_path = os.path.join(app.config['PIPE_FOLDER'], secure_filename)
    with open(file_path, "w") as file:
        file.write(data['text'])

    # 呼叫處理函式
    try:
        # ensure all queued task or running task NOT exist (delete with task.id)
        keys = []
        if type_str == "Full":
            for tmp_type_str in type_mapping.values():
                keys.extend(r.keys(f'sqe:{data["sqe"]}-{tmp_type_str}-*'))
        else:
            keys.extend(r.keys(f'sqe:{data["sqe"]}-{type_str}-*'))
        if keys:
            # f'sqe:{data["sqe"]}-{type_str}-*')中的星號部分就是task.id，終止這些任務
            for key in keys:
                # task_id像這樣：dbf2873c-89f4-4217-8107-4dc7edc08bee
                task_id = "-".join(key.decode().split("-")[-5:])
                print("try to revoke task_id:", task_id)
                task = AsyncResult(task_id, app=celery) 
                task.revoke(terminate=True)
            r.delete(*keys)
            print(f"Deleted {len(keys)} keys.")
        # 呼叫 Celery 任務
        task = process_medical_text_task.delay(data['sqe'], type_str, file_path)
        # process_medical_text(file_path)
        # TODO: 這裡會有race condition，基本上沒辦法確定最新的task一定會是最新的
        if type_str == "Full":
            for type_str in type_mapping.values():
                r.hset(f'sqe:{data["sqe"]}-{type_str}-{task.id}', 'status', 'queued')
                r.hset(f'latest_sqe:{data["sqe"]}-{type_str}', 'task_id', task.id)
                r.hset(f'latest_sqe:{data["sqe"]}-{type_str}', 'status', 'processing')
        else:
            r.hset(f'sqe:{data["sqe"]}-{type_str}-{task.id}', 'status', 'queued')
            r.hset(f'latest_sqe:{data["sqe"]}-{type_str}', 'task_id', task.id)
            r.hset(f'latest_sqe:{data["sqe"]}-{type_str}', 'filepath_raw', file_path)
            r.hset(f'latest_sqe:{data["sqe"]}-{type_str}', 'status', 'processing')
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
    # latest_sqe:1234-ER
    # latest_sqe:1234-HR
    # latest_sqe:1234-LR
    # latest_sqe:5678-ER
    # latest_sqe:9012-HR
    # 把集齊ER+HR+LR的紀錄，設定為uploaded，其他維持processing，以JSON回傳
    # 回傳JSON範例：
    # {
    #     "records": [
    #         {
    #             "sqe": 1234,
    #             "status": "uploaded",
    #             "text": "file_content"
    #         },
    #         {
    #             "sqe": 5678,
    #             "status": "processing",
    #             "text": "file_content"
    #         },
    #         {
    #             "sqe": 9012,
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
        sqe = key.split(":")[-1].split("-")[0]
        unique_sqe.add(sqe)
    records = []
    for sqe in unique_sqe:
        status = "processing"
        text = ""
        all_exist = True
        for type_str in ["ER", "HR", "LR"]:
            key = f'latest_sqe:{sqe}-{type_str}'
            if key not in unit_uploaded_keys:
                all_exist = False
                break
        if all_exist:
            status = "uploaded"
            for type_str in ["ER", "HR", "LR"]:
                key = f'latest_sqe:{sqe}-{type_str}'
                filepath = r.hget(key, 'filepath_polish')
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
            "sqe": sqe,
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
    sqe = data['sqe']
    entities = []
    base_ind = 0
    for type_str in ["ER", "HR", "LR"]:
        key = f'latest_sqe:{sqe}-{type_str}'
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
    sqe = data['sqe']
    entities = {}
    for type_str in ["ER", "HR", "LR"]:
        key = f'latest_sqe:{sqe}-{type_str}'
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
    #     "sqe": 1234
    # }

    # response應該是這樣的JSON：
    # {
    #     "is_confirmed": true
    # }

    # 掠過所有參數檢查，直接進行處理

    # 1. 如果pipe_result中不存在sqe_{sqe}_info.json，就建立新的（初始狀態）
    # 2. 讀取sqe_{sqe}_info.json，修改is_confirmed的值
    # 3. 寫回sqe_{sqe}_info.json
    is_confirmed = None
    if not os.path.exists(f'../data/pipe_result/sqe_{data["sqe"]}_info.json'):
        with open(f'../data/pipe_result/sqe_{data["sqe"]}_info.json', "w") as file:
            json.dump({"is_confirmed": None}, file)
    else:
        with open(f'../data/pipe_result/sqe_{data["sqe"]}_info.json', "r") as file:
            info = json.load(file)
        is_confirmed = info["is_confirmed"]
    
    # 如同上述的response範例
    response = {
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
    #     "sqe": 1234,
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
    if not os.path.exists(f'../data/pipe_result/sqe_{data["sqe"]}_info.json'):
        with open(f'../data/pipe_result/sqe_{data["sqe"]}_info.json', "w") as file:
            json.dump({"is_confirmed": data["is_confirmed"]}, file)
    else:
        with open(f'../data/pipe_result/sqe_{data["sqe"]}_info.json', "r") as file:
            info = json.load(file)
        info["is_confirmed"] = data["is_confirmed"]
        with open(f'../data/pipe_result/sqe_{data["sqe"]}_info.json', "w") as file:
            json.dump(info, file)
    
    # 如同上述的response範例
    response = {
        "is_confirmed": data['is_confirmed']
    }
    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=62593, debug=True, use_reloader=False)
