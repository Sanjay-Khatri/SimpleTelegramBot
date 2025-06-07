import requests
from bs4 import BeautifulSoup
import re

def fetch_product_info(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        if "amazon" in url:
            name = soup.select_one('#productTitle')
            price = soup.select_one('span.a-price-whole') or soup.select_one('.a-offscreen')
        elif "flipkart" in url:
            name = soup.select_one('span.B_NuCI')
            price = soup.select_one('div._30jeq3')
        elif "myntra" in url:
            name = soup.select_one('h1.pdp-title')
            price = soup.select_one('div.pdp-price span')
        elif "ajio" in url:
            name = soup.select_one('div.product-title h1')
            price = soup.select_one('div.product-price span.price')
        elif "tatacliq" in url:
            name = soup.select_one('h1.pdp-title')
            price = soup.select_one('div.price-section span.final-price')
        elif "croma" in url:
            name = soup.select_one('h1.prod-title')
            price = soup.select_one('span.new-price')

        product_name = name.get_text(strip=True) if name else "Unknown Product"
        price_text = price.get_text(strip=True) if price else "0"
        price_num = float(re.sub(r'[^\d.]', '', price_text))

        return product_name, price_num

    except Exception as e:
        print(f"Error fetching product info: {e}")
        return "Unknown Product", 0.0