# GetRaiditems.py - Pokémon Scarlet/Violet Raid Data Fetcher

## Current Status

### What's Working ✅
- **Reward Tables**: Successfully fetches fixed and lottery reward tables from RaidCrawler
- **Item Names**: Falls back to PokeAPI if the main itemnames source is unavailable
- **Pokémon Names**: Resolves species names from PokeAPI
- **Error Handling**: Clear messages about what's missing and why

### What's Blocking ❌
- **Encounter Data**: Cannot parse the binary FlatBuffer format (.bin files) that RaidCrawler uses
  - Files: `raid_enemy_0N_array.bin` (N = 1-6 for each star level)
  - Format: FlatBuffer binary protocol (requires C# schema definitions)

## Why This Matters

The script needs encounter data to map which Pokémon appear in which raids. Without it, we can't create the final output JSON that connects Pokémon to their raid rewards.

## Solutions

### Option 1: Use RaidCrawler Directly (RECOMMENDED)
The most reliable solution is to run RaidCrawler itself to export the data:

1. Clone the RaidCrawler repository:
   ```bash
   git clone https://github.com/LegoFigure11/RaidCrawler.git
   cd RaidCrawler
   ```

2. Run RaidCrawler (requires .NET runtime):
   ```bash
   # On Windows
   dotnet run --project RaidCrawler.WinForms
   
   # Or access the data programmatically through the C# code
   ```

3. The encounter data is embedded in the project - you would need to export it as JSON

### Option 2: Install FlatBuffers Support (Advanced)
If you want to parse the binary files directly:

```bash
pip install flatbuffers
```

Then you need to: 1. Obtain the FlatBuffer schema files (.fbs format) for RaidCrawler
2. Compile them to Python: `flatc --python schemas/*.fbs`
3. Modify `GetRaiditems.py` to use the generated Python code to parse the .bin files

This requires understanding FlatBuffer tools and C# schema definitions.

### Option 3: Wait for Community Data
Look for community projects that have already converted the RaidCrawler binary data to JSON format. Examples to check:
- Pokémon community data repositories on GitHub
- Data extraction projects that focus on SV game data
- Community wikis or data sites

### Option 4: Hybrid Approach
Run the script as-is to:
- Verify the reward tables are fetching correctly
- Check that item and Pokémon name resolution works
- Debug any other issues

Then manually obtain encounter data from another source and modify the script to load it.

## Running the Script

### With Encounter Data
Once you have encounter data in JSON format:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the script
python3 GetRaiditems.py
```

Expected output: `sv_raid_drops.json` containing all Pokémon raid drops

### Testing Current Functionality
Even without encounter data, test individual components:

```python
# Test reward table loading
from GetRaiditems import fetch_json, load_fixed_rewards, load_lottery_rewards

fixed = load_fixed_rewards("https://raw.githubusercontent.com/LegoFigure11/RaidCrawler/main/RaidCrawler.Core/Resources/Base/raid_fixed_reward_item_array.json")
lottery = load_lottery_rewards("https://raw.githubusercontent.com/LegoFigure11/RaidCrawler/main/RaidCrawler.Core/Resources/Base/raid_lottery_reward_item_array.json")

print(f"Fixed reward tables: {len(fixed)}")
print(f"Lottery reward tables: {len(lottery)}")
```

## Technical Details

### Data Sources
- **Reward Tables**: RaidCrawler GitHub (`Resources/Base/raid_*_reward_item_array.json`)
- **Item Names**: Community maintained or PokeAPI  
- **Pokémon Names**: PokeAPI (`pokeapi.co/api/v2/pokemon-species/{id}/`)
- **Encounter Tables**: RaidCrawler (`Resources/Base/raid_enemy_0N_array.bin`) - Binary format

### What Each File Contains
- `raid_fixed_reward_item_array.json`: Guaranteed drops for each reward table
- `raid_lottery_reward_item_array.json`: Random drops with probabilities
- `raid_enemy_0N_array.bin`: Which Pokémon appear in which raids (each star level)

## Contributing

If you find a source for encounter data in JSON format or develop a FlatBuffer parser for this, please contribute!

## Links
- RaidCrawler: https://github.com/LegoFigure11/RaidCrawler
- PokeAPI: https://pokeapi.co
- FlatBuffers: https://google.github.io/flatbuffers/
