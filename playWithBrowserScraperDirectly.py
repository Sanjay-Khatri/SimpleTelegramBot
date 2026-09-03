from browerScraper import price_getter

price_getter = price_getter("direct_client", headless=False)

price = price_getter.get_amazon_price("https://www.amazon.in/dp/B0H82V826Z")
print(price)

price = price_getter.get_flipkart_price(
    "https://www.flipkart.com/stride-up-stylish-comfortable-lightweight-sports-running-shoes-sneakers-men/p/itm70058b56758cf?pid=SHOHNVQDNTXG6EZV&lid=LSTSHOHNVQDNTXG6EZV3BISR3&marketplace=FLIPKART&store=osp%2Fcil%2F1cu&srno=b_1_5&otracker=browse&fm=organic&iid=a8e4465e-bd66-4a87-8053-266dc5677cd6.SHOHNVQDNTXG6EZV.SEARCH&ppt=browse&ppn=browse&ssid=pi9q7rseyo0000001788436155159&ov_redirect=true")
print(price)