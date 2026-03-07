# AI产业链领域地图 v2.0

> 用途：评分时的领域识别参考。scorer.py 按层 grep，不全量加载。
> 关键词搜索：LAYER0 / LAYER1 / LAYER2 / LAYER3 / LAYER4 / LAYER5 / GEO

---

## LAYER0 · 能源与基础设施

**核心问题**：AI数据中心的电从哪来？

关键词：
`核电` `SMR小型模块堆` `太阳能` `风能` `储能` `超导输电` `UPS` `电网扩容`
`MW兆瓦` `GW吉瓦` `PPA电力采购协议` `数据中心供电合同` `碳排放` `电力短缺`

代表公司/机构：
Constellation Energy / Vistra / Oklo / Southern Company / NextEra Energy
国家电网 / 华能 / 大唐

触发加权信号：
- "数据中心 + 电力/能源" → market_impact +1
- "核电 + AI/科技公司" → market_impact +1
- "PPA协议签订" → information_edge +1

---

## LAYER1 · 芯片与硬件

**核心问题**：算力由谁制造？

关键词：
`GPU` `H100` `H200` `B200` `GB300` `Blackwell` `Rubin`
`NPU` `TPU` `ASIC` `HBM内存` `HBM3` `HBM4` `CoWoS封装`
`纳米制程` `2nm` `3nm` `晶圆产能` `出口管制` `堆叠封装`
`Chiplet` `互连` `带宽`

代表公司：
Nvidia / AMD / Intel / TSMC台积电 / SK Hynix / Samsung
Broadcom / Marvell / Qualcomm / 寒武纪 / 海思 / 壁仞

触发加权信号：
- "出口管制 + 芯片/GPU" → market_impact +1，geopolitical加权触发
- "TSMC产能/涨价" → market_impact +1
- "新架构发布（Blackwell/Rubin等）" → information_edge +1

---

## LAYER2 · 算力网络与数据中心

**核心问题**：算力如何组织和传输？

关键词：
`数据中心` `超算中心` `Infiniband` `以太网AI组网` `光互连` `液冷`
`RDMA` `400G` `800G网络` `PUE能效` `CoreWeave` `Lambda Labs`
`微软Azure AI` `Google Cloud TPU` `AWS Trainium`

触发加权信号：
- "数据中心 + 新建/扩容/投资金额" → market_impact +1
- "云厂商资本开支" → market_impact +1

---

## LAYER3 · 基础模型层

**核心问题**：模型从哪来？训练成本多少？

关键词：
`预训练` `RLHF` `MoE架构` `Transformer` `扩展法则` `推理优化`
`Context窗口` `参数量` `训练成本` `评测基准` `MMLU` `ARC` `MATH`
`多模态` `视频生成` `代码生成` `Agent框架`

代表机构：
OpenAI / Anthropic / Google DeepMind / Meta AI / Mistral
月之暗面Kimi / 智谱GLM / DeepSeek / 百川 / MiniMax

触发加权信号：
- "新模型发布 + 性能提升/成本降低" → information_edge +1
- "训练成本对比（同比大幅下降）" → market_impact +1，causal_depth +1
- "GPT-5/Claude-4等旗舰发布" → market_impact 直接4分

---

## LAYER4 · 平台与工具链

**核心问题**：开发者用什么工具？

关键词：
`MLOps` `推理框架` `vLLM` `TensorRT` `向量数据库` `Fine-tuning`
`Hugging Face` `Weights & Biases` `Pinecone` `LangChain`
`API成本` `token价格` `并发性能` `开源模型`

触发加权信号：
- "API价格大幅下降" → market_impact +1（影响AI应用层成本结构）
- "开源模型接近闭源SOTA" → information_edge +1

---

## LAYER5 · AI应用与场景

**核心问题**：AI在哪里赚钱？

关键词：
`AI Agent` `RAG` `代码生成` `Copilot` `医疗AI` `法律AI`
`教育AI` `金融AI` `AI Native产品` `workflow自动化` `多模态应用`
`MAU` `ARR` `替代率` `ROI` `企业AI采购` `AI+机器人`

触发加权信号：
- "企业级AI采购/部署规模" → market_impact +1
- "AI产品月活/收入里程碑" → information_edge +1

---

## GEO · 地缘政治联动图

> 凡出现以下触发词，market_impact 自动+1（上限4分）

### 中美科技脱钩链
触发词：`芯片禁令` `出口管制` `实体清单` `瓦森纳协议` `中美脱钩` `台湾` `台海`
联动资产：TSMC / Nvidia / ASML / 中芯国际 / 海光信息 / 华为

### 中东能源链
触发词：`伊朗` `以色列` `霍尔木兹海峡` `OPEC` `沙特` `也门胡塞`
联动资产：原油(WTI/Brent) / 天然气 / 能源股 / 航空股 / 通胀预期

### 俄乌欧洲能源链
触发词：`俄罗斯` `乌克兰` `北溪` `欧洲能源` `天然气价格`
联动资产：欧洲能源股 / 欧元 / 欧洲工业股

### 稀土/关键矿产链
触发词：`稀土` `锂` `钴` `稀有金属` `矿产出口限制`
联动资产：稀土ETF / 新能源车产业链 / 电池股

### 关税/贸易战链
触发词：`关税` `贸易战` `报复性关税` `贸易协定`
联动资产：出口导向型股票 / 美元 / 新兴市场ETF
