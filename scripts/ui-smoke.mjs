import {chromium} from '@playwright/test';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:8000');
await page.getByLabel('Username',{exact:true}).fill('mariam');await page.getByLabel('Password',{exact:true}).fill(readFileSync('.local/demo-login.txt','utf8').match(/Password: (.+)/)[1]);
await page.getByRole('button',{name:'Sign in',exact:true}).click();
await page.getByRole('heading',{name:'Inventory overview',exact:true}).waitFor();
for(const name of ['Products','Batches','Movements','Expiry tracker','Alerts','Imports & exports','Audit log','Settings','Overview']){
 await page.locator('nav').getByRole('button',{name:name==='Alerts'?/^Alerts/:name,exact:name!=='Alerts'}).click();
 await page.getByRole('heading',{name:name==='Overview'?'Inventory overview':name,exact:true}).waitFor();
 await page.waitForTimeout(300);
}
await page.screenshot({path:'.local/screenshots/dashboard.png',fullPage:true});
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(350);
assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
await page.screenshot({path:'.local/screenshots/mobile-dashboard.png',fullPage:true});
await page.locator('.mobile-menu').click();await page.locator('nav').getByRole('button',{name:'Expiry tracker',exact:true}).click();
await page.getByLabel('Status filter').selectOption('expired');await page.waitForTimeout(500);
await page.screenshot({path:'.local/screenshots/mobile.png',fullPage:true});
assert.equal(errors.length,0,errors.join('\n'));
console.log('PASS: all nine navigation views, 390px mobile layout, mobile navigation, filters; zero browser exceptions.');
await browser.close();
