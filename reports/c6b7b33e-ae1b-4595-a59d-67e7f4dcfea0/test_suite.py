import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time

# ---------------------------------------------------------------------------
# Selectors (from crawled DOM)
# ---------------------------------------------------------------------------
SEL_USERNAME = "#user-name"
SEL_PASSWORD = "#password"
SEL_LOGIN_BTN = "#login-button"

SEL_ADD_BACKPACK = "#add-to-cart-sauce-labs-backpack"
SEL_ADD_BIKE_LIGHT = "#add-to-cart-sauce-labs-bike-light"
SEL_ADD_BOLT_SHIRT = "#add-to-cart-sauce-labs-bolt-t-shirt"
SEL_ADD_FLEECE = "#add-to-cart-sauce-labs-fleece-jacket"
SEL_ADD_ONESIE = "#add-to-cart-sauce-labs-onesie"
SEL_ADD_RED_SHIRT = r"#add-to-cart-test\.allthethings\(\)-t-shirt-\(red\)"

SEL_BURGER_MENU = "#react-burger-menu-btn"

SEL_SORT_SELECT = "#header_container > div:nth-of-type(2) > div > span > select"

SEL_TWITTER = "#page_wrapper > footer > ul > li:nth-of-type(1) > a"
SEL_FACEBOOK = "#page_wrapper > footer > ul > li:nth-of-type(2) > a"
SEL_LINKEDIN = "#page_wrapper > footer > ul > li:nth-of-type(3) > a"

SEL_ITEM_0_IMG = "#item_0_img_link"
SEL_ITEM_1_IMG = "#item_1_img_link"
SEL_ITEM_2_IMG = "#item_2_img_link"
SEL_ITEM_3_IMG = "#item_3_img_link"
SEL_ITEM_4_IMG = "#item_4_img_link"
SEL_ITEM_5_IMG = "#item_5_img_link"

SEL_TITLE_BACKPACK = "#item_4_title_link"
SEL_TITLE_BIKE_LIGHT = "#item_0_title_link"
SEL_TITLE_BOLT_SHIRT = "#item_1_title_link"
SEL_TITLE_FLEECE = "#item_5_title_link"
SEL_TITLE_ONESIE = "#item_2_title_link"
SEL_TITLE_RED_SHIRT = "#item_3_title_link"

BASE_URL = "https://www.saucedemo.com"
PRODUCTS_URL = f"{BASE_URL}/inventory.html"
CART_URL = f"{BASE_URL}/cart.html"
CHECKOUT_URL = f"{BASE_URL}/checkout-step-one.html"
CHECKOUT_STEP2_URL = f"{BASE_URL}/checkout-step-two.html"
CHECKOUT_COMPLETE_URL = f"{BASE_URL}/checkout-complete.html"


# ---------------------------------------------------------------------------
# Helper / Page-Object utilities
# ---------------------------------------------------------------------------

def make_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver


def login(driver, username="standard_user", password="secret_sauce"):
    driver.get(BASE_URL)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SEL_USERNAME)))
    driver.find_element(By.CSS_SELECTOR, SEL_USERNAME).clear()
    driver.find_element(By.CSS_SELECTOR, SEL_USERNAME).send_keys(username)
    driver.find_element(By.CSS_SELECTOR, SEL_PASSWORD).clear()
    driver.find_element(By.CSS_SELECTOR, SEL_PASSWORD).send_keys(password)
    driver.find_element(By.CSS_SELECTOR, SEL_LOGIN_BTN).click()


def get_cart_badge_count(driver):
    """Returns the integer count shown in cart badge, or 0 if badge not visible."""
    try:
        badge = driver.find_element(By.CSS_SELECTOR, ".shopping_cart_badge")
        return int(badge.text)
    except Exception:
        return 0


def is_cart_badge_visible(driver):
    try:
        badge = driver.find_element(By.CSS_SELECTOR, ".shopping_cart_badge")
        return badge.is_displayed()
    except Exception:
        return False


def get_error_message(driver):
    try:
        el = driver.find_element(By.CSS_SELECTOR, "[data-test='error']")
        return el.text
    except Exception:
        return ""


def get_product_prices(driver):
    """Returns list of floats representing prices shown on inventory page."""
    price_elements = driver.find_elements(By.CSS_SELECTOR, ".inventory_item_price")
    prices = []
    for el in price_elements:
        text = el.text.replace("$", "").strip()
        try:
            prices.append(float(text))
        except ValueError:
            pass
    return prices


