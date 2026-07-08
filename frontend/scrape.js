const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('Navigating to elektraweb...');
  try {
    await page.goto('https://www.elektraweb.com/teklifapp/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    console.log('Page loaded. Waiting for 10 seconds to allow Angular to render...');
    await page.waitForTimeout(10000); 
    
    // Attempt to extract text
    const content = await page.evaluate(() => document.body.innerText);
    console.log('--- CONTENT START ---');
    console.log(content);
    console.log('--- CONTENT END ---');

  } catch (err) {
    console.error('Error during scraping:', err);
  } finally {
    await browser.close();
  }
})();
