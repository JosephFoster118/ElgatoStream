import requests
import json

query = """
{
  pokemon_v2_pokemon {
    id name
    pokemon_v2_pokemontypes { pokemon_v2_type { name } }
    pokemon_v2_pokemonstats { base_stat pokemon_v2_stat { name } }
  }
}
"""
result_file_path = "resources/pokemon_stats.json"

r = requests.post("https://beta.pokeapi.co/graphql/v1beta", json={"query": query})
data = r.json()

#Grab data.pokemon_v2_pokemon from json response
data = data["data"]["pokemon_v2_pokemon"]

#Convert dictionary key pokemon_v2_pokemontypes to "types" and pokemon_v2_pokemonstats to "stats"
for pokemon in data:
    pokemon["types"] = [t["pokemon_v2_type"]["name"] for t in pokemon.pop("pokemon_v2_pokemontypes")]
    pokemon["stats"] = {s["pokemon_v2_stat"]["name"]: s["base_stat"] for s in pokemon.pop("pokemon_v2_pokemonstats")}


#Save the data to a JSON file

with open(result_file_path, "w") as f:
    json.dump(data, f, indent=4)
