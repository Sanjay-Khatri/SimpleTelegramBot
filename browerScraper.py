import threading
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By


class price_getter:

    def __init__(self, name=None, timeout_limit=50):
        self.lock = threading.Lock()
        options = ChromeOptions()
        # ✅ Enable headless mode
        options.add_argument("--headless=new")
        # Recommended flags for stability
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        # options.add_argument('--proxy-server=%s' % selected_proxy)
        # capabilities = options.to_capabilities()
        # capabilities['pageLoadStrategy'] = "eager"

        # Page load strategy
        options.page_load_strategy = "eager"

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(timeout_limit)
        # self.driver.maximize_window()
        print("HEADLESS BEGINS FOR...{}....Timeout={}".format(name, timeout_limit))

    def destroy(self):
        print("destroying browser....")
        self.driver.close()
        self.driver.quit()

    def __newTab(self):
        self.driver.execute_script("window.open()")
        for window in self.driver.window_handles[:-1]:
            self.driver.switch_to.window(window)
            self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[-1])

    def __safe_get(self, url):
        try:
            self.driver.get(url)
            return True
        except Exception as e:
            print("Navigation Error:", e)
            return False

    def __try_find_text(self, xpath):
        try:
            return self.driver.find_element(by=By.XPATH, value=xpath).text.replace("*", "").strip()
        except:
            return None

    def __check_element_exists(self, xpath):
        try:
            self.driver.find_element(by=By.XPATH, value=xpath)
            return True
        except:
            return False

    def __clean_price(self, price_str):
        return price_str.replace("\n", ".").replace("₹", "").replace(",", "").strip()

    def __clean_hmt_price(self, price_str):
        return price_str.lower().replace("\n", ".").replace("mrp", "").replace("₹", "").replace(",", "").strip()

    def get_amazon_price(self, url, wait=False):
        self.lock.acquire()
        try:
            if not self.__safe_get(url):
                self.__newTab()
                return None, None

            title = self.__try_find_text("//span[@id='productTitle']")
            if not title:
                self.__newTab()
                return None, None

            price_xpaths = [
                "//span[@id='priceblock_saleprice']",
                "//span[@id='priceblock_dealprice']",
                "//span[@id='priceblock_ourprice']",
                "//span[@class='a-price a-text-price a-size-medium apexPriceToPay']",
                "//span[@class='a-price aok-align-center priceToPay']",
                "//span[@class='a-price aok-align-center reinventPricePriceToPayMargin priceToPay']",
                "//span[contains(@class, 'priceToPay')]",
                "//div[@id='soldByThirdParty']",
                "//span[@id='price']"
            ]

            for xpath in price_xpaths:
                price = self.__try_find_text(xpath)
                if price:
                    return title, self.__clean_price(price)

            if self.__check_element_exists("//*[text()='Currently unavailable.']"):
                return title, "Currently Unavailable"

            print("AMAZON: FINALLY RETURNING...", url)
            return title, "Currently Unavailable"

        finally:
            self.__newTab()
            self.lock.release()

    def get_flipkart_price(self, url):
        self.lock.acquire()
        try:
            if not self.__safe_get(url):
                self.__newTab()
                return None, None

            title = self.__try_find_text("//h1[@class='_6EBuvT']")
            if not title:
                self.__newTab()
                return None, None

            out_of_stock_xpath = "//button[contains(@class, 'QqFHMw') and contains(@class, 'vslbG+') and contains(@class, 'In9uk2') and not(@disabled)]"
            if not self.__check_element_exists(out_of_stock_xpath):
                return title, "Out of Stock"

            price = self.__try_find_text("//div[@class='Nx9bqj CxhGGd']")
            if price:
                return title, self.__clean_price(price)

            print("FLIPKART: FINALLY RETURNING...", url)
            return title, None

        finally:
            self.__newTab()
            self.lock.release()

    def get_myntra_price(self, url):
        self.lock.acquire()
        try:
            if not self.__safe_get(url):
                self.__newTab()
                return None, None

            title_part1 = self.__try_find_text("//h1[@class='pdp-title']")
            title_part2 = self.__try_find_text("//h1[contains(@class, 'pdp-name')]")
            title = (title_part1 or "") + " " + (title_part2 or "")
            title = title.strip()

            if not title:
                self.__newTab()
                return None, None

            add_to_bag_xpath = "//div[contains(text(), 'ADD TO BAG')]"
            if not self.__check_element_exists(add_to_bag_xpath):
                return title, "Out of Stock"

            price = self.__try_find_text("//span[@class='pdp-price']")
            if price:
                return title, self.__clean_price(price)

            print("MYNTRA: FINALLY RETURNING...", url)
            return title, None

        finally:
            self.__newTab()
            self.lock.release()

    def get_hmt_price(self, url):
        self.lock.acquire()
        try:
            if not self.__safe_get(url):
                self.__newTab()
                return None, None

            title = self.__try_find_text("//*[@class='product-title']")

            if not title:
                self.__newTab()
                return None, None

            out_of_stock = "//*[@class='vote text-danger']"
            if self.__check_element_exists(out_of_stock):
                return title, "Out of Stock"

            price = self.__try_find_text("//*[@class='price discountPrice']")
            if price:
                return title, self.__clean_hmt_price(price)

            print("HMT: FINALLY RETURNING...", url)
            return title, None

        finally:
            self.__newTab()
            self.lock.release()


