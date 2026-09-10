import csv
import random

pincodes_path = 'data/full_pincodes.csv'
shelters_path = 'data/cyclone_shelters.csv'

shelters = []
try:
    with open(pincodes_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if random.random() < 0.005:
                if row.get('state') and row.get('district'):
                    place_name = row.get('place_name', 'Primary School')
                    shelters.append({
                        'name': f'Shelter {place_name}',
                        'state': row['state'],
                        'district': row['district'],
                        'lat': row['lat'],
                        'lon': row['lon'],
                        'capacity': random.randint(50, 1000),
                        'shelter_type': random.choice(['School', 'Community Hall', 'Cyclone Shelter', 'Government Building']),
                        'data_source': 'Synthetic Generation'
                    })

    with open(shelters_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'state', 'district', 'lat', 'lon', 'capacity', 'shelter_type', 'data_source'])
        writer.writeheader()
        writer.writerows(shelters)
    print(f'Generated {len(shelters)} synthetic shelters in {shelters_path}')
except Exception as e:
    print('Error:', e)
