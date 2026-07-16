# 已核实的公开来源快照（2026-07-16）

以下信息用于减少开发智能体再次搜索。正式集成前仍应读取仓库当前 README、LICENSE 和锁定 revision。

## 计算库

### 6tail/lunar-python

- 地址：https://github.com/6tail/lunar-python
- MIT；
- GitHub 页面说明支持公历、农历、干支、节气、八字、五行、十神等；
- 页面显示 2025-11-05 的 v1.4.8 release；
- 用作 Python 主 adapter 候选。

### 6tail/lunar-java

- 地址：https://github.com/6tail/lunar-java
- MIT；
- README 明确支持干支纪年按正月初一、立春当日、立春交接时刻，以及纪月按节当日或交接时刻；
- 可作为口径设计参考和跨语言复核，不要求项目采用 Java。

### sxtwl_cpp

- 地址：https://github.com/yuangu/sxtwl_cpp
- 寿星天文历 C++ 实现，提供 Python 绑定生态；
- 用作独立复核候选；
- 集成前必须核实许可证、安装方式和日期范围。

### Python zoneinfo

- 地址：https://docs.python.org/3/library/zoneinfo.html
- Python 3.9 起标准库 IANA 时区支持；
- 系统无时区数据时可使用第一方 `tzdata` 包。

## 数据集

### tellang/yeji-processed

- 地址：https://huggingface.co/datasets/tellang/yeji-processed
- 页面显示 MIT、27.7k viewer rows、25k train、2.77k validation；
- 仓库约 185 MB；
- 中韩混合，包含 bazi、tarot、astrology；
- 只能隔离筛选，不能整体导入。

### clinno/eightwords-241112

- 地址：https://huggingface.co/datasets/clinno/eightwords-241112
- 页面显示 Apache-2.0、JSON、1K–10K、4.55 MB、用于多轮微调；
- 来源说明不足，先隔离审核。

### czuo03/bazi-reasoning-300

- 地址：https://huggingface.co/datasets/czuo03/bazi-reasoning-300
- CC BY 4.0；327 条；928 kB；
- 数据卡说明由 DeepSeek-R1-0528 根据讲义和教材合成；
- 只能作为待验证合成轨迹。

### tellang/yeji-bazi-rules

- 地址：https://huggingface.co/datasets/tellang/yeji-bazi-rules
- MIT；页面 viewer 为 7 行，仓库约 1.02 MB；
- 文件树包含 `classics/sanming_tonghui.txt`、`classics/yuanhai_ziping.txt`、分析文档和 `rules/shensha_51.json`；
- 规则和文本版本必须再核验。

### BaziQA

- 地址：https://github.com/ChenJiangxi/BaziQA
- MIT；页面说明包含 2021–2025 Contest8 和 Celebrity50，总计 90 人、450 题；
- 含真实或匿名人物出生和事件信息；
- 仅评测。

### MingLi-Bench

- 地址：https://github.com/DestinyLinker/MingLi-Bench
- MIT；160 道标准化选择题，十二类主题，含预计算命盘；
- 仅评测。

## 古籍文本

### 维基文库《渊海子平》

- 地址：https://zh.wikisource.org/wiki/淵海子平
- 站点文本通常按 CC BY-SA 4.0；
- 页面存在来源/版本质量提示，必须保存 revision 和校勘状态。

### 维基文库《三命通会》

- 地址：https://zh.wikisource.org/wiki/三命通會
- 多卷可用；站点页面标示 CC BY-SA 4.0；
- 四库版本页面还会说明古籍公有领域状态；
- 必须保留版本、卷、章节和站点署名。