# p = price_getter()
# print(p.get_amazon_price("https://www.amazon.in/gp/aw/d/B0987BTSDV"))
# print(p.get_amazon_price("https://www.amazon.in/Wayona-Custom-100W-Charger-Cable/dp/B0F29DWD7T"))
# print(p.get_amazon_price("https://www.amazon.in/dp/B0CB83QY4L"))
#
# print(p.get_flipkart_price("https://www.flipkart.com/acedan-sneakers-women/p/itm6535e06627f77?pid=SHOHCFR5UGKUDJQF&lid=LSTSHOHCFR5UGKUDJQF4UB1DG&marketplace=FLIPKART&store=osp%2Fiko&srno=b_1_2&otracker=browse&fm=organic&iid=en_JLhM3VWMGQ1ZZA6ae1V6uCqjtnbzbO14cV3QzvMcsdhJYaMAkL6SvJGmKmM8W_LjzCaGfvMMatnr-8Uegvd8kA%3D%3D&ppt=hp&ppn=homepage&ssid=svikub416o0000001749441153034"))
# print(p.get_flipkart_price("https://www.flipkart.com/nothing-phone-3a/p/itm8150b2c810f5b?pid=MOBH8G3P6UXPEFSZ"))
# print(p.get_flipkart_price(("https://www.flipkart.com/leader-beast-26t-front-suspension-disc-brake-complete-accessories-26-t-inch-mountain-cycle/p/itm23f449164291b?pid=CCEGVZ9YFTAKRXMN&lid=LSTCCEGVZ9YFTAKRXMN900VVQ&marketplace=FLIPKART&store=abc%2Fulv%2Fixt%2Fi5v&srno=b_1_1&otracker=browse&fm=organic&iid=en_2XK2mGDOdRohDNgomAGmtdO4XDCAwCWN6uWgPIRAd6QHVSzY1evuSDIPvj_X_GjLD1oLBGa0aRVO5jrsG97O5PUFjCTyOHoHZs-Z5_PS_w0%3D&ppt=None&ppn=None&ssid=jon6n666cw0000001749441977312")))
#
# for myntra_url in ["https://www.myntra.com/socks/heelium/heelium-men-pack-of-3-blue-solid-anti-odour-ankle-length-socks/10598478/buy",
#             "https://www.myntra.com/sunglasses/skechers/skechers-men-blue-rectangle-sunglasses-se6035-58-91x/10216815/buy",
#             "https://www.myntra.com/sports-accessories/kookaburra/kookaburra-men-white-rh-blaze-100-batting-leg-guards/7157062/buy",
#             "https://www.myntra.com/accessory-gift-set/evoq/evoq-men-rust--beige-cuff-bands/16167784/buy",
#             "https://www.myntra.com/10841992"
#         ]:
#     print(p.get_myntra_price(myntra_url))