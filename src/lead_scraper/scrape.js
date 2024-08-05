const { chromium } = require('playwright');
const createCsvWriter = require('csv-writer').createObjectCsvWriter;
const fs = require('fs');

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForSelector(page, selector, timeout = 30000, retries = 3) {
    for (let i = 0; i < retries; i++) {
        try {
            return await page.waitForSelector(selector, { timeout });
        } catch (error) {
            console.log(`Attempt ${i + 1} failed. Retrying...`);
            await sleep(2000 + Math.random() * 1000);
        }
    }
    throw new Error(`Selector ${selector} not found after ${retries} attempts`);
}

async function scrollAndLoadAllResults(page) {
    console.log('Scrolling through all results...');
    let isEndOfList = false;
    let lastResultCount = 0;
    let noNewElementsTimeout = false;

    while (!isEndOfList && !noNewElementsTimeout) {
        try {
            await page.evaluate(() => {
                const resultsDiv = document.querySelector('div[role="feed"]');
                if (resultsDiv) {
                    resultsDiv.scrollTo(0, resultsDiv.scrollHeight);
                } else {
                    throw new Error('Results div not found');
                }
            });
            await sleep(3000 + Math.random() * 2000); // Random delay between 3-5 seconds

            isEndOfList = await page.evaluate(() => {
                const endOfListText = document.querySelector('.HvlsQe span');
                return endOfListText && endOfListText.textContent.includes("You've reached the end of the list.");
            });

            const currentResultCount = await page.evaluate(() => {
                return document.querySelectorAll('.Nv2PK').length;
            });

            if (currentResultCount === lastResultCount) {
                noNewElementsTimeout = true;
            } else {
                lastResultCount = currentResultCount;
                noNewElementsTimeout = false;
            }

            if (isEndOfList) {
                console.log('Reached end of list.');
            }

            if (noNewElementsTimeout) {
                console.log('No new elements loaded, stopping scroll.');
            }
        } catch (error) {
            console.log('Error during scrolling:', error);
            break;
        }
    }

    console.log('Finished scrolling through all results.');
}

async function scrapeQuery(query) {
    const { niche, zone } = query;
    console.log(`Starting scrape for ${niche} in ${zone}...`);

    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const url = `https://www.google.com/maps/search/${niche}+${zone}/@${zone}&entry=ttu`;
    console.log(`Navigating to URL: ${url}`);

    try {
        await page.goto(url, { timeout: 60000 });

        try {
            await waitForSelector(page, 'button.VfPpkd-LgbsSe', 10000);
            console.log('Consent screen detected, clicking "Accept all"');
            await page.click('button.VfPpkd-LgbsSe');
            await sleep(2000 + Math.random() * 1000);
        } catch (e) {
            console.log('No consent screen detected.');
        }

        console.log('Waiting for results to load...');
        await waitForSelector(page, '.Nv2PK', 30000);

        await scrollAndLoadAllResults(page);

        const businessData = new Map();
        const results = await page.$$('.Nv2PK');

        console.log(`Found ${results.length} results in total.`);

        for (const result of results) {
            try {
                const name = await result.$eval('.qBF1Pd.fontHeadlineSmall', el => el.textContent.trim());
                console.log(`Processing business: ${name}`);

                let website = null;
                const websiteHandle = await result.$('a[href^="http"]');
                if (websiteHandle) {
                    const href = await websiteHandle.evaluate(el => el.href);
                    if (!href.includes('google.com')) {
                        website = href;
                    }
                }

                if (!website) {
                    console.log(`Website not found in main results, clicking on ${name} to find more details.`);
                    await result.click();
                    await sleep(2000 + Math.random() * 1000);

                    const websiteInDetails = await page.$('a.CsEnBe');
                    if (websiteInDetails) {
                        website = await websiteInDetails.evaluate(el => el.href);
                    }
                }

                if (name && website && !businessData.has(name)) {
                    businessData.set(name, website);
                    console.log(`Added: ${name} - ${website}`);
                } else {
                    console.log(`No website found for ${name}`);
                }

                const closeButton = await page.$('button[jsaction="pane.pageBack"]');
                if (closeButton) {
                    await closeButton.click();
                    await sleep(1000 + Math.random() * 500);
                }
            } catch (error) {
                console.log('Error extracting data from result:', error);
            }
        }

        await browser.close();
        console.log(`Scraping complete for ${niche} in ${zone}. Found ${businessData.size} businesses.`);
        return Array.from(businessData, ([name, website]) => ({ name, website }));
    } catch (error) {
        console.log(`Error scraping ${niche} in ${zone}:`, error);
        await browser.close();
        return [];
    }
}

async function scrapeGoogleMaps(queries) {
    const concurrencyLimit = 2; // Adjust this based on your risk tolerance
    const results = [];

    for (let i = 0; i < queries.length; i += concurrencyLimit) {
        const batch = queries.slice(i, i + concurrencyLimit);
        const batchResults = await Promise.all(batch.map(scrapeQuery));
        results.push(...batchResults.flat());

        // Add a delay between batches
        if (i + concurrencyLimit < queries.length) {
            await sleep(10000 + Math.random() * 5000);
        }
    }

    await saveToCsv(results, 'src/lead_scraper/business_leads.csv');
}

async function saveToCsv(data, filePath) {
    console.log(`Saving data to ${filePath}...`);

    const fileExists = fs.existsSync(filePath);

    const csvWriter = createCsvWriter({
        path: filePath,
        header: [
            { id: 'name', title: 'Name' },
            { id: 'website', title: 'Website' }
        ],
        append: fileExists
    });

    await csvWriter.writeRecords(data);
    console.log('Data saved to CSV successfully');
}

(async () => {
    try {
        const args = process.argv.slice(2);
        const queries = JSON.parse(args[0].replace(/'/g, '"'));
        console.log('Starting the lead scraping process...');

        await scrapeGoogleMaps(queries);

        console.log('Lead scraping process complete.');
    } catch (error) {
        console.error('An error occurred:', error);
    }
})();