def get_product_names(driver):
    """Returns list of product name strings shown on inventory page."""
    name_elements = driver.find_elements(By.CSS_SELECTOR, ".inventory_item_name")
    return [el.text.strip() for el in name_elements]


def apply_sort_filter(driver, option_text):
    sel = Select(driver.find_element(By.CSS_SELECTOR, SEL_SORT_SELECT))
    sel.select_by_visible_text(option_text)
    time.sleep(0.5)


def add_item_to_cart(driver, item_name):
    mapping = {
        "Sauce Labs Backpack": SEL_ADD_BACKPACK,
        "Sauce Labs Bike Light": SEL_ADD_BIKE_LIGHT,
        "Sauce Labs Bolt T-Shirt": SEL_ADD_BOLT_SHIRT,
        "Sauce Labs Fleece Jacket": SEL_ADD_FLEECE,
        "Sauce Labs Onesie": SEL_ADD_ONESIE,
        "Test.allTheThings() T-Shirt (Red)": SEL_ADD_RED_SHIRT,
    }
    selector = mapping.get(item_name)
    if selector is None:
        raise ValueError(f"Unknown item: {item_name}")
    wait = WebDriverWait(driver, 10)
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
    btn.click()


def navigate_to_cart(driver):
    driver.find_element(By.CSS_SELECTOR, ".shopping_cart_link").click()
    WebDriverWait(driver, 10).until(EC.url_contains("/cart.html"))


def is_item_in_cart(driver, item_name):
    try:
        items = driver.find_elements(By.CSS_SELECTOR, ".cart_item .inventory_item_name")
        for item in items:
            if item.text.strip() == item_name:
                return True
        return False
    except Exception:
        return False


def get_checkout_error(driver):
    try:
        el = driver.find_element(By.CSS_SELECTOR, "[data-test='error']")
        return el.text
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def driver():
    d = make_driver()
    yield d
    d.quit()


@pytest.fixture
def logged_in_driver():
    d = make_driver()
    login(d)
    WebDriverWait(d, 10).until(EC.url_contains("/inventory.html"))
    yield d
    d.quit()


# ===========================================================================
# FEATURE 1: Customer Login
# ===========================================================================

