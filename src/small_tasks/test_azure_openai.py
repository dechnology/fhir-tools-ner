# import requests

# # 設定端點與金鑰
# endpoint = "https://dhp.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"
# api_key = "＊＊＊＊＊"

# # 定義請求的資料
# headers = {
#     "Content-Type": "application/json",
#     "api-key": api_key,
# }
# data = {
#     "messages": [
#         {"role": "system", "content": "You are an AI assistant."},
#         {"role": "user", "content": "你好，幫我解決問題吧！"}
#     ],
#     "max_tokens": 100,
#     "temperature": 0.7,
# }

# # 發送請求
# response = requests.post(endpoint, headers=headers, json=data)

# # 檢視結果
# if response.status_code == 200:
#     print("回應內容:", response.json())
# else:
#     print("錯誤:", response.status_code, response.text)

import openai

client = openai.AzureOpenAI(
    api_key="＊＊＊＊＊",
    api_version="2024-08-01-preview",
    azure_endpoint="https://dhp.openai.azure.com"
    )

# 設定 Deployment Name（Azure OpenAI 不使用 model name，而是用 deployment name）
deployment_name = "gpt-4o"

# # 發送請求
# completion = client.chat.completions.create(
#     model=deployment_name,
#     messages=[
#         {"role": "system", "content": "你是一個 AI 助手。"},
#         {"role": "user", "content": "你好，幫我解決問題吧！"}
#     ],
#     max_tokens=100,
#     temperature=0.75,
# )

# # 輸出回應
# print(completion.choices[0].message.content)

segment = """Triage Information  
Triage Level: 3  
Computer Grading: 3  

Chief Complaint:   
Began since last night: Anuria, Shortness of Breath  

Determination Basis:   
Shortness of Breath, Mild Respiratory Distress (92-94% oxygen saturation)  

Past Medical History:   
- Outpatient: Chronic Obstructive Pulmonary Disease  
- Outpatient: Lung transplant  
- Hypertension  
- Outpatient: Aspergillosis  

TOCC (Travel, Occupation, Contact, Clustering):  
- Travel History: None  
- Clustering History: None  
- Special Occupation: None  
- Patient Contact: None  
- Animal Contact: None  

Vital Signs:BP (Blood Pressure): 133/72 mmHg  
PR (Pulse Rate): 80 beats per minute  
SpO2 (Oxygen Saturation): 96%  """

llm_extract_completion = client.chat.completions.create(
    model=deployment_name,

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

print(llm_extract_completion.choices[0].message.content)