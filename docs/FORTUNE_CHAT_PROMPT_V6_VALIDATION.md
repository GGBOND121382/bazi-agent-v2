# 八字问答 Prompt v6 优化与 12 命造验证报告

## 总体结论

- 12/12 命造的四柱、指定神煞及指定关系在模型 Context 中完整保留。
- 下层 scope 均保留全部上层：流年含原局+大运，流月再含流年，流日再含流月。
- 模型输入不再包含双份 natal/temporal、恒定布尔矩阵、审计 rule/source 元数据和不适用 null/空字符串。
- 四个历史命造缺少可核验出生日期，只验证原局 Prompt；八个有日期命造验证真实岁运 Prompt。

## 旧问答实例的规模对比

- 旧调用实际输入：145,219 tokens。
- 旧序列化字符：443,485；新序列化字符：55,753。
- 新旧字符比：12.6%。
- 按同一调用字符/token 比例估算，新输入约 18,256 tokens。
- 该估算包含动态 system prompt、JSON Schema 和 8 条非重复 RAG 证据。

## 逐例验证

### case-01-1995
- 场景：`year` / relationship
- 层级字段：`hierarchy, active_dayun, target_liunian, monthly_windows`
- Golden 事实保留：通过
- 新 Prompt JSON：51,925 字符；旧确定性载荷 436,480 字符；比例 11.9%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主丁，四柱乙亥 戊子 丁亥 戊申；当前大运乙酉已提供原局作用；流年丙午已提供运年交互；全年12个流月窗口可比较；配偶星位置1处、夫妻宫和相关神煞均可读取。

### case-02-1999
- 场景：`month` / wealth, career
- 层级字段：`hierarchy, active_dayun, target_liunian, target_liuyue`
- Golden 事实保留：通过
- 新 Prompt JSON：15,730 字符；旧确定性载荷 437,802 字符；比例 3.6%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主壬，四柱己卯 庚午 壬子 丙午；当前大运癸酉已提供原局作用；流年丙午已提供运年交互；流月乙未承接流年；官杀、印星和食伤位置索引可读取；财星及食伤生财位置索引可读取。

### case-03-chongzhen
- 场景：`general` / relationship, career
- 层级字段：`hierarchy, scope_note`
- Golden 事实保留：通过
- 新 Prompt JSON：7,342 字符
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主乙，四柱辛亥 庚寅 乙未 己卯；配偶星位置3处、夫妻宫和相关神煞均可读取；官杀、印星和食伤位置索引可读取。

### case-04-kublai
- 场景：`general` / career
- 层级字段：`hierarchy, scope_note`
- Golden 事实保留：通过
- 新 Prompt JSON：5,543 字符
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主乙，四柱乙亥 乙酉 乙酉 乙酉；官杀、印星和食伤位置索引可读取。

### case-05-wuzetian
- 场景：`general` / relationship, career
- 层级字段：`hierarchy, scope_note`
- Golden 事实保留：通过
- 新 Prompt JSON：5,933 字符
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主甲，四柱甲申 丙寅 甲午 甲戌；配偶星位置2处、夫妻宫和相关神煞均可读取；官杀、印星和食伤位置索引可读取。

### case-06-zhuyuanzhang
- 场景：`general` / career, health
- 层级字段：`hierarchy, scope_note`
- Golden 事实保留：通过
- 新 Prompt JSON：6,117 字符
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主丁，四柱戊辰 壬戌 丁丑 丁未；五行、月令季节和健康相关神煞可读取；官杀、印星和食伤位置索引可读取。

### case-07-1974
- 场景：`day` / relationship, wealth
- 层级字段：`hierarchy, active_dayun, target_liunian, target_liuyue, target_liuri`
- Golden 事实保留：通过
- 新 Prompt JSON：19,687 字符；旧确定性载荷 430,933 字符；比例 4.6%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主甲，四柱甲寅 丁卯 甲戌 辛未；当前大运癸酉已提供原局作用；流年丙午已提供运年交互；流月乙未承接流年；流日癸巳作为短期触发；配偶星位置3处、夫妻宫和相关神煞均可读取；财星及食伤生财位置索引可读取。

### case-08-1986
- 场景：`lifecycle` / career, health
- 层级字段：`hierarchy, qiyun, dayun_sequence`
- Golden 事实保留：通过
- 新 Prompt JSON：31,307 字符；旧确定性载荷 448,679 字符；比例 7.0%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主己，四柱丙寅 己亥 己巳 己巳；大运序列12步可比较；五行、月令季节和健康相关神煞可读取；官杀、印星和食伤位置索引可读取。

### case-09-1948-01
- 场景：`year` / health
- 层级字段：`hierarchy, active_dayun, target_liunian, monthly_windows`
- Golden 事实保留：通过
- 新 Prompt JSON：52,501 字符；旧确定性载荷 449,301 字符；比例 11.7%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主甲，四柱丁亥 癸丑 甲辰 乙丑；当前大运乙巳已提供原局作用；流年丙午已提供运年交互；全年12个流月窗口可比较；五行、月令季节和健康相关神煞可读取。

### case-10-1948-00
- 场景：`month` / wealth
- 层级字段：`hierarchy, active_dayun, target_liunian, target_liuyue`
- Golden 事实保留：通过
- 新 Prompt JSON：10,964 字符；旧确定性载荷 444,620 字符；比例 2.5%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主甲，四柱丁亥 癸丑 甲辰 甲子；当前大运乙巳已提供原局作用；流年丙午已提供运年交互；流月乙未承接流年；财星及食伤生财位置索引可读取。

### case-11-1990
- 场景：`day` / career
- 层级字段：`hierarchy, active_dayun, target_liunian, target_liuyue, target_liuri`
- Golden 事实保留：通过
- 新 Prompt JSON：17,799 字符；旧确定性载荷 448,176 字符；比例 4.0%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主丙，四柱己巳 丙子 丙寅 戊子；当前大运癸酉已提供原局作用；流年丙午已提供运年交互；流月乙未承接流年；流日癸巳作为短期触发；官杀、印星和食伤位置索引可读取。

### case-12-2000
- 场景：`dayun` / relationship, career
- 层级字段：`hierarchy, qiyun, target_dayun, dayun_sequence`
- Golden 事实保留：通过
- 新 Prompt JSON：10,881 字符；旧确定性载荷 509,498 字符；比例 2.1%
- 空/无效字段统计：null=0，空字符串=0，布尔值=0，审计键=0
- 模拟模型可用性：日主癸，四柱庚辰 甲申 癸亥 戊午；大运序列12步可比较；配偶星位置4处、夫妻宫和相关神煞均可读取；官杀、印星和食伤位置索引可读取。

## 判定

Prompt 信息量合格：没有阉割上层岁运背景，12 个命造的关键确定性事实均可读取；主要冗余已从模型输入移到审计快照。仍保留的少量重复属于专题索引（如配偶星位置），用于降低模型在完整四柱中自行搜索和误读的概率。