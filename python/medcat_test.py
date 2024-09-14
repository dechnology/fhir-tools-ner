import sys
import time
start_time = time.time()
import json
from medcat.cat import CAT
import_time = time.time()
print(f"Libraries imported in {import_time - start_time:.2f} seconds.")

# Load the model pack
cat = CAT.load_model_pack('../model/umls_self_train_model_pt2ch_3760d588371755d0.zip')
model_loaded_time = time.time()
print(f"Model loaded in {model_loaded_time - import_time:.2f} seconds.")

# Open the input file to read the text
with open("../data/Testing EMR_v3plus_1.raw.standardized.txt", "r") as file:
    text = file.read()
    entities = cat.get_entities(text)
entities_extracted_time = time.time()
print(f"Entities extracted in {entities_extracted_time - model_loaded_time:.2f} seconds.")

# Save the entities to a JSON file
with open("../data/Testing EMR_v4_1_MedCAT.json", "w") as json_file:
    json.dump(entities, json_file, indent=2)
json_saved_time = time.time()
print(f"Entities have been saved to '../data/Testing EMR_v4_1_MedCAT.json' in {json_saved_time - entities_extracted_time:.2f} seconds.")

# accept user new text and display the analysis result (infinitive loop)
while True:
    print("Please enter a new text (press Ctrl+D to finish):")
    new_text = sys.stdin.read()
    new_entities = cat.get_entities(new_text)
    # print json format
    result = json.dumps(new_entities, indent=2)
    print(result)



# # To run unsupervised training over documents
# data_iterator = <your iterator>
# cat.train(data_iterator)
# #Once done, save the whole model_pack 
# cat.create_model_pack(<save path>)