import {test,expect} from '@playwright/test'

test.beforeEach(async({page})=>{
 await page.goto('/')
 await page.getByLabel('Username',{exact:true}).fill(process.env.SWARM_TEST_USER||'reviewer')
 await page.getByLabel('Password',{exact:true}).fill(process.env.SWARM_TEST_PASSWORD||'review-only-password')
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.getByRole('heading',{name:'Cluster overview'})).toBeVisible()
})

test('real coordinator routes, enrollment and responsive navigation',async({page,isMobile})=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message))
 if(isMobile){
  await expect(page.locator('#main-sidebar')).toHaveAttribute('inert','')
  await page.getByRole('button',{name:'Open navigation'}).click()
  await expect(page.getByRole('button',{name:'Open navigation'})).toHaveAttribute('aria-expanded','true')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button',{name:'Open navigation'})).toBeFocused()
 }
 for(const [route,title] of [['/workers','Workers'],['/experiments','Experiments'],['/checkpoints','Checkpoints'],['/logs','Logs & events'],['/settings','Coordinator settings'],['/help','Setup & participation']]){
  await page.goto(route);await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible()
  expect(await page.locator('body').evaluate(e=>e.scrollWidth<=innerWidth)).toBe(true)
 }
 await page.goto('/workers');await page.getByRole('button',{name:'Add worker'}).click()
 await page.getByLabel('Owner username').fill('browser-test-owner')
 await page.getByRole('button',{name:'Generate code'}).click()
 await expect(page.locator('.pairing-code')).toBeVisible()
 await page.getByRole('button',{name:'Close enrollment'}).click()
 expect(errors).toEqual([])
})

test('invalid sign-in shows a recoverable error',async({page})=>{
 if(await page.getByRole('button',{name:'Open navigation'}).isVisible())await page.getByRole('button',{name:'Open navigation'}).click()
 await page.getByRole('button',{name:'Sign out'}).click()
 await page.getByLabel('Username',{exact:true}).fill('wrong-user')
 await page.getByLabel('Password',{exact:true}).fill('wrong-password')
 await page.getByRole('button',{name:'Sign in',exact:true}).click()
 await expect(page.getByRole('alert')).toContainText('invalid username or password')
})
