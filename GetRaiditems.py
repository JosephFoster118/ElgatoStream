"""
sv_raid_drops.py
 
Fetches Pokémon Scarlet/Violet tera raid reward tables from the RaidCrawler
community data and merges them with PokeAPI species names to produce a single
JSON file keyed by Pokémon name.
 
Sources:
  - Encounter tables (which Pokémon appear in which raids, and which reward
    tables they reference):
      RaidCrawler repo » raid_enemy_0N_array.json  (stars 1-6)
  - Fixed reward tables (guaranteed drops per table index):
      RaidCrawler repo » raid_fixed_reward_item_array.json
  - Lottery reward tables (random drop pool per table index):
      RaidCrawler repo » raid_lottery_reward_item_array.json
  - Item name strings:
      RaidCrawler repo » en/itemnames.json
  - Species name strings:
      PokeAPI  » https://pokeapi.co/api/v2/pokemon-species/{id}/
 
Output: sv_raid_drops.json
"""
 
import json
import time
import sys
import urllib.request
import urllib.error
from pathlib import Path
import io
 
# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
 
RAIDCRAWLER_BASE = (
    "https://raw.githubusercontent.com/LegoFigure11/"
    "RaidCrawler/main/RaidCrawler.Core/Resources/Base"
)

ENCOUNTER_FILES = [
    f"{RAIDCRAWLER_BASE}/raid_enemy_0{n}_array.bin" for n in range(1, 7)
]
FIXED_REWARDS_URL   = f"{RAIDCRAWLER_BASE}/raid_fixed_reward_item_array.json"
LOTTERY_REWARDS_URL = f"{RAIDCRAWLER_BASE}/raid_lottery_reward_item_array.json"
ITEM_NAMES_URL      = (
    "https://raw.githubusercontent.com/Koi-3088/sv-live-map/main/resources/en/itemnames.json"
)
 
OUTPUT_FILE = Path("sv_raid_drops.json")
 
