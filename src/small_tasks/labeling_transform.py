# labeling_transform.py

import sys
import os
import json
import time
from elasticsearch import Elasticsearch

# 透過Elasticsearch查詢ICD10CM資料
umls_client = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "jpDUH1dC"),
    verify_certs=False
)

# Elasticsearch查詢函數封裝
def get_icd10cm_form_elasticsearch(source, code):
    if source == "SNOMEDCT_US":
        index_route = "snomedct_us"
    elif source == "RXNORM":
        index_route = "rxnorm"
    elif source == "LNC":
        index_route = "lnc"
    else:        
        raise ValueError(f'LLM generated type: {source}, which is not supported (extract stage)')
    
    # get full row from UMLS
    query_body = {
        "query": {
            "bool": {
                "must": [
                    {
                        "match": {
                            "CODE": code
                        }
                    }
                ]
            }
        }
    }
    response = umls_client.search(index=index_route, body=query_body)
    if response['hits']['hits']:
        cui = response['hits']['hits'][0]['_source']['CUI']
        icd10cm_query_body = {
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
        icd10cm_response = umls_client.search(index="icd10cm", body=icd10cm_query_body)
        # check if icd10cm_response['hits']['hits'] is not empty
        if icd10cm_response['hits']['hits']:
            icd10_code_str = icd10cm_response['hits']['hits'][0]['_source']['CODE']
            icd10_code_name = icd10cm_response['hits']['hits'][0]['_source']['STR']
            return {
                "code": icd10_code_str,
                "name": icd10_code_name
            }
        else:
            return {
                "code": "N/A",
                "name": "N/A"
            }
    else:
        print(f"{Fore.RED}Answer not found for code ({code}) from {source}{Style.RESET_ALL}")
        return {
            "code": "N/A",
            "name": "N/A"
        }


# 1. 原始病歷：*.raw.txt
# 2. Polished結果：*.raw.polishing.txt
# 3. 分析結果：*.raw.polishing.llmExtract.txt
# ===== input example =====
# {
#     "entities": [
#         {
#             "source": "LNC",
#             "code": "2951-2",
#             "code_name": "Sodium [Moles/volume] in Serum or Plasma",
#             "text": "Sodium (Na)    : 141 mmol/L\n",
#             "icd10": {
#                 "code": "N/A",
#                 "name": "N/A"
#             },
#             "unique": 3,
#             "confidence": 1.0,
#             "count": 6
#         }
#     ]
# }
# ===== output example =====
# {
#     "entities": [
#         {
#             "source": "SNOMEDCT_US",
#             "code": "3006004",
#             "code_name": "Disturbance of consciousness (finding)",
#             "text": "Consciousness change since August 11,",
#             "icd10cm": {
#                 "code": "N/A",
#                 "name": "N/A"
#             },
#             "unique": 2,
#             "confidence": 0.6666666666666666,
#             "count": 3,
#             "correctness": true,
#             "insurance_related": false,
#             "remark": ""
#         }
#     ]
# }

input_folder_path = "../data/pipe_result/1001_full"
output_folder_path = "../data/pipe_result/1001_full_with_icd10cm"
output_folder_path_csv = "../data/pipe_result/1001_full_with_icd10cm_csv"

# 從input_folder_path中讀取分析完畢的結果JSON檔案，轉換為目標JSON格式後，輸出到output_folder_path
time_start = time.time()
time_seg_start = time.time()
handle_count_now = 0
max_handle_count = sys.maxsize
# max_handle_count = 1
# sort by file name
# for file_name in os.listdir(input_folder_path):
for file_name in sorted(os.listdir(input_folder_path)):
    if file_name.endswith(".llmExtract.txt"):
        with open(f"{input_folder_path}/{file_name}", "r") as file:
            llm_extract_json = json.load(file)
        
        reconstructed_result = {
            "entities": []
        }
        for entity in llm_extract_json["entities"]:
            icd10cm_result = get_icd10cm_form_elasticsearch(entity["source"], entity["code"])
            reconstructed_entity = {}
            reconstructed_entity["source"] = entity["source"]
            reconstructed_entity["code"] = entity["code"]
            reconstructed_entity["code_name"] = entity["code_name"]
            reconstructed_entity["text"] = entity["text"].replace("\n", "\\n")
            reconstructed_entity["icd10cm"] = icd10cm_result
            reconstructed_entity["unique"] = entity["unique"]
            reconstructed_entity["confidence"] = entity["confidence"]
            reconstructed_entity["count"] = entity["count"]
            reconstructed_entity["correctness"] = True
            reconstructed_entity["insurance_related"] = False
            reconstructed_entity["remark"] = "".replace("\n", "\\n")
            reconstructed_result["entities"].append(reconstructed_entity)
        
        with open(f"{output_folder_path}/{file_name}.json", "w") as file:
            json.dump(reconstructed_result, file, indent=4, ensure_ascii=False)
        with open(f"{output_folder_path_csv}/{file_name}.csv", "w") as file:
            # dict to csv
            # write header
            file.write("source,code,code_name,text,icd10cm_code,icd10cm_name,unique,confidence,count,correctness,insurance_related,remark\n")
            for entity in reconstructed_result["entities"]:
                file.write(f""""{entity['source']}","{entity['code']}","{entity['code_name']}","{entity['text']}","{entity['icd10cm']['code']}","{entity['icd10cm']['name']}",{entity['unique']},{entity['confidence']},{entity['count']},{entity['correctness']},{entity['insurance_related']},"{entity['remark']}"\n""")

        
        # print(file_name)
        handle_count_now += 1
        if handle_count_now % 100 == 0:
            print(f"{handle_count_now} files have been processed. ({time.time() - time_seg_start} seconds)")
            time_seg_start = time.time()
        if handle_count_now >= max_handle_count:
            break
        
print(f"Total {handle_count_now} files have been processed.")
print(f"Time used: {time.time() - time_start} seconds")