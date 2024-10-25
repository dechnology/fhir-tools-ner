from elasticsearch import Elasticsearch
import json

client = Elasticsearch(
    "http://localhost:9200",
    basic_auth=("elastic", "jpDUH1dC"),
    verify_certs=False
)

# API key should have cluster monitor rights
client.info()

concept = "Sennosides 12.5 MG Oral Tablet"
search = {
    "Ingredient": [
        "Sennoside A",
        "Sennoside B"
    ],
    "Strength/Dose": [
        "12.5 mg/tablet"
    ],
    "Dosage_Form": [
        "Tablet"
    ],
    "Route_of_Administration": [
        "Oral"
    ],
    "Frequency_and_Duration": [
        "2 tablets at bedtime"
    ],
    "Brand_Name": [
        "Sennapur"
    ]
}

# 建立格式如下的查詢：
# {
#   "query": {
#     "bool": {
#       "should": [
#         {
#           "multi_match": {
#             "STR": "Sennosides 12.5 MG Oral Tablet"
#           }
#         },
#         {
#           "multi_match": {
#             "query": "Sennoside A",
#             "fields": ["STR"]
#           }
#         },
#         {
#           "multi_match": {
#             "query": "Sennoside B",
#             "fields": ["STR"]
#           }
#         },
#         {
#           "multi_match": {
#             "query": "12.5 mg/tablet",
#             "fields": ["STR"]
#           }
#         },
#         {
#           "multi_match": {
#             "query": "Tablet",
#             "fields": ["STR"]
#           }
#         },
#         {
#           "multi_match": {
#             "query": "Oral",
#             "fields": ["STR"]
#           }
#         },
#         {
#           "multi_match": {
#             "query": "2 tablets at bedtime",
#             "fields": ["STR"]
#           }
#         },
#         {
#           "multi_match": {
#             "query": "Sennapur",
#             "fields": ["STR"]
#           }
#         }
#       ],
#       "minimum_should_match": 1
#     }
#   },
#   "size": 10
# }
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
# 讓console能印出標準格式的json
print(json.dumps(query_body, indent=4))

# 执行查询
response = client.search(index="rxnorm", body=query_body)

# 讓console能印出標準格式的json，但是response是ObjectApiResponse，要先轉換為dict

print(json.dumps(response.raw, indent=4))