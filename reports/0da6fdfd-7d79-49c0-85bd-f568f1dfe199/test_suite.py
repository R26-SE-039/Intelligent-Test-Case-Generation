import pytest
from playwright.sync_api import sync_playwright, Page, expect
import re


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_context_args():
    return {}


@pytest.fixture(scope="function")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        pg = context.new_page()
        yield pg
        context.close()
        browser.close()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

BASE_URL = "https://www.saucedemo.com"
INVENTORY_URL = f"{BASE_URL}/inventory.html"
CART_URL = f"{BASE_URL}/cart.html"


def do_login(page: Page, username: str = "standard_user", password: str = "secret_sauce"):
    page.goto(BASE_URL)
    page.fill("#user-name", username)
    page.fill("#password", password)
    page.click("#login-button")


def go_to_products(page: Page):
    page.goto(INVENTORY_URL)


def get_cart_badge(page: Page):
    return page.locator(".shopping_cart_badge")


def get_item_prices(page: Page):
    """Return list of float prices from inventory page."""
    prices = page.locator(".inventory_item_price").all_text_contents()
    return [float(p.replace("$", "").strip()) for p in prices]


def get_item_names(page: Page):
    """Return list of product names from inventory page."""
    names = page.locator(".inventory_item_name").all_text_contents()
    return [n.strip() for n in names]


# ---------------------------------------------------------------------------
# ============================================================
# Feature 1: Customer Login
# ============================================================
# ---------------------------------------------------------------------------

class TestCustomerLogin:

    def test_successful_login_with_valid_credentials(self, page: Page):
        """Scenario: Successful login with valid credentials"""
        # Given I am on the SauceDemo login page
        page.goto(BASE_URL)
        assert page.url == BASE_URL + "/"  or page.url == BASE_URL

        # Given I have a registered account with username "standard_user"
        # (precondition – no UI action needed)

        # When I enter valid username "standard_user"
        page.fill("#user-name", "standard_user")

        # And I enter valid password "secret_sauce"
        page.fill("#password", "secret_sauce")

        # And I click the login button
        page.click("#login-button")

        # Then I should be redirected to the products page
        expect(page).to_have_url(re.compile(r".*/inventory\.html"))

        # And I should see my account dashboard
        expect(page.locator(".inventory_container")).to_be_visible()

        # And I should be able to access my order history
        # (on SauceDemo "order history" is represented by the cart/menu; verify menu accessible)
        expect(page.locator("#react-burger-menu-btn")).to_be_visible()

    def test_failed_login_with_invalid_username_and_password(self, page: Page):
        """Scenario: Failed login with invalid username and password"""
        # Given I am on the SauceDemo login page
        page.goto(BASE_URL)

        # Given I do not have an account with username "wrong_user"
        # When I enter invalid username "wrong_user"
        page.fill("#user-name", "wrong_user")

        # And I enter invalid password "wrong_pass"
        page.fill("#password", "wrong_pass")

        # And I click the login button
        page.click("#login-button")

        # Then I should see an error message
        error_msg = "Epic sadface: Username and password do not match any user in this service"
        expect(page.locator("[data-test='error']")).to_contain_text(error_msg)

        # And I should remain on the login page
        assert BASE_URL in page.url and "inventory" not in page.url

        # And I should not be granted access to the system
        expect(page.locator("#user-name")).to_be_visible()

    def test_failed_login_with_empty_username_field(self, page: Page):
        """Scenario: Failed login with empty username field"""
        # Given I am on the SauceDemo login page
        page.goto(BASE_URL)

        # When I leave the username field empty
        page.fill("#user-name", "")

        # And I enter valid password "secret_sauce"
        page.fill("#password", "secret_sauce")

        # And I click the login button
        page.click("#login-button")

        # Then I should see an error message "Epic sadface: Username is required"
        expect(page.locator("[data-test='error']")).to_contain_text("Epic sadface: Username is required")

        # And I should remain on the login page
        assert "inventory" not in page.url

    def test_failed_login_with_empty_password_field(self, page: Page):
        """Scenario: Failed login with empty password field"""
        # Given I am on the SauceDemo login page
        page.goto(BASE_URL)

        # When I enter valid username "standard_user"
        page.fill("#user-name", "standard_user")

        # And I leave the password field empty
        page.fill("#password", "")

        # And I click the login button
        page.click("#login-button")

        # Then I should see an error message "Epic sadface: Password is required"
        expect(page.locator("[data-test='error']")).to_contain_text("Epic sadface: Password is required")

        # And I should remain on the login page
        assert "inventory" not in page.url

    def test_failed_login_with_locked_out_user(self, page: Page):
        """Scenario: Failed login with locked out user credentials"""
        # Given I am on the SauceDemo login page
        page.goto(BASE_URL)

        # When I enter invalid username "locked_out_user"
        page.fill("#user-name", "locked_out_user")

        # And I enter valid password "secret_sauce"
        page.fill("#password", "secret_sauce")

        # And I click the login button
        page.click("#login-button")

        # Then I should see an error message "Epic sadface: Sorry, this user has been locked out"
        expect(page.locator("[data-test='error']")).to_contain_text(
            "Epic sadface: Sorry, this user has been locked out"
        )

        # And I should remain on the login page
        assert "inventory" not in page.url

        # And I should not be granted access to the system
        expect(page.locator("#user-name")).to_be_visible()

    def test_session_persists_across_page_refresh(self, page: Page):
        """Scenario: Session persists across page refresh"""
        # Given I am logged in as "standard_user" with password "secret_sauce"
        do_login(page, "standard_user", "secret_sauce")
        expect(page).to_have_url(re.compile(r".*/inventory\.html"))

        # When I refresh the browser page
        page.reload()

        # Then I should still be on the products page
        expect(page).to_have_url(re.compile(r".*/inventory\.html"))

        # And my session should be active
        expect(page.locator(".inventory_container")).to_be_visible()

        # And I should still have access to my order history
        expect(page.locator("#react-burger-menu-btn")).to_be_visible()

    def test_successful_logout_after_login(self, page: Page):
        """Scenario: Successful logout after login"""
        # Given I am logged in as "standard_user" with password "secret_sauce"
        do_login(page, "standard_user", "secret_sauce")
        expect(page).to_have_url(re.compile(r".*/inventory\.html"))

        # When I open the navigation menu
        page.click("#react-burger-menu-btn")

        # And I click the logout button
        # TODO: selector for 'logout_link' not crawled yet – using sidebar link
        page.click("#logout_sidebar_link")

        # Then I should be redirected to the login page
        expect(page).to_have_url(re.compile(r".*saucedemo\.com/?$"))
        expect(page.locator("#login-button")).to_be_visible()

        # And my session should be terminated
        # Attempt to go to inventory without logging in
        page.goto(INVENTORY_URL)

        # And I should not be able to access the products page without logging in again
        expect(page).not_to_have_url(re.compile(r".*/inventory\.html"))


