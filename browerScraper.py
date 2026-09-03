import asyncio
import requests, re, json
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright


class price_getter:
    def __init__(self, name=None, timeout_limit=50000, headless=False):
        self.name = name
        self.timeout_limit = timeout_limit
        self.playwright = None
        self.browser = None
        self.lock = asyncio.Lock()
        self.headless = headless

    async def start(self):
        if self.browser:
            return
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        print(f"PLAYWRIGHT BEGINS FOR...{self.name}....Timeout={self.timeout_limit}.....HEADLESS={self.headless}")

    async def destroy(self):
        print("destroying browser....")
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    async def _new_page(self):
        if not self.browser:
            await self.start()
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        page.set_default_timeout(self.timeout_limit)
        return context, page

    async def _safe_goto(self, page, url):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_limit)
            return True
        except Exception as e:
            print("Navigation Error:", e)
            return False

    async def _try_find_text(self, page, selector):
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                return None
            text = await locator.inner_text(timeout=self.timeout_limit)
            return text.replace("*", "").strip()
        except Exception:
            return None

    async def _check_element_exists(self, page, selector):
        try:
            return await page.locator(selector).count() > 0
        except Exception:
            return False

    def _clean_price(self, price_str):
        return price_str.replace("\n", ".").replace("₹", "").replace(",", "").strip()

    def _clean_hmt_price(self, price_str):
        return price_str.lower().replace("\n", ".").replace("mrp", "").replace("₹", "").replace(",", "").strip()

    async def get_amazon_price(self, url, wait=False):
        async with self.lock:
            context, page = await self._new_page()
            try:
                if not await self._safe_goto(page, url):
                    return None, None

                title = await self._try_find_text(page, "#productTitle")
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
                    "#price",
                ]
                for selector in price_selectors:
                    price = await self._try_find_text(page, selector)
                    if price:
                        return title, self._clean_price(price)

                if await self._check_element_exists(page, "text=Currently unavailable."):
                    return title, "Currently Unavailable"

                print("AMAZON: FINALLY RETURNING...", url)
                return title, "Currently Unavailable"
            finally:
                await context.close()

    async def get_flipkart_price(self, url, pid_from_url=None):
        async with self.lock:
            context = None

            try:
                context, page = await self._new_page()
                print("GETTING FLIPKART PRODUCT ::", url)

                if not await self._safe_goto(page, url):
                    print("FLIPKART PAGE LOAD FAILED")
                    return None, None, None

                # Give React/Flipkart enough time to render the product section.
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

                await page.wait_for_timeout(2500)

                current_url = page.url

                if not pid_from_url:
                    pid_from_url = self.extract_pid_from_url(current_url)

                # ---------------------------------------------------------
                # TITLE
                # ---------------------------------------------------------
                title = None

                title_selectors = [
                    "h1",
                    '[class*="VU-ZEz"]',
                    '[class*="aA9eLq"]',
                ]

                for selector in title_selectors:
                    try:
                        locator = page.locator(selector).first

                        if await locator.count() and await locator.is_visible():
                            text = (await locator.inner_text()).strip()

                            if text and len(text) > 5:
                                title = text
                                break

                    except Exception as e:
                        print(f"FLIPKART TITLE ERROR :: {selector} :: {e}")

                # ---------------------------------------------------------
                # PRICE
                # ---------------------------------------------------------
                price = None

                # These are known/current Flipkart price patterns.
                # Keep the generic class matching because Flipkart changes
                # generated class names frequently.
                price_selectors = [
                    "div._30jeq3",
                    "div.Nx9bqj",
                    "div.CxhGGd",
                    '[class*="_30jeq3"]',
                    '[class*="Nx9bqj"]',
                    '[class*="CxhGGd"]',
                ]

                def parse_price(text):
                    """
                    Extract a rupee price from a small product-price element.
                    Avoid accepting obviously unrelated numbers.
                    """
                    if not text:
                        return None

                    text = " ".join(text.split())

                    # Normal Flipkart price format:
                    # ₹476
                    # ₹ 476
                    # ₹3,224
                    matches = re.findall(r"₹\s*([0-9][0-9,]*)", text)

                    for value in matches:
                        try:
                            value = int(value.replace(",", ""))

                            # Reject clearly invalid values.
                            if value >= 50:
                                return value

                        except (ValueError, TypeError):
                            continue

                    return None

                # ---------------------------------------------------------
                # 1. First try Flipkart's actual price elements
                # ---------------------------------------------------------
                for selector in price_selectors:
                    try:
                        locator = page.locator(selector)
                        count = await locator.count()

                        for i in range(count):
                            element = locator.nth(i)

                            try:
                                if not await element.is_visible():
                                    continue

                                text = (await element.inner_text()).strip()

                                if not text:
                                    continue

                                print(
                                    f"FLIPKART PRICE CANDIDATE :: "
                                    f"{selector} :: {text}"
                                )

                                candidate = parse_price(text)

                                if candidate is not None:
                                    price = candidate
                                    break

                            except Exception:
                                continue

                        if price is not None:
                            break

                    except Exception as e:
                        print(
                            f"FLIPKART PRICE SELECTOR ERROR :: "
                            f"{selector} :: {e}"
                        )

                # ---------------------------------------------------------
                # 2. Try JSON-LD structured product data
                # ---------------------------------------------------------
                #
                # Flipkart can expose:
                #
                # Product
                #   offers
                #      price
                #
                # This is much safer than scanning the entire body.
                # ---------------------------------------------------------
                if price is None:
                    try:
                        scripts = await page.locator(
                            'script[type="application/ld+json"]'
                        ).all_inner_texts()

                        for script_text in scripts:
                            try:
                                data = json.loads(script_text)

                                objects = (
                                    data
                                    if isinstance(data, list)
                                    else [data]
                                )

                                for obj in objects:
                                    if not isinstance(obj, dict):
                                        continue

                                    if obj.get("@type") != "Product":
                                        continue

                                    offers = obj.get("offers")

                                    if isinstance(offers, dict):
                                        raw_price = offers.get("price")

                                        if raw_price is not None:
                                            candidate = int(
                                                float(str(raw_price))
                                            )

                                            if candidate >= 50:
                                                price = candidate
                                                break

                                    elif isinstance(offers, list):
                                        for offer in offers:
                                            if not isinstance(offer, dict):
                                                continue

                                            raw_price = offer.get("price")

                                            if raw_price is None:
                                                continue

                                            candidate = int(
                                                float(str(raw_price))
                                            )

                                            if candidate >= 50:
                                                price = candidate
                                                break

                                    if price is not None:
                                        break

                            except Exception:
                                continue

                            if price is not None:
                                break

                    except Exception as e:
                        print(
                            "FLIPKART JSON-LD PRICE ERROR ::",
                            e
                        )

                # ---------------------------------------------------------
                # 3. Last-resort price extraction
                # ---------------------------------------------------------
                #
                # IMPORTANT:
                # Do NOT simply take the first ₹ value from body text.
                #
                # Flipkart pages can contain:
                #
                #   MRP
                #   selling price
                #   bank offer
                #   lowest price
                #   EMI
                #   related products
                #
                # So only use a tightly scoped product-area fallback.
                # ---------------------------------------------------------
                if price is None:
                    try:
                        # Look around the main product area first.
                        product_candidates = [
                            "main",
                            '[role="main"]',
                            'div[data-id]',
                        ]

                        for selector in product_candidates:
                            try:
                                locator = page.locator(selector).first

                                if not await locator.count():
                                    continue

                                if not await locator.is_visible():
                                    continue

                                text = await locator.inner_text()

                                # Get all prices from this section.
                                values = re.findall(
                                    r"₹\s*([0-9][0-9,]*)",
                                    text
                                )

                                parsed_values = []

                                for value in values:
                                    try:
                                        candidate = int(
                                            value.replace(",", "")
                                        )

                                        if candidate >= 50:
                                            parsed_values.append(candidate)

                                    except ValueError:
                                        continue

                                if parsed_values:
                                    # Usually the selling price is the
                                    # lowest of the first few product prices,
                                    # but don't blindly use the entire page.
                                    price = min(parsed_values[:5])
                                    break

                            except Exception:
                                continue

                    except Exception as e:
                        print(
                            "FLIPKART PRODUCT AREA PRICE ERROR ::",
                            e
                        )

                # ---------------------------------------------------------
                # AVAILABILITY
                # ---------------------------------------------------------
                #
                # DO NOT use:
                #
                #   "if 'out of stock' in body"
                #
                # because Flipkart can show that text for another
                # variant/section.
                # ---------------------------------------------------------
                availability = "UNKNOWN"

                try:
                    body_text = await page.locator("body").inner_text()
                    normalized = " ".join(body_text.lower().split())

                    # -----------------------------------------------------
                    # Strong positive signals
                    # -----------------------------------------------------
                    buy_now = page.get_by_text(
                        re.compile(r"^buy now$", re.I)
                    )

                    add_to_cart = page.get_by_text(
                        re.compile(r"^add to cart$", re.I)
                    )

                    buy_visible = False
                    cart_visible = False

                    try:
                        for i in range(await buy_now.count()):
                            if await buy_now.nth(i).is_visible():
                                buy_visible = True
                                break
                    except Exception:
                        pass

                    try:
                        for i in range(await add_to_cart.count()):
                            if await add_to_cart.nth(i).is_visible():
                                cart_visible = True
                                break
                    except Exception:
                        pass

                    if buy_visible or cart_visible:
                        availability = "IN_STOCK"

                    else:
                        # -------------------------------------------------
                        # Strong negative signals
                        # -------------------------------------------------
                        #
                        # Only inspect the product's main area rather than
                        # the whole page.
                        # -------------------------------------------------
                        product_text = normalized

                        try:
                            main_locator = page.locator(
                                'main, [role="main"]'
                            ).first

                            if await main_locator.count():
                                if await main_locator.is_visible():
                                    product_text = " ".join(
                                        (
                                            await main_locator.inner_text()
                                        ).lower().split()
                                    )
                        except Exception:
                            pass

                        out_of_stock_patterns = [
                            "currently out of stock",
                            "out of stock",
                            "sold out",
                        ]

                        if any(
                                pattern in product_text
                                for pattern in out_of_stock_patterns
                        ):
                            availability = "OUT_OF_STOCK"

                        # -------------------------------------------------
                        # No delivery / unavailable signals
                        # -------------------------------------------------
                        elif any(
                                pattern in product_text
                                for pattern in (
                                        "not deliverable",
                                        "currently unavailable",
                                )
                        ):
                            availability = "OUT_OF_STOCK"

                        # -------------------------------------------------
                        # If we have a valid product price but no explicit
                        # OOS message, treat it as available.
                        #
                        # This is useful because Flipkart sometimes renders
                        # the purchase buttons dynamically.
                        # -------------------------------------------------
                        elif price is not None:
                            availability = "IN_STOCK"

                except Exception as e:
                    print(
                        "FLIPKART AVAILABILITY ERROR ::",
                        e
                    )

                # ---------------------------------------------------------
                # DEBUG
                # ---------------------------------------------------------
                print(
                    f"FLIPKART TITLE :: {title}"
                )
                print(
                    f"FLIPKART PRICE :: {price}"
                )
                print(
                    f"FLIPKART AVAILABILITY :: {availability}"
                )
                print(
                    f"FLIPKART PID :: {pid_from_url}"
                )

                # ---------------------------------------------------------
                # RETURN
                # ---------------------------------------------------------
                if not title:
                    return None, None, pid_from_url

                if availability == "OUT_OF_STOCK":
                    return title, "Out of Stock", pid_from_url

                return (
                    title,
                    str(price) if price is not None else None,
                    pid_from_url,
                )

            except Exception as e:
                print(
                    "FLIPKART SCRAPING ERROR ::",
                    e
                )
                return None, None, pid_from_url

            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

    async def get_myntra_price(self, url):
        async with self.lock:
            context, page = await self._new_page()
            try:
                if not await self._safe_goto(page, url):
                    return None, None

                title_part1 = await self._try_find_text(page, "//h1[@class='pdp-title']")
                title_part2 = await self._try_find_text(page, "//h1[contains(@class, 'pdp-name')]")
                title = f"{title_part1 or ''} {title_part2 or ''}".strip()
                if not title:
                    return None, None

                if not await self._check_element_exists(page, "text=ADD TO BAG"):
                    return title, "Out of Stock"

                price = await self._try_find_text(page, "//span[@class='pdp-price']")
                if price:
                    return title, self._clean_price(price)

                print("MYNTRA: FINALLY RETURNING...", url)
                return title, None
            finally:
                await context.close()

    async def get_hmt_price(self, url):
        async with self.lock:
            context, page = await self._new_page()
            try:
                if not await self._safe_goto(page, url):
                    return None, None

                title = await self._try_find_text(page, ".product-title")
                if not title:
                    return None, None

                if await self._check_element_exists(page, ".vote.text-danger"):
                    return title, "Out of Stock"

                price = await self._try_find_text(page, ".price.discountPrice")
                if price:
                    return title, self._clean_hmt_price(price)

                print("HMT: FINALLY RETURNING...", url)
                return title, None
            finally:
                await context.close()

    def extract_pid_from_url(self, url: str):
        try:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            return query_params.get("pid", [None])[0]
        except Exception:
            return None

    def fetch_flipkart_price_api(self, pid):
        url = "https://2.rome.api.flipkart.com/api/4/page/fetch?cacheFirst=false"
        headers = {
            "x-user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 FKUA/website/42/website/Desktop",
            "Content-Type": "application/json",
        }
        payload = {"pageUri": "/a/p/b?pid=" + pid + "&marketplace=FLIPKART"}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            return self._extract_product_info(response.json())
        except requests.exceptions.RequestException:
            return {"error": "Request Failed"}

    def _extract_product_info(self, response_json: dict) -> dict:
        try:
            page_context = response_json["RESPONSE"]["pageData"]["pageContext"]
            return {
                "product_id": page_context.get("productId"),
                "title": page_context.get("titles", {}).get("title"),
                "subtitle": page_context.get("titles", {}).get("subtitle"),
                "brand": page_context.get("brand"),
                "final_price": str(page_context.get("pricing", {}).get("finalPrice", {}).get("value")),
                "availability": page_context.get("trackingDataV2", {}).get("serviceable"),
            }
        except (KeyError, TypeError):
            return {"error": "Invalid response structure"}
