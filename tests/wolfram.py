import os
import wolframalpha

api_key = os.environ.get('WOLFRAM_ID')
client = wolframalpha.Client(api_key)

question = "160cm in feet and inches"
# question = "black in spanish"
results = client.query(question)

# print(results)

if not results["@success"]:
    print("no results")

# Iterate through the first N results
n = 1

for result in [result for result in results.pods if result["@id"] == "Result"][:n]:

    print(type(result["subpod"]), len(result["subpod"]))
    if isinstance(result["subpod"], list):
        print("yeh")

    # print(result["subpod"]["plaintext"])

