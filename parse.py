import json
import re

with open('pipeline_output.json', 'r', encoding='utf-16le') as f:
    text = f.read()

json_str = text[text.find('{'):text.rfind('}')+1]
d = json.loads(json_str)

print('Pressure:', d['central_pressure_hpa'])
print('Confidence:', d['eye_confidence_label'], d['eye_confidence'])
print('Path:')
print(f' Center: {d["center_lat"]}, {d["center_lon"]}')
for t in d['forecast_timeline']:
    print(f' +{t["forecast_hour"]}h: {t["lat"]}, {t["lon"]}')
