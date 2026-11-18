# 数据集可用性评估 —— South Asian Recipes（5 表版）

> 评估对象：`group_project/dataset/archive/` 下 5 个 CSV
> 评估方式：`dataset/profile_dataset.py` 可复现（`python3 profile_dataset.py`），全部数字均由该脚本产出
> 对应分工：**A1 数据集与 license 清单 / A2 Data profiling**｜结论同时影响 **B5（反向检索排序）** 与 **B7（全文检索）** 的设计

---

## 0. 一句话结论

**可以用，建议直接定稿为主数据集** —— 它的"工程结构分"接近满分（0 空值、0 重复主键、双向引用完整、23 个字段覆盖了我们 P0 三类检索的全部筛选维度，10k 主表 + 10 万明细的体量正好做索引实验）。

但必须同时接受一个事实：**这是一份模板合成数据集**（证据见 §3.1），营养值、膳食标签、用量三者互相对不上，**不能直接入库**，必须先做 §3.2 里的 P1–P5 修复（其中 P1/P3 属于阻塞项）。另外有 1 个范围决策（菜系只有南亚 5 类）和 1 个功能降级（全文检索的步骤文本几乎无区分度）。

---

## 1. 数据概况

| 文件 | 行 × 列 | 主键 | 作用 |
| --- | ---: | --- | --- |
| `recipes_master.csv` | 9,997 × 23 | `recipe_id` | 菜谱主表：菜系、类别、烹饪方式、难度、三段时间、份数、辣度、餐次、4 个膳食标签、评分/评论数、热量、成本、上架日期、传统/节日标记 |
| `recipe_ingredients.csv` | 103,908 × 5 | (`recipe_id`,`ingredient_number`) | 食材明细：名称、**原始用量字符串**、食材大类（8 类） |
| `recipe_steps.csv` | 84,616 × 4 | (`recipe_id`,`step_number`) | 步骤：描述文本 + 单步预计耗时（2–14 min） |
| `recipe_nutrition.csv` | 9,997 × 13 | `recipe_id` | 12 项营养：热量/蛋白/碳水/脂肪/纤维/糖/钠/胆固醇 + 4 个维生素矿物质百分比 |
| `cuisine_metadata.csv` | 5 × 3 | `cuisine` | 菜系 → 类别清单 + 声明菜谱数 |

规模分布：Indian 3,498 / Pakistani 3,000 / Bangladeshi 1,500 / Afghan 1,000 / Fusion 999（与 `cuisine_metadata` 声明值 **5/5 完全一致**）。
覆盖 11 个 category、8 种 cooking_method、6 种 meal_type、4 级 spice_level、3 档 difficulty；热量 150–799 kcal、成本 \$2.00–25.00、总时长 26–237 min、评分 3.5–5.0。

---

## 2. 通过项：确定不用动的地方

| # | 检查项 | 结果 | 对项目的意义 |
| --- | --- | --- | --- |
| 1 | 空值 | 四表 **0 个空值** | 不用写缺失值填补逻辑，A2 工时省一半 |
| 2 | 主键 / 复合主键唯一性 | 全部 **0 重复** | 可直接建 PK，3NF 论证干净 |
| 3 | 引用完整性（双向差集） | 四表 ↔ master **0 缺失 / 0 孤儿** | FK 能加约束，不会在导入时炸 |
| 4 | `total_time = prep + cook` | **9,997/9,997** | 派生列可信，B6 按时间过滤可用 |
| 5 | `master.calories_per_serving = nutrition.calories` | **9,997/9,997** | 主表与营养表不会打架，C5 不必做优先级仲裁 |
| 6 | `cuisine_metadata.recipe_count` vs 实数 | **5/5 一致** | 菜系统计页可直出 |
| 7 | 用量字符串可解析性 | **100% 可解析**，6 种格式（g 17.2% / ml 7.8% / tbsp 30.8% / tsp 7.7% / medium·cloves 26.9% / to taste 9.6%） | A4 用量解析器有真实工作量，但**边界有限、8 小时内可收敛**；且天然产出"脏数据测试集"（A9） |
| 8 | 过敏原可推导性 | 58 个食材已覆盖 乳（Paneer/Butter/Milk/Cream/Yogurt/Ghee）、蛋、虾、鱼、麸质（Wheat/AP Flour/Semolina）、坚果（Almonds/Cashews）、芝麻、大豆（Tofu） | **"排除过敏原"功能可以做**，A6 映射表不用外部数据源 |

> 补充：`review_count` 10–4,999、`rating` 3.5–5.0、`date_added` 2023-02-16 → 2026-02-13，都可用于"按热度/评分排序"与"最近上新"两个排序维度。

