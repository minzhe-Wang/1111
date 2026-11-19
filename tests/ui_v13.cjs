const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE ? {executablePath:process.env.PLAYWRIGHT_EXECUTABLE} : {})});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const username='ui_'+Date.now();
 await page.request.post('http://127.0.0.1:8080/api/v1/register',{data:{username,password:'Testing2026'}});
 await page.goto('http://127.0.0.1:8080/');
 await page.locator('#loginForm [name=username]').fill(username);await page.locator('#loginForm [name=password]').fill('Testing2026');
 await page.locator('#loginForm button').click();await page.locator('#app').waitFor({state:'visible'});
 await page.locator('#entryForm [name=title]').fill('浏览器验收日程');await page.locator('#submitEntry').click();
 await page.getByRole('heading',{name:'浏览器验收日程',exact:true}).waitFor();
 // Verify selection visibility for vehicle and leave.
 await page.locator('#kindSeg [data-kind=vehicle]').click();
 if(await page.locator('#passengerWrap').isVisible())throw Error('Vehicle still asks for passengers');
 await page.locator('#kindSeg [data-kind=leave]').click();
 if(await page.locator('#entryForm [name=title]').isVisible())throw Error('Leave title not generated');
 await page.locator('#kindSeg [data-kind=schedule]').click();
 for(const width of [1440,1024,390]){
  await page.setViewportSize({width,height:1000});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  if(overflow) {
    console.log(await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().right]).slice(0,20)));
    await page.screenshot({path:'tests/v13-overflow.png',fullPage:true});
    throw Error('Horizontal overflow at '+width);
  }
  await page.screenshot({path:'tests/v13-ui-'+width+'.png',fullPage:true});
 }
 // Preserve fields on a real network failure.
 await page.locator('#entryForm [name=title]').fill('断网保留验收');
 await page.route('**/api/v1/records',route=>route.request().method()==='POST'?route.abort():route.continue());
 await page.locator('#submitEntry').click();await page.locator('#entryMsg').filter({hasText:'Failed'}).waitFor();
 if(await page.locator('#entryForm [name=title]').inputValue()!=='断网保留验收')throw Error('Lost form fields');
 await page.unroute('**/api/v1/records');
 await page.locator('#submitEntry').click();await page.getByRole('heading',{name:'断网保留验收',exact:true}).waitFor();
 // A successful HTTP response can still mean model failure; retain both input kinds.
 await page.locator('#chatForm [name=message]').fill('模型故障保留测试');
 await page.locator('#imageInput').setInputFiles({name:'demo.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l1kAAAAASUVORK5CYII=','base64')});
 await page.route('**/api/v1/agent/chat',route=>route.fulfill({json:{mode:'fallback',items:['模型测试故障'],context_available:true}}));
 await page.locator('#sendChat').click();await page.locator('.bubble').filter({hasText:'模型测试故障'}).waitFor();
 if(await page.locator('#chatForm [name=message]').inputValue()!=='模型故障保留测试')throw Error('Lost chat message on model failure');
 if(await page.locator('#imageInput').evaluate(el=>el.files.length)!==1)throw Error('Lost image on model failure');
 await page.unroute('**/api/v1/agent/chat');await page.locator('#imageInput').setInputFiles([]);
 // Real model and real persistence, edit and confirmation endpoints (small API charge).
 await page.setViewportSize({width:1024,height:1000});
 await page.locator('#chatForm [name=message]').fill('创建个人日程，标题浏览器草稿验收，2043年1月1日9点到10点。');
 await page.locator('#sendChat').click();
 try { await page.locator('.proposal').first().waitFor({timeout:40000}); }
 catch(error) { console.error(await page.locator('#chatLog').innerText());await browser.close();throw error; }
 const draft=page.locator('.proposal').last();
 await draft.locator('input').first().fill('浏览器修改后的草稿');
 if(!(await draft.getByRole('button',{name:'确认提交',exact:true}).isDisabled()))throw Error('Unreviewed edit confirm allowed');
 await draft.getByRole('button',{name:'保存修改',exact:true}).click();
 await draft.getByRole('button',{name:'确认提交',exact:true}).click();
 await page.getByRole('heading',{name:'浏览器修改后的草稿',exact:true}).waitFor();
 await page.locator('#logout').click();
 if(await page.locator('#chatLog').textContent())throw Error('Private chat survived sign-out');
 await page.locator('#loginForm button').click();await page.locator('#app').waitFor({state:'visible'});
 await page.goto('http://127.0.0.1:8080/mobile.html');await page.locator('#app').waitFor({state:'visible'});
 await page.goto('http://127.0.0.1:8080/admin.html');
 await page.locator('#loginForm button').click();await page.locator('#app').waitFor({state:'visible'});
 await page.locator('#nav [data-panel=vehicles]').click();await page.locator('#panel-vehicles form input').first().waitFor();
 if(await page.getByText('座位数',{exact:true}).count())throw Error('Legacy seats in admin');
 await page.screenshot({path:'tests/v13-admin.png',fullPage:true});
 if(errors.length)throw Error(errors.join('\n'));
 fs.writeFileSync('tests/v13-ui-result.json',JSON.stringify({date:new Date().toISOString(),passed:['login','schedule submission','vehicle without passengers','generated leave title','1440/1024/390 no horizontal overflow','network failure preserves input and retries','model failure preserves message and image','real model draft edit/confirm','sign-out clears private chat','mobile page','admin plate page'],pageErrors:errors},null,2));
 await browser.close();console.log('UI tests passed');
})().catch(e=>{console.error(e);process.exit(1)});
