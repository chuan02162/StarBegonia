# 功能
1. 自动从各种平台获取账单/流水, 管理家庭的所有开销/收入/投资
2. 支持对不同平台的流水进行整合, 用可视化的方式展示 (每天/每周/每月/每季度/每年的收入支出结余总数, 以及每个平台的收入支出总数等等)
3. 支持根据数据源对账单进行组合, 方便使用者根据账单来源设定aa规则(哪些账单需要a, 每人a多少百分比)
4. 开放MCP供ai agent使用 (agent不在该项目范畴, agent将要实现的任务包括生成购物清单等, 供你参考如何实现mcp)
5. 有web ui进行展示

# 概念
1. 数据源 (source), 从coles/wws/kmart以及commbank获取, 也可以从csv导入, 手动输入, ocr识别发票等. 每个数据源下获取到的账单分成多个条目 (entry), 比如coles获取一次账单, 每个entry就是购买的不同商品(包括数量, 单价, 折扣, 名字等等). 从银行获取一次流水, 就只包含一个entry, 叫general(或者别的). 数据源做成接口, 每个平台做不同实现

# 技术栈
前端: React + tailwind + typescript
后端: Python + Flask + SQLAlchemy + sqlite
部署: Docker
MCP: fastmcp