---

## 3. 问题项：必须修的 6 件事

### 3.1 先定性：这是模板合成数据（判断依据）

| 证据 | 数字 |
| --- | --- |
| 步骤描述去重后**只有 20 种**文本 | 84,616 行 → 20 种 |
| 30.3% 菜名是占位名（`… Special 123`） | 3,034 / 9,997（去重后仅 3,085 个名字） |
| Onion / Garlic / Salt 出现在 **100%** 菜谱 | 各 9,997 次 |
| 步骤与食材互不耦合：说"Soak rice"却无米的菜谱 | 3,445 / 4,015 |
| 步骤里 44.7% 的菜谱含"Add the **marinated protein**"这类占位表述 | 4,472 条 |
| 营养值 12 项均为整数且有整齐上下界（钠 200–1499、评分 3.5–5.0、成本 \$2–25） | — |

**这不是缺点，而是要在报告里主动讲清楚的事实**：我们会把它写成"半合成数据集"，并把这 6 个问题当成 §7"挑战"的素材 —— 评分里"数据质量分析"恰恰是加分项，藏起来才会被问穿。

### 3.2 问题清单与修复契约

| # | 问题 | 严重度 | 现象（数字） | 影响的功能 | 修复策略 | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| P1 | **膳食标签与食材矛盾** | 🔴 阻塞 | `is_vegetarian=True` 却含肉/海鲜 **1,195 条（32.0%）**；`is_vegan=True` 却含动物制品 **860 条（89.2%）**，其中 557 条含肉；`is_gluten_free=True` 却含小麦/粗麦粉 **544 条（35.6%）** | B6 过敏原/素食过滤、D2 筛选器 —— 直接出错结果 | **丢弃原始标签，由食材表重生**：`is_vegetarian = 无(肉∪海鲜)`、`is_vegan = vegetarian ∧ 无(蛋/乳)`、`is_gluten_free = 无麸质谷物`。原值另存 `*_declared` 列，用于报告对比"修复前后召回差异" | A6/A7 |
| P2 | **热量与宏量营养素不符**（Atwater 4P+4C+9F） | 🟠 中 | 仅 **17.1%** 落在 ±10%，**33.2%** 落在 ±20%，**34.0%** 偏差 >50%（例：RCP00002 标 264 kcal，按宏量应为 673 kcal） | C5 营养分析、D 营养面板、meal-plan 汇总 —— 用户会当场算出矛盾 | 两级方案：① 主口径**保留原始 `calories`**（数据即事实），新增 `calories_atwater` 派生列；② API 只暴露 `calories`，`macros_consistent` 布尔标记在详情页显示"营养数据为估算值" | A7 / C5 |
| P3 | **用量荒谬 + 单位语义错配 + 重复食材** | 🟠 中 | 每份可用食材质量中位数 170 g，却标 477 kcal（物理上不成立）；**4,107 行**固体食材用 ml（`Butter 229 ml`、`Ghee 133 ml`、`Paneer 286 ml`）；**39.0%** 菜谱出现 ≥4 条 tbsp 用量；**4,849/9,997** 菜谱在同一菜谱内重复列同一食材 | C4 购物清单聚合、D4 购物清单页 —— 会输出"933g 虾 + 4 tbsp 鸡肉"这种明显离谱结果 | ① `(recipe_id, ingredient_name)` 聚合去重（保留最大量、`to taste` 优先）；② 单位规范化到 (数值, 单位枚举) 二元组 + 换算表（tbsp 15ml / tsp 5ml / 1 medium≈120g 等）；③ **硬性截断** `grams > 500` 与 `total_serving_mass ∉ [100, 600]` 的极端值 | A4 / A8 |
| P4 | **步骤文本无区分度、且与实际食材不耦合** | 🟠 中 | 20 种模板覆盖 84,616 行；34% 菜谱"泡米"但没米 | **B7 全文检索**（评分点之一） | 不改数据，改**搜索文档定义**（见 §5-D2）：`search_doc = 菜名 + 菜系 + 类别 + 食材名串 + 步骤模板`，用 `to_tsvector('simple', …)` + GIN；报告中如实写明"步骤文本为模板化生成，故检索质量主要来自菜名与食材" | B7 |
| P5 | **占位菜名 + 菜名重复** | 🟡 低 | 3,034 条（30.3%）为 `Pakistani Main Course Special 14`；`Biryani` 336 次、`Chole Bhature` 191 次 | D1 列表页观感、D2 检索结果可读性 | ETL 里把占位名重写为 `{cuisine} {category} #{n}` 并置 `is_placeholder_name=true`，**列表默认按 `is_placeholder_name` 排序靠后**；前端对重名菜谱显示 `#recipe_id` 后缀 | A5 / D1 |
| P6 | **缺图片 / 缺用户与评论正文 / 缺真实自然语言步骤** | 🟡 低 | 无 `image_url`、无 user 表、无 review 文本 | D3 详情页视觉、P2 用户收藏功能 | ① 图片：按 `cuisine+category` 映射到 8–10 张本地占位图（不引外链，避免离线演示翻车）；② 用户/收藏：**自建表**（本来就要做，属原生需求）；③ 不补真实步骤文本 | D3 / C7 |

