# -*- coding: utf-8 -*-
"""JobsSelect 志愿页 -> FillInResume 推进（技能 playbook 第 1 步）。
Usage: python jobs_select_go.py <CtmID>
"""
import asyncio
import sys

from cdp import CDP


async def main():
    ctmid = sys.argv[1]
    async with CDP(f"CtmID={ctmid}") as c:
        pre = await c.js('''(()=>{
          const s=document.querySelector("select[name="grdJobs$ctl02$drpJobs"]");
          return s? s.options[s.selectedIndex].text : "no select";
        })()''')
        print("志愿1预填:", pre)
        await c.js('''(()=>{
          const s=document.querySelector("select[name="grdJobs$ctl02$drpJobs"]");
          s.dispatchEvent(new Event("change",{bubbles:true}));
          return "change dispatched";
        })()''')
        await asyncio.sleep(1)
        ok = await c.click_el("input[name=btnOk]", sleep_after=6)
        print("btnOk clicked:", ok)
        print("url:", await c.js("location.href.slice(0,110)"))


asyncio.run(main())
