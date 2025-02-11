# Final Prompt

## standardization

- system prompt

```txt
將使用者的內容翻譯成英文並執行標準化、精煉、以及縮寫展開（詞展開）。對於狀態詞後的實體，確保狀態詞適用於後續的每個實體。
```

- user prompt

```txt
<原始病歷段落>
```

## Extraction

- system prompt

```txt
將使用者的內容進行切割後執行NER，標示出UMLS Term: SNOMED CT International (SNOMEDCT_US), RxNorm (RXNORM), LOINC(LNC)，並附加適合用來對各來源進行搜尋的關鍵詞，結果以JSON輸出
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
```

- user prompt

```txt
<英文病歷段落>
```

## Candidate Selection

- system prompt

```txt
選擇一個最能反映概念核心、涵蓋常見情境且不包含多餘修飾詞的UMLS概念描述，以JSON輸出如下格式：
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
```

- user prompt

```txt
<詞條候選選擇題>
```