**修复优先级**：P1 → P3 → P2 → P4/P5 → P6。P1 和 P3 不进 ETL 就不能跑 B6 与购物清单，属于"链路阻塞项"。

---

## 4. 功能点 → 数据可用性映射

| 功能（分工项） | 数据够不够 | 前提 / 说明 |
| --- | --- | --- |
| ① 食材反向检索 + 重合度排序（B5） | ✅ 够，**但排序必须加 IDF** | 58 个食材、9,491 个不同食材集合 → 区分度可用；但 Onion/Garlic/Salt 出现在 **100%** 菜谱，随机菜谱对平均 Jaccard 已高达 **0.267**，纯 Jaccard 会让"我有洋葱大蒜盐"命中全部 9,997 条且并列。**设计改为 IDF 加权余弦式 `score = Σ idf(i) / √(n_cand × n_query)`，并设最小匹配阈值（≥2 个命中，且至少 1 个 idf 高于阈值）** |
| ② 多条件正向过滤（B6） | ✅ 很强 | 11 category × 8 method × 6 meal_type × 4 spice × 3 difficulty × 5 cuisine，加 calories 150–799 / cost \$2–25 / time 26–237 / rating 3.5–5.0 的连续区间 + 4 个膳食标签（**P1 修复后**）→ 组合筛选项充足，索引实验也够做（多列 B-tree + 部分索引） |
| ③ 全文检索 + 高亮（B7） | ⚠️ 可用但需换文档定义 | 见 §5-D2；菜名 3,085 个真实菜名（Biryani / Butter Chicken / Palak Paneer / Hakka Noodles / Chaat…）足够演示 LIKE vs tsvector 的差异与 GIN 加速 |
| 营养分析 API（C5） | ✅ 丰富 | 12 项营养全在，可做"高蛋白低钠"、"蛋白质密度 g/100kcal"（中位数 5.4，≥20 的 313 条）等角度；注意 P2 的一致性标记 |
| 饮食计划 / 购物清单（C6、C4） | ✅ 但依赖 P3 | 有 servings + cost + 营养，做 meal-plan 汇总天然可行；购物清单的**单位换算**是这块的真正难点（也是亮点） |
| 过敏原排除（A6） | ✅ 58 食材可全覆盖 | 乳/蛋/虾/鱼/麸质/坚果/芝麻/大豆 都能命中，无需外部映射数据 |
| 用户系统 / 收藏 / 偏好（P2 域） | ❌ 需自建 | 数据集完全没有用户与评论正文，只有聚合的 `rating`/`review_count` → 用户表、收藏表、偏好表全部自建（这也正好是 P2 新功能域的合理工作量） |
| 性能实验：有/无索引 × 三档规模（B8） | ✅ 理想 | 9,997 / 103,908 的基础量级 → Part A 复制扩到 5 万 / 20 万菜谱（47 万 / 189 万条食材行）是纯数据工程活；因为**数据本来就是合成的，扩展不涉及任何隐私或版权问题**，实验前提比真实数据集更干净。实测见 `docs/scale_experiment.md` |
| 菜系多样性展示 | ⚠️ 仅南亚 | 5 个菜系全是南亚（Indian/Pakistani/Bangladeshi/Afghan/Fusion）→ 见 §5-D1 |

---

## 5. 需要你拍板的 3 个决策（附推荐）

### D1｜菜系范围：收窄还是补数据？（推荐：收窄）
- **推荐做法**：把项目范围明确写成「**南亚菜系（印度 / 巴基斯坦 / 孟加拉 / 阿富汗 / 印式中餐融合）智能食谱与营养检索系统**」，报告 §1 一句话说明范围。理由：数据内部自洽、演示统一、评审不会觉得"杂"。
- 不推荐的做法：硬说"多菜系"。5 个菜系全在南亚次大陆，一说就漏。
- 若确实需要多样性（成本 4–6 h）：只补 1 个真实数据集（如 Food.com / RecipeNLG 子集 2–5k 条）**仅用于全文检索文本质量对照**，独立一张 `external_recipes_text` 表，不并入主 schema。

