from pathlib import Path

import requests
from bs4 import BeautifulSoup

url = "https://www.tunisianet.com.tn/recherche?controller=search&orderby=position&orderway=desc&s=rtx+5060&submit_search="

headers = {"User-Agent": "Mozilla/5.0"}

r = requests.get(url, headers=headers, timeout=20)
print("Status code:", r.status_code)

output_file = Path(__file__).parent / "tunisianet_rtx5060.html"

with open(output_file, "w", encoding="utf-8") as f:
    f.write(r.text)

print("Saved to:", output_file)