# Delay between PokeAPI requests to stay well within rate limits
POKEAPI_DELAY = 0.3   # seconds
 
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
def fetch_json(url: str) -> object:
    """Download and parse JSON from a URL. Raises on HTTP errors."""
    req = urllib.request.Request(url, headers={"User-Agent": "sv-raid-drops/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())
 
 
def get_species_name(species_id: int, cache: dict) -> str:
    """
    Return the English name for a species ID, fetching from PokeAPI if needed.
    Falls back to "Species_{id}" if the lookup fails.
    """
    if species_id in cache:
        return cache[species_id]
 
    try:
        data = fetch_json(POKEAPI_SPECIES.format(id=species_id))
        for entry in data.get("names", []):
            if entry["language"]["name"] == "en":
                name = entry["name"]
                cache[species_id] = name
                time.sleep(POKEAPI_DELAY)
                return name
        # Fallback: use the name field at root level
        name = data.get("name", f"Species_{species_id}").title()
        cache[species_id] = name
        time.sleep(POKEAPI_DELAY)
        return name
    except Exception as e:
        print(f"  [warn] PokeAPI lookup failed for species {species_id}: {e}")
        fallback = f"Species_{species_id}"
        cache[species_id] = fallback
        return fallback
 
 
def resolve_item_name(item_id: int, item_names: list[str], item_cache: dict) -> str:
    """
    Map an item ID integer to its English name string.
    item_names is a list where index == item_id.
    item_id 0 means "no item" / experience candy type reward.
    Falls back to PokeAPI if item_names list is not available.
    """
    if item_id == 0:
        return "None"
    
    # Try to use cached item names first (if available)
    if item_id < len(item_names) and item_names[item_id]:
        name = item_names[item_id]
        return name if name else f"Item_{item_id}"
    
    # Fallback: try to fetch from cache or PokeAPI
    if item_id in item_cache:
        return item_cache[item_id]
    
    try:
        # Fetch from PokeAPI
        item_data = fetch_json(f"https://pokeapi.co/api/v2/item/{item_id}/")
        name = item_data.get("name", f"Item_{item_id}").replace("-", " ").title()
        item_cache[item_id] = name
        return name
    except:
        fallback = f"Item_{item_id}"
        item_cache[item_id] = fallback
        return fallback
 
 
# ---------------------------------------------------------------------------
# Step 1: Load reward tables
# ---------------------------------------------------------------------------
 
def load_fixed_rewards(url: str) -> dict[int, list[dict]]:
    """
    Returns a dict mapping table_index -> list of fixed reward slots.
    Each slot: {"item": str, "item_id": int, "count": int}
 
    Expected JSON shape (array of reward tables):
    [
      {
        "TableName": "...",
        "Items": [
          {"ItemID": 123, "Num": 1},
          ...
        ]
      },
      ...
    ]
    The position in the outer array IS the table index (dropTableFix).
    """
    print("Fetching fixed reward tables...")
    raw = fetch_json(url)
    tables = {}
    for idx, table in enumerate(raw):
        slots = []
        for slot in table.get("Items", []):
            item_id = slot.get("ItemID", 0)
            count   = slot.get("Num", 1)
            slots.append({"item_id": item_id, "count": count})
        tables[idx] = slots
    print(f"  Loaded {len(tables)} fixed reward tables.")
    return tables
 
 
def load_lottery_rewards(url: str) -> dict[int, list[dict]]:
    """
    Returns a dict mapping table_index -> list of lottery reward slots.
    Each slot: {"item_id": int, "count": int, "rate": int}
 
    Expected JSON shape:
    [
      {
        "TableName": "...",
        "Items": [
          {"ItemID": 456, "Num": 1, "RateValue": 50},
          ...
        ]
      },
      ...
    ]
    """
    print("Fetching lottery reward tables...")
    raw = fetch_json(url)
    tables = {}
    for idx, table in enumerate(raw):
        slots = []
        for slot in table.get("Items", []):
            item_id = slot.get("ItemID", 0)
            count   = slot.get("Num", 1)
            rate    = slot.get("RateValue", 0)
            slots.append({"item_id": item_id, "count": count, "rate": rate})
        tables[idx] = slots
    print(f"  Loaded {len(tables)} lottery reward tables.")
    return tables
 
 
# ---------------------------------------------------------------------------
# Step 2: Load encounter tables
# ---------------------------------------------------------------------------
 
def load_encounters(urls: list[str]) -> list[dict]:
    """
    Load all 6 star-level encounter files and return a flat list of encounter
    records.  Each record contains species ID, form, star rating, and the
    indices into the fixed/lottery reward tables.
 
    Expected JSON shape per file (array of encounter entries):
    [
      {
        "Species": 6,
        "Form": 0,
        "Stars": [3, 4],          # which star ratings this entry covers
        "dropTableFix": 12,       # index into fixed_reward_item_array
        "dropTableRandom": 7,     # index into lottery_reward_item_array
        ...
      },
      ...
    ]
    Star level is also inferred from filename (raid_enemy_0N_array → N stars).
    """
    encounters = []
    for star_num, url in enumerate(urls, start=1):
        print(f"Fetching encounter table for {star_num}★ raids...")
        try:
            # Try to fetch as JSON first (for compatibility), then as binary
            if url.endswith('.bin'):
                print(f"  [warn] Binary FlatBuffer format detected (.bin)")
                print(f"  [info] Skipping binary encounters - requires FlatBuffer schema")
                continue
            raw = fetch_json(url)
        except Exception as e:
            print(f"  [warn] Could not fetch {url}: {e}")
            continue
 
        for entry in raw:
            # The encounter block is often nested under a key like "Tokusei"
            # or directly at root. Handle both.
            enc = entry.get("RaidEnemyInfo", entry)
            species_id     = enc.get("BossPokeParam", {}).get("DevId", 0)
            form           = enc.get("BossPokeParam", {}).get("FormId", 0)
            drop_fix       = enc.get("dropTableFix", -1)
            drop_random    = enc.get("dropTableRandom", -1)
 
            # Some schemas use "DropTableFix" (capital D)
            if drop_fix == -1:
                drop_fix    = enc.get("DropTableFix", -1)
            if drop_random == -1:
                drop_random = enc.get("DropTableRandom", -1)
 
            if species_id == 0:
                continue  # empty / placeholder slot
 
            encounters.append({
                "species_id":   species_id,
                "form":         form,
                "stars":        star_num,
                "drop_fix":     drop_fix,
                "drop_random":  drop_random,
            })
 
    if not encounters:
        print(f"  [warn] No encounter entries loaded from JSON files.")
        print(f"  [info] Encounter files appear to be in binary FlatBuffer format.")
        print(f"  [info] Install 'flatbuffers' package and provide schema to load them.")
    else:
        print(f"  Loaded {len(encounters)} encounter entries total.")
    return encounters
 
 
# ---------------------------------------------------------------------------
# Step 3: Resolve item names into all reward entries
# ---------------------------------------------------------------------------
 
def resolve_rewards(tables: dict[int, list[dict]], item_names: list[str], item_cache: dict) -> dict[int, list[dict]]:
    """Replace numeric item_id fields with human-readable item names."""
    resolved = {}
    for idx, slots in tables.items():
        resolved[idx] = [
            {
                "item":    resolve_item_name(s["item_id"], item_names, item_cache),
                "item_id": s["item_id"],
                "count":   s["count"],
                **( {"rate": s["rate"]} if "rate" in s else {} ),
            }
            for s in slots
            if s["item_id"] != 0   # skip empty slots
        ]
    return resolved
 
 
# ---------------------------------------------------------------------------
# Step 4: Build per-Pokémon output
# ---------------------------------------------------------------------------
 
def build_pokemon_drops(
    encounters:      list[dict],
    fixed_tables:    dict[int, list[dict]],
    lottery_tables:  dict[int, list[dict]],
) -> dict[str, dict]:
    """
    Group encounters by species+form, collect all star ratings and the
    associated reward tables, and return a dict keyed by species_id.
 
    The final merge happens after species names are resolved.
    """
    grouped: dict[tuple, dict] = {}
 
    for enc in encounters:
        key = (enc["species_id"], enc["form"])
        if key not in grouped:
            grouped[key] = {
                "species_id": enc["species_id"],
                "form":       enc["form"],
                "raids":      [],
            }
 
        fix_items    = fixed_tables.get(enc["drop_fix"],    [])
        random_items = lottery_tables.get(enc["drop_random"], [])
 
        grouped[key]["raids"].append({
            "stars":          enc["stars"],
            "fixed_rewards":  fix_items,
            "random_rewards": random_items,
        })
 
    return grouped
 
 
# ---------------------------------------------------------------------------
# Step 5: Attach species names via PokeAPI
# ---------------------------------------------------------------------------
 
def attach_names(grouped: dict, species_cache: dict) -> dict[str, dict]:
    """
    Resolve every species_id to a name, then re-key the output dict by name.
    Forms get a suffix like "Raichu-Alola".
    """
    named: dict[str, dict] = {}
    total = len(grouped)
 
    for i, ((species_id, form), data) in enumerate(grouped.items(), start=1):
        sys.stdout.write(f"\r  Resolving species names... {i}/{total}  ")
        sys.stdout.flush()
        base_name = get_species_name(species_id, species_cache)
        key = base_name if form == 0 else f"{base_name}-{form}"
 
        # Deduplicate key if multiple form entries resolve to the same string
        if key in named:
            key = f"{key}-{species_id}"
 
        named[key] = {
            "species":    base_name,
            "species_id": species_id,
            "form":       form,
            "raids":      data["raids"],
        }
 
    print()  # newline after the progress indicator
    return named
 
 
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
 
def main():
    print("=" * 60)
    print("SV Tera Raid Drop Fetcher")
    print("=" * 60)
 
    # --- Load item names ---
    item_cache: dict[int, str] = {}
    print("\nFetching item name strings...")
    try:
        item_names: list[str] = fetch_json(ITEM_NAMES_URL)
        print(f"  Loaded {len(item_names)} item names from local source.")
    except Exception as e:
        print(f"  [warn] Could not load itemnames.json: {e}")
        print(f"  [info] Will fetch item names from PokeAPI as needed.")
        item_names = []
 
    # --- Load reward tables ---
    print()
    try:
        raw_fixed   = load_fixed_rewards(FIXED_REWARDS_URL)
        raw_lottery = load_lottery_rewards(LOTTERY_REWARDS_URL)
    except Exception as e:
        print(f"\n[fatal] Could not load reward tables: {e}")
        print("Make sure you have internet access and the RaidCrawler repo is reachable.")
        sys.exit(1)
 
    # Resolve item IDs to names
    print("\nResolving item names in reward tables...")
    print(f"  Using PokeAPI to fill in missing item names...")
    fixed_tables   = resolve_rewards(raw_fixed,   item_names, item_cache)
    lottery_tables = resolve_rewards(raw_lottery, item_names, item_cache)
    print(f"  Resolved {len(item_cache)} unique items.")
 
    # --- Load encounter tables ---
    print()
    encounters = load_encounters(ENCOUNTER_FILES)
    if not encounters:
        print("\n[error] Could not load encounter data (binary FlatBuffer format not supported)")
        print("\nTo fix this, you have these options:")
        print("  1. Use RaidCrawler's C# export functionality to generate JSON encounter files")
        print("  2. Find community-provided encounter JSON data")
        print("  3. Install FlatBuffers library: pip install flatbuffers")
        print("     Then provide the generated schema (RaidCrawler schema files needed)")
        print("\nWithout encounters, cannot map rewards to Pokémon.")
        print("Exiting.")
        sys.exit(1)
 
    # --- Build per-Pokémon drop data ---
    print("\nGrouping encounters by species...")
    grouped = build_pokemon_drops(encounters, fixed_tables, lottery_tables)
    print(f"  Found {len(grouped)} unique species+form combinations.")
 
    # --- Resolve species names ---
    print("\nResolving species names from PokeAPI (this may take a moment)...")
    species_cache: dict[int, str] = {}
    output = attach_names(grouped, species_cache)
 
    # Sort alphabetically for readability
    output = dict(sorted(output.items()))
 
    # --- Write output ---
    print(f"\nWriting {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
 
    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"  Done! {len(output)} Pokémon written ({size_kb:.1f} KB).")
    print(f"\nOutput: {OUTPUT_FILE.resolve()}")
    print("\nExample entry structure:")
    sample_key = next(iter(output))
    sample = output[sample_key]
    print(json.dumps({sample_key: {
        **sample,
        "raids": sample["raids"][:1]   # show just the first raid entry
    }}, indent=2))
 
 
if __name__ == "__main__":
    main()