### D2｜全文检索的"搜索文档"怎么定义？（推荐：复合文档）
```
search_doc = recipe_name + cuisine + category + cooking_method
           + 所有 ingredient_name（去重，空格连接）
           + 去重后的 step_description（仅 20 种模板，贡献极小）
```
配 `GIN(to_tsvector('simple', search_doc))`，并在报告里写明："步骤文本为模板化生成（84,616 行仅 20 种表述），因此检索质量主要来自菜名与食材名；若换用真实数据集该字段可直接替换。" —— 这样"数据局限"就变成了"设计留了扩展口"，是加分叙述。

### D3｜是否现在就换数据集？（推荐：不换）
换数据集的唯一收益是文本真实，代价是重建 schema、重做 ETL、重跑 8 周排期。而我们现在这批数据的**结构性优势（0 脏键 / 引用完整 / 23 字段 / 10 万明细）在公开数据集里相当罕见**。结论：**留着，用 ETL 和报告把短板讲清楚。**

---

## 6. 报告里可以直接用的话术

**中文（放 §3.1 数据来源）**
> 本项目数据源为 5 张关联 CSV（菜谱主表 9,997 条、食材明细 103,908 条、步骤 84,616 条、营养 9,997 条、菜系元数据 5 条），覆盖印度、巴基斯坦、孟加拉、阿富汗与印式融合五个南亚菜系。数据在结构层面质量良好：无空值、无主键重复、四表双向引用完整，派生字段（总时长、热量）与源字段完全一致。检查同时发现该数据集为**模板化半合成数据**：步骤文本仅 20 种表述、30.3% 菜名为占位命名，且原始膳食标签与食材存在系统性冲突（素食标签中 32.0% 含肉、纯素标签中 89.2% 含动物制品）。因此本项目将数据清洗本身作为工作的一环：膳食标签由食材表重新推导（并以 `*_declared` 列保留原值用于对比），用量统一解析为「数值 + 单位」二元组并做极端值截断，热量与宏量营养素的 Atwater 偏差作为数据可信度指标在详情页披露。

**English（Report abstract / §3.1）**
> The dataset comprises five linked CSVs (9,997 recipes, 103,908 ingredient rows, 84,616 step rows, 9,997 nutrition rows and 5 cuisine records) covering five South Asian cuisines. Structural quality is high — no nulls, no duplicate keys, full two-way referential integrity, and derived columns consistent with their sources. Profiling also revealed the data to be **template-generated**: only 20 distinct step descriptions and 30.3% placeholder recipe names, with dietary flags systematically contradicting the ingredient lists (32.0% of "vegetarian" recipes contain meat, 89.2% of "vegan" recipes contain animal products). Rather than discarding the dataset, we treat cleansing as part of the deliverable: dietary flags are re-derived from ingredients (declared values retained for comparison), quantities are normalised into numeric-plus-unit pairs with outlier clipping, and the Atwater discrepancy between stated calories and macronutrients is surfaced as a confidence indicator in the UI.

---

## 7. 待办与对现有分工表的影响

| 事项 | Owner | 说明 |
| --- | --- | --- |
| 记录数据出处与 license（URL / 下载日期 / 授权） | A1 | 目录名 `archive/` 为 Kaggle 下载解包结构，**原始页面与 license 未随文件附带**；报告里必须写明来源，若无法确认授权则注明"仅用于课程作业" |
| 把 `profile_dataset.py` 的输出落到 `etl/profile_report.md` | A2 | 脚本已可复现全部数字，直接 `python3 profile_dataset.py > ../etl/profile_report.md` |
| 标签重算 + 单位解析 + 去重/截断 | A7 / A4 | 见 §3.2 的 P1/P3 |
| 反向检索排序改 IDF 加权 + 最小匹配阈值 | B5 | **原计划的纯 Jaccard 在此数据上会全量并列**，这是本次体检最重要的设计修正 |
| 全文检索改用复合 `search_doc` | B7 | 见 §5-D2 |
| 前端占位图方案 + 重名菜谱展示 | D1 / D3 | 见 §3.2 的 P5/P6 |

**对工时的影响**：A5（食材名归一化）原估 10 h 需要**下调**（只有 58 个食材，同义词/复数问题几乎不存在，2–3 h 即可）；省下的工时转到 **A4（用量/单位解析）与 A7（标签重算）**，这两项在本数据集上才是真正耗时的部分。总工时不变，A 的 68 h 仍成立。