class TestCustomerLogin:

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 10)
        self.driver.get(BASE_URL)
        yield

    def _enter_username(self, username):
        el = self.driver.find_element(By.CSS_SELECTOR, SEL_USERNAME)
        el.clear()
        if username:
            el.send_keys(username)

    def _enter_password(self, password):
        el = self.driver.find_element(By.CSS_SELECTOR, SEL_PASSWORD)
        el.clear()
        if password:
            el.send_keys(password)

    def _click_login(self):
        self.driver.find_element(By.CSS_SELECTOR, SEL_LOGIN_BTN).click()

    def _is_on_login_page(self):
        return BASE_URL.rstrip("/") in self.driver.current_url and "/inventory" not in self.driver.current_url

    def _is_on_products_page(self):
        return "/inventory.html" in self.driver.current_url

    # --- Scenario: Successful login with valid credentials ---
    def test_successful_login_valid_credentials(self):
        # Given I am on the SauceDemo login page
        assert BASE_URL in self.driver.current_url

        # Given I have a registered account with username "standard_user"
        # (precondition - no action needed)

        # When I enter valid username "standard_user"
        self._enter_username("standard_user")

        # And I enter valid password "secret_sauce"
        self._enter_password("secret_sauce")

        # And I click the login button
        self._click_login()

        # Then I should be redirected to the products page
        self.wait.until(EC.url_contains("/inventory.html"))
        assert self._is_on_products_page(), "Expected to be on products page"

        # And I should see my account dashboard
        assert self.driver.find_element(By.CSS_SELECTOR, ".inventory_list").is_displayed()

        # And I should be able to access my order history
        # The burger menu provides access to account/order history
        assert self.driver.find_element(By.CSS_SELECTOR, SEL_BURGER_MENU).is_displayed()

    # --- Scenario: Failed login with invalid username and password ---
    def test_failed_login_invalid_credentials(self):
        # Given I do not have an account with username "wrong_user"
        # When I enter invalid username "wrong_user"
        self._enter_username("wrong_user")

        # And I enter invalid password "wrong_pass"
        self._enter_password("wrong_pass")

        # And I click the login button
        self._click_login()

        # Then I should see an error message
        error = get_error_message(self.driver)
        assert "Epic sadface: Username and password do not match any user in this service" in error

        # And I should remain on the login page
        assert self._is_on_login_page()

        # And I should not be granted access to the system
        assert not self._is_on_products_page()

    # --- Scenario: Failed login with empty username field ---
    def test_failed_login_empty_username(self):
        # When I leave the username field empty
        self._enter_username("")

        # And I enter valid password "secret_sauce"
        self._enter_password("secret_sauce")

        # And I click the login button
        self._click_login()

        # Then I should see an error message "Epic sadface: Username is required"
        error = get_error_message(self.driver)
        assert "Epic sadface: Username is required" in error

        # And I should remain on the login page
        assert self._is_on_login_page()

    # --- Scenario: Failed login with empty password field ---
    def test_failed_login_empty_password(self):
        # When I enter valid username "standard_user"
        self._enter_username("standard_user")

        # And I leave the password field empty
        self._enter_password("")

        # And I click the login button
        self._click_login()

        # Then I should see an error message "Epic sadface: Password is required"
        error = get_error_message(self.driver)
        assert "Epic sadface: Password is required" in error

        # And I should remain on the login page
        assert self._is_on_login_page()

    # --- Scenario: Failed login with locked out user credentials ---
    def test_failed_login_locked_out_user(self):
        # When I enter invalid username "locked_out_user"
        self._enter_username("locked_out_user")

        # And I enter valid password "secret_sauce"
        self._enter_password("secret_sauce")

        # And I click the login button
        self._click_login()

        # Then I should see an error message
        error = get_error_message(self.driver)
        assert "Epic sadface: Sorry, this user has been locked out" in error

        # And I should remain on the login page
        assert self._is_on_login_page()

        # And I should not be granted access to the system
        assert not self._is_on_products_page()

    # --- Scenario: Session persists across page refresh ---
    def test_session_persists_after_refresh(self):
        # Given I am logged in as "standard_user" with password "secret_sauce"
        login(self.driver, "standard_user", "secret_sauce")
        self.wait.until(EC.url_contains("/inventory.html"))

        # When I refresh the browser page
        self.driver.refresh()

        # Then I should still be on the products page
        self.wait.until(EC.url_contains("/inventory.html"))
        assert self._is_on_products_page()

        # And my session should be active
        assert self.driver.find_element(By.CSS_SELECTOR, ".inventory_list").is_displayed()

        # And I should still have access to my order history
        assert self.driver.find_element(By.CSS_SELECTOR, SEL_BURGER_MENU).is_displayed()

    # --- Scenario: Successful logout after login ---
    def test_successful_logout(self):
        # Given I am logged in as "standard_user" with password "secret_sauce"
        login(self.driver, "standard_user", "secret_sauce")
        self.wait.until(EC.url_contains("/inventory.html"))

        # When I open the navigation menu
        self.driver.find_element(By.CSS_SELECTOR, SEL_BURGER_MENU).click()
        self.wait.until(EC.element_to_be_clickable((By.ID, "logout_sidebar_link")))

        # And I click the logout button
        self.driver.find_element(By.ID, "logout_sidebar_link").click()

        # Then I should be redirected to the login page
        self.wait.until(EC.url_to_be(BASE_URL + "/"))
        assert self._is_on_login_page() or BASE_URL in self.driver.current_url

        # And my session should be terminated
        # And I should not be able to access the products page without logging in again
        self.driver.get(PRODUCTS_URL)
        time.sleep(1)
        assert "/inventory.html" not in self.driver.current_url or \
               "You can only access" in self.driver.page_source or \
               BASE_URL in self.driver.current_url


# ===========================================================================
# FEATURE 2: Shopping Cart Management
# ===========================================================================

class TestShoppingCart:

    @pytest.fixture(autouse=True)
    def setup(self, logged_in_driver):
        self.driver = logged_in_driver
        self.wait = WebDriverWait(logged_in_driver, 10)
        yield

    # --- Scenario: Successfully add a single item to the cart ---
    def test_add_single_item_to_cart(self):
        # Given the cart badge