"""Script to generate Markov sentences.

Generated sentences are stored in a JSON file with the keyword as the key.
"""

import json
from pathlib import Path

from tqdm import tqdm

from slashbot.markov import _generate_markov_sentence, load_markov_model

markov_file = Path("data/markov/markov-sentences.json")
if not markov_file.exists():
    with markov_file.open("w") as file_out:
        json.dump({}, file_out)
with markov_file.open("r") as file_in:
    markov_sentences = json.load(file_in)

num_sentences = 500
seed_words = ["weather", "forecast", "help", "error"]
print(f"Generating {num_sentences} sentences for seed words: {seed_words}")
model = load_markov_model("data/markov/chain.pickle")
for seed_word in seed_words:
    markov_sentences[seed_word] = [
        _generate_markov_sentence(model, seed_word) for _ in tqdm(range(num_sentences), desc=seed_word)
    ]
num_sentences = 10000
markov_sentences["?random"] = [
    _generate_markov_sentence(model, None) for _ in tqdm(range(num_sentences), desc="random sentences")
]

with markov_file.open("w") as file_out:
    json.dump(markov_sentences, file_out)
