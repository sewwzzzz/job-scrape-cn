# JobScrape-CN

## 目标

根据过滤条件，抓取国内知名招聘平台的岗位JD，存储到本地数据库，最后导出JSON/CSV。

## 需求拆解

1. 过滤条件：关键词、城市、薪资下限、工作年限、学历、hr活跃度、标题/日结岗位/公司黑名单

2. 目标平台：Boss直聘、猎聘

3. 最终数据

- 过滤条件提及字段

- 岗位URL

- 平台

## 难点（需研究）

1. 爬取岗位是否需要登录状态？

1) 实际调查：

- 未登陆状态下，在`BOSS`平台，我们无法根据过滤条件得到完整的有效信息，且会频繁出现登陆提示；在`猎聘`平台，我们可以得到有效信息。

2) 措施:

- 用户人工登录，登录完成后检测属于已登录状态，才进行爬取操作。BOSS的`Token.location=Cookie; key=__zp_stoken__`；猎聘的`Token.location=Cookie;key=XSRF-TOKEN`。


2. 如何处理招聘平台的反爬虫机制？

1) 实际调查:

- 抓取岗位信息，最直接的是采取`抓取DOM`的方式，但当打开浏览器开发者工具简单看DOM元素标签时，`BOSS`和`猎聘`的反爬虫机制都会直接关闭标签页。

- 无论是否在已登陆状态下进行查询频繁，都会弹出登录验证提示，中断爬取

2) 措施:

- 使用Playwright进行有头浏览器自动化，模拟正常用户的查询行为，绕过反爬虫机制，且需要额外加入反爬虫处理。

* navigator.webdriver = undefined(Browser)
* slow_mo(Browser)
* navigator.webdriver(Browser) + viewport=None(Context) 
* headless = false(Context)
* user_agent(Context)
* console方法打印对象时脱敏成`{}`
* 浏览器里原生函数调用 .toString() 返回的固定就是这种样子，比如 console.log.toString() → "function log() { [native code] }"（因为原生函数的源码 JS 读不到）。而手写的函数 .toString() 会返回真实源码。console方法改写后，console各方法`${name}`的`.toString()`需要伪装成`function ${name}{ [native code] }`,`.toString.toString()`伪装成`function toString{ [native code] }`

- 识别招聘平台的拦截形态，Boss滑块/登录页，猎聘登录页/风控拦截，不依赖易变选择器，选择URL作为识别依据，DOM元素选择器易变化。识别拦截页启用时机在进入页面后，执行任务前。

3. 如何处理招聘平台的查询结果可能含有不符合条件的数据的情况？



4. 在多次抓取过程中，如何处理重复岗位数据？



## 技术选型

1. 开发语言

- 选型：Python

2. 数据库

- 选型：SQLite
 
- 原因：轻量、数据库引擎和文件一体，单文件数据库

## 设计数据库表

### 实体



### 表结构

1. 岗位信息表

- 岗位URL

- 岗位标题

- 平台

- 公司

- 城市

- 地区

- 薪资

- 年限

- 学历

- hr名字

- hr活跃度

- hr头衔

- 搜索关键词

- 岗位卡片搜索时间

- 岗位JD

- 岗位JD抓取时间

- 抓取错误原因

- 抓取重试次数

- 拒绝岗位原因

- 拒绝时间


## 流程设计



### catch（打断正常流程的意外情况）



## 代码结构设计



## 测试


## 专有名词

1) 浏览器爬虫

- SSR CSR

- Chromium

- Playwright

- Browser -> Context -> Page 

- 浏览器内核

- UA/User-Agent

- navigator

    - userAgent

    - webdriver

    - plugins.length

    - languages

- 无头浏览器

- __zp_stoken__

- XSRF-TOKEN

2) Python

- with上下文管理器