# ---------------------------------------------------------------------------
# ============================================================
# Feature 2: Shopping Cart Management
# ============================================================
# ---------------------------------------------------------------------------

class TestShoppingCartManagement:

    def _login_and_go_to_products(self, page: Page):
        do_login(page, "standard_user", "secret_sauce")
        expect(page).to_have_url(re.compile(r".*/inventory\.html"))

    def test_successfully_add_single_item_to_cart(self, page: Page):
        """Scenario: Successfully add a single item to the cart"""
        self._login_and_go_to_products(page)

        # Given the cart badge is not visible
        expect(get_cart_badge(page)).to_have_count(0)

        # When I click "Add to cart" on "Sauce Labs Backpack"
        page.click("#add-to-cart-sauce-labs-backpack")

        # Then the item "Sauce Labs Backpack" should appear in the cart
        page.goto(CART_URL)
        expect(page.locator(".cart_item")).to_contain_text("Sauce Labs Backpack")

        # And the cart badge should show "1"
        page.goto(INVENTORY_URL)
        expect(get_cart_badge(page)).to_have_text("1")

        # And the button label for "Sauce Labs Backpack" should change to "Remove"
        # TODO: selector for 'remove_sauce_labs_backpack' not crawled yet – using known ID pattern
        expect(page.locator("#remove-sauce-labs-backpack")).to_have_text("Remove")

    def test_successfully_add_multiple_items_to_cart(self, page: Page):
        """Scenario: Successfully add multiple items to the cart"""
        self._login_and_go_to_products(page)

        # Given the cart badge is not visible
        expect(get_cart_badge(page)).to_have_count(0)

        # When I click "Add to cart" on "Sauce Labs Backpack"
        page.click("#add-to-cart-sauce-labs-backpack")

        # And I click "Add to cart" on "Sauce Labs Bike Light"
        page.click("#add-to-cart-sauce-labs-bike-light")

        # And I click "Add to cart" on "Sauce Labs Bolt T-Shirt"
        page.click("#add-to-cart-sauce-labs-bolt-t-shirt")

        # Then the cart badge should show "3"
        expect(get_cart_badge(page)).to_have_text("3")

        # And all three items should appear in the cart
        page.goto(CART_URL)
        cart_items = page.locator(".cart_item").all_text_contents()
        assert any("Sauce Labs Backpack" in item for item in cart_items)
        assert any("Sauce Labs Bike Light" in item for item in cart_items)
        assert any("Sauce Labs Bolt T-Shirt" in item for item in cart_items)

    def test_cart_count_badge_updates_immediately(self, page: Page):
        """Scenario: Cart count badge updates immediately after adding an item"""
        self._login_and_go_to_products(page)

        # Given the cart badge is not visible
        expect(get_cart_badge(page)).to_have_count(0)

        # When I click "Add to cart" on "Sauce Labs Fleece Jacket"
        page.click("#add-to-cart-sauce-labs-fleece-jacket")

        # Then the cart badge should update immediately to "1"
        expect(get_cart_badge(page)).to_have_text("1")

        # And I should not need to refresh the page to see the updated count
        # (assertion already verified above without reload)

    def test_remove_item_from_cart_via_product_listing(self, page: Page):
        """Scenario: Remove an item from the cart via the product listing page"""
        self._login_and_go_to_products(page)

        # Given I have "Sauce Labs Backpack" in my cart
        page.click("#add-to-cart-sauce-labs-backpack")

        # And the cart badge shows "1"
        expect(get_cart_badge(page)).to_have_text("1")

        # When I click "Remove" on "Sauce Labs Backpack" from the products page
        # TODO: selector for 'remove_sauce_labs_backpack' not crawled yet – using known ID pattern
        page.click("#remove-sauce-labs-backpack")

        # Then the cart badge should not be visible
        expect(get_cart_badge(page)).to_have_count(0)

        # And the button label for "Sauce Labs Backpack" should change back to "Add to cart"
        expect(page.locator("#add-to-cart-sauce-labs-backpack")).to_have_text("Add to cart")

    def test_remove_item_from_cart_via_cart_page(self, page: Page):
        """Scenario: Remove an item from the cart via the cart page"""
        self._login_and_go_to_products(page)

        # Given I have "Sauce Labs Bike Light" in my cart
        page.click("#add-to-cart-sauce-labs-bike-light")

        # And the cart badge shows "1"
        expect(get_cart_badge(page)).to_have_text("1")

        # When I navigate to the cart page
        page.goto(CART_URL)

        # And I click "Remove" on "Sauce Labs Bike Light" in the cart
        # TODO: selector for 'remove_sauce_labs_bike_light_in_cart' not crawled yet – using known ID pattern
        page.click("#remove-sauce-labs-bike-light")

        # Then the cart should be empty
        expect(page.locator(".cart_item")).to_have_count(0)

        # And the cart badge should not be visible
        expect(get_cart_badge(page)).to_have_count(0)

    def test_add_item_without_login_redirects_to_login(self, page: Page):
        """Scenario: Attempt to add an item to the cart without being logged in"""
        # Given I am logged out of SauceDemo
        page.goto(BASE_URL)  # Ensure we're on a clean state

        # And I navigate to the products page URL directly
        page.goto(INVENTORY_URL)

        # Then I should be redirected to the login page
        expect(page).not_to_have_url(re.compile(r".*/inventory\.html"))
        expect(page.locator("#login-button")).to_be_visible()

        # And I should see the error message
        expect(page.locator("[data-test='error']")).to_contain_text(
            "You can only access '/inventory.html' when you are logged in."
        )

    def test_cart_persists_after_navigating_away_and_returning(self, page: Page):
        """Scenario: Cart persists after navigating away and returning"""
        self._login_and_go_to_products(page)

        # Given I have "Sauce Labs Backpack" in my cart
        page.click("#add-to-cart-sauce-labs-backpack")

        # And the cart badge shows "1"
        expect(get_cart_badge(page)).to_have_text("1")

        # When I navigate to a different page (product detail page)
        page.click("#item_4_img_link")
        expect(page).to_have_url(re.compile(r".*/inventory-item\.html"))

        # And I navigate back to the cart page