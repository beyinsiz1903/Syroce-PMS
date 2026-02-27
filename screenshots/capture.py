#!/usr/bin/env python3
"""
Capture App Store screenshots using Playwright directly.
"""
import asyncio
from playwright.async_api import async_playwright

BASE_URL = "https://locust-load-test.preview.emergentagent.com"
RAW_DIR = "/app/screenshots/raw"

async def login(page):
    await page.goto(f"{BASE_URL}/login")
    await page.wait_for_timeout(3000)
    await page.fill('input[type="email"], input[name="email"]', "demo@hotel.com")
    await page.fill('input[type="password"]', "demo123")
    await page.click('button[type="submit"]')
    await page.wait_for_timeout(5000)
    await page.wait_for_load_state("networkidle")

async def capture_iphone():
    """Capture iPhone screenshots at 428x926 viewport"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 428, "height": 926},
            device_scale_factor=3  # Retina
        )
        page = await context.new_page()

        # 1. Landing page
        await page.goto(BASE_URL)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/iphone_01_landing.png")
        print("iPhone: landing captured")

        # 2. Login page
        await page.goto(f"{BASE_URL}/login")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/iphone_02_login.png")
        print("iPhone: login captured")

        # 3. Login and Dashboard
        await login(page)
        await page.screenshot(path=f"{RAW_DIR}/iphone_03_dashboard.png")
        print("iPhone: dashboard captured")

        # 4. PMS
        await page.goto(f"{BASE_URL}/pms")
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"{RAW_DIR}/iphone_04_pms.png")
        print("iPhone: PMS captured")

        # 5. Reports
        await page.goto(f"{BASE_URL}/reports")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/iphone_05_reports.png")
        print("iPhone: reports captured")

        # 6. Settings
        await page.goto(f"{BASE_URL}/settings")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/iphone_06_settings.png")
        print("iPhone: settings captured")

        await browser.close()

async def capture_ipad():
    """Capture iPad screenshots at 1024x1366 viewport"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1024, "height": 1366},
            device_scale_factor=2  # Retina
        )
        page = await context.new_page()

        # 1. Landing page
        await page.goto(BASE_URL)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/ipad_01_landing.png")
        print("iPad: landing captured")

        # 2. Login page
        await page.goto(f"{BASE_URL}/login")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/ipad_02_login.png")
        print("iPad: login captured")

        # 3. Login and Dashboard
        await login(page)
        await page.screenshot(path=f"{RAW_DIR}/ipad_03_dashboard.png")
        print("iPad: dashboard captured")

        # 4. PMS
        await page.goto(f"{BASE_URL}/pms")
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"{RAW_DIR}/ipad_04_pms.png")
        print("iPad: PMS captured")

        # 5. Reports
        await page.goto(f"{BASE_URL}/reports")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/ipad_05_reports.png")
        print("iPad: reports captured")

        # 6. Settings
        await page.goto(f"{BASE_URL}/settings")
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{RAW_DIR}/ipad_06_settings.png")
        print("iPad: settings captured")

        await browser.close()

async def main():
    print("Capturing iPhone screenshots...")
    await capture_iphone()
    print("\nCapturing iPad screenshots...")
    await capture_ipad()
    print("\nAll captures done!")

asyncio.run(main())
