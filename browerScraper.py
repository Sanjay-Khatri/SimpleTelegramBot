import threading
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlparse, parse_qs

class price_getter:

    def __init__(self, name=None, timeout_limit=50):
        self.lock = threading.Lock()

        # Playwright timeout is in milliseconds
        self.timeout_limit = timeout_limit * 1000

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        self.context = self.browser.new_context(
            viewport={
                "width": 1920,
                "height": 1080
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )

        self.context.set_default_timeout(self.timeout_limit)

        print(
            "PLAYWRIGHT HEADLESS BEGINS FOR...{}....Timeout={}".format(
                name,
                timeout_limit
            )
        )

    def destroy(self):
        print("Destroying Playwright browser...")

        try:
            self.context.close()
        except Exception:
            pass

        try:
            self.browser.close()
        except Exception:
            pass

        try:
            self.playwright.stop()
        except Exception:
            pass

    def __safe_goto(self, page, url):
        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout_limit
            )
            return True

        except PlaywrightTimeoutError:
            print("Navigation timeout:", url)
            return False

        except Exception as e:
            print("Navigation Error:", e)
            return False

    def __try_find_text(self, page, selector):
        try:
            locator = page.locator(selector).first

            if locator.count() == 0:
                return None

            text = locator.inner_text(
                timeout=self.timeout_limit
            )

            return text.replace("*", "").strip()

        except Exception:
            return None

    def __check_element_exists(self, page, selector):
        try:
            return page.locator(selector).count() > 0
        except Exception:
            return False

    def __clean_price(self, price_str):
        return (
            price_str
            .replace("\n", ".")
            .replace("₹", "")
            .replace(",", "")
            .strip()
        )

    def __clean_hmt_price(self, price_str):
        return (
            price_str
            .lower()
            .replace("\n", ".")
            .replace("mrp", "")
            .replace("₹", "")
            .replace(",", "")
            .strip()
        )

    # ---------------------------------------------------------
    # AMAZON
    # ---------------------------------------------------------

    def get_amazon_price(self, url, wait=False):

        with self.lock:

            page = self.context.new_page()

            try:

                if not self.__safe_goto(page, url):
                    return None, None

                title = self.__try_find_text(
                    page,
                    "#productTitle"
                )

                if not title:
                    return None, None

                price_selectors = [
                    "#priceblock_saleprice",
                    "#priceblock_dealprice",
                    "#priceblock_ourprice",
                    ".a-price.a-text-price.a-size-medium.apexPriceToPay",
                    ".a-price.aok-align-center.priceToPay",
                    ".a-price.aok-align-center.reinventPricePriceToPayMargin.priceToPay",
                    "[class*='priceToPay']",
                    "#soldByThirdParty",
                    "#price"
                ]

                for selector in price_selectors:

                    price = self.__try_find_text(
                        page,
                        selector
                    )

                    if price:
                        return title, self.__clean_price(price)

                if self.__check_element_exists(
                    page,
                    "text=Currently unavailable."
                ):
                    return title, "Currently Unavailable"

                print(
                    "AMAZON: FINALLY RETURNING...",
                    url
                )

                return title, "Currently Unavailable"

            except Exception as e:

                print(
                    "Amazon scraping error:",
                    e
                )

                return None, None

            finally:

                try:
                    page.close()
                except Exception:
                    pass

    # ---------------------------------------------------------
    # FLIPKART
    # ---------------------------------------------------------

    def get_flipkart_price(self, url, pid_from_url=None):

        with self.lock:

            page = self.context.new_page()

            try:

                if not pid_from_url:

                    print(
                        "GETTING FULL URL FROM BROWSER FOR :: ",
                        url
                    )

                    if not self.__safe_goto(page, url):
                        return None, None, None

                    current_url = page.url

                    print(
                        "EXPANDED FLIPKART URL ::",
                        current_url
                    )

                    pid_from_url = self.extract_pid_from_url(
                        current_url
                    )

                    print(
                        "PID :: ",
                        pid_from_url
                    )

                if not pid_from_url:
                    return None, None, None

                response = self.fetch_flipkart_price_api(
                    pid_from_url
                )

                print(
                    "FLIPKART API RESPONSE :: ",
                    response
                )

                if not response or response.get("error"):
                    return None, None, None

                title = response.get("title") or ""
                subtitle = response.get("subtitle") or ""

                product_name = (
                    f"{title} {subtitle}"
                    if subtitle
                    else title
                )

                if response.get("availability") is False:

                    return (
                        product_name,
                        "Out of Stock",
                        pid_from_url
                    )

                return (
                    product_name,
                    response.get("final_price"),
                    pid_from_url
                )

            except Exception as e:

                print(
                    "Flipkart scraping error:",
                    e
                )

                return None, None, None

            finally:

                try:
                    page.close()
                except Exception:
                    pass

    # ---------------------------------------------------------
    # MYNTRA
    # ---------------------------------------------------------

    def get_myntra_price(self, url):

        with self.lock:

            page = self.context.new_page()

            try:

                if not self.__safe_goto(page, url):
                    return None, None

                title_part1 = self.__try_find_text(
                    page,
                    "h1.pdp-title"
                )

                title_part2 = self.__try_find_text(
                    page,
                    "h1.pdp-name"
                )

                title = (
                    (title_part1 or "")
                    + " "
                    + (title_part2 or "")
                ).strip()

                if not title:
                    return None, None

                add_to_bag_selector = (
                    "div:has-text('ADD TO BAG')"
                )

                if not self.__check_element_exists(
                    page,
                    add_to_bag_selector
                ):
                    return title, "Out of Stock"

                price = self.__try_find_text(
                    page,
                    "span.pdp-price"
                )

                if price:
                    return (
                        title,
                        self.__clean_price(price)
                    )

                print(
                    "MYNTRA: FINALLY RETURNING...",
                    url
                )

                return title, None

            except Exception as e:

                print(
                    "Myntra scraping error:",
                    e
                )

                return None, None

            finally:

                try:
                    page.close()
                except Exception:
                    pass

    # ---------------------------------------------------------
    # HMT
    # ---------------------------------------------------------

    def get_hmt_price(self, url):

        with self.lock:

            page = self.context.new_page()

            try:

                if not self.__safe_goto(page, url):
                    return None, None

                title = self.__try_find_text(
                    page,
                    ".product-title"
                )

                if not title:
                    return None, None

                out_of_stock_selector = (
                    ".vote.text-danger"
                )

                if self.__check_element_exists(
                    page,
                    out_of_stock_selector
                ):
                    return title, "Out of Stock"

                price = self.__try_find_text(
                    page,
                    ".price.discountPrice"
                )

                if price:
                    return (
                        title,
                        self.__clean_hmt_price(price)
                    )

                print(
                    "HMT: FINALLY RETURNING...",
                    url
                )

                return title, None

            except Exception as e:

                print(
                    "HMT scraping error:",
                    e
                )

                return None, None

            finally:

                try:
                    page.close()
                except Exception:
                    pass

    # ---------------------------------------------------------
    # FLIPKART HELPERS
    # ---------------------------------------------------------

    def extract_pid_from_url(self, url: str):

        try:

            parsed_url = urlparse(url)

            query_params = parse_qs(
                parsed_url.query
            )

            return query_params.get(
                "pid",
                [None]
            )[0]

        except Exception:

            return None

    def fetch_flipkart_price_api(self, pid):

        url = (
            "https://2.rome.api.flipkart.com/"
            "api/4/page/fetch?cacheFirst=false"
        )

        headers = {
            "x-user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/143.0.0.0 Safari/537.36 "
                "FKUA/website/42/website/Desktop"
            ),
            "Content-Type": "application/json"
        }

        payload = {
            "pageUri": (
                "/a/p/b?pid="
                + pid
                + "&marketplace=FLIPKART"
            )
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            response.raise_for_status()

            return self.__extract_product_info(
                response.json()
            )

        except requests.exceptions.RequestException as e:

            print(
                "Flipkart API request failed:",
                e
            )

            return {
                "error": "Request Failed"
            }

    def __extract_product_info(
        self,
        response_json: dict
    ) -> dict:

        try:

            page_context = (
                response_json["RESPONSE"]
                ["pageData"]
                ["pageContext"]
            )

            product_info = {

                "product_id":
                    page_context.get("productId"),

                "title":
                    page_context
                    .get("titles", {})
                    .get("title"),

                "subtitle":
                    page_context
                    .get("titles", {})
                    .get("subtitle"),

                "brand":
                    page_context.get("brand"),

                "final_price":
                    str(
                        page_context
                        .get("pricing", {})
                        .get(
                            "finalPrice",
                            {}
                        )
                        .get("value")
                    ),

                "availability":
                    page_context
                    .get(
                        "trackingDataV2",
                        {}
                    )
                    .get("serviceable")
            }

            return product_info

        except (
            KeyError,
            TypeError
        ):

            return {
                "error":
                    "Invalid response structure"
            }
