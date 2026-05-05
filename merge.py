import json

with open("original_data.json", "r") as f:
    original = json.load(f)

with open("../albums_output_fixed.json", "r") as f:
    enriched = json.load(f)

# Create a lookup dictionary for enriched albums based on serie + tome
enriched_lookup = {}
for album in enriched:
    key = f"{album.get('serie', '').strip()}|{album.get('tome', '').strip()}"
    enriched_lookup[key] = album

# Merge logic: update original if found, else keep original
merged = []
updated_count = 0
added_count = 0

# Track what we've processed from original
processed_keys = set()

for album in original:
    key = f"{album.get('serie', '').strip()}|{album.get('tome', '').strip()}"
    processed_keys.add(key)
    if key in enriched_lookup:
        # Update with enriched data
        merged.append(enriched_lookup[key])
        updated_count += 1
    else:
        merged.append(album)

# Add any new albums that were in enriched but not in original
for album in enriched:
    key = f"{album.get('serie', '').strip()}|{album.get('tome', '').strip()}"
    if key not in processed_keys:
        merged.append(album)
        added_count += 1

with open("data.json", "w") as f:
    json.dump(merged, f, indent=4, ensure_ascii=False)

print(f"Original count: {len(original)}")
print(f"Enriched count: {len(enriched)}")
print(f"Updated in place: {updated_count}")
print(f"Added as new: {added_count}")
print(f"Total merged count: {len(merged)}")
