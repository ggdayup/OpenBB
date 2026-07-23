Edited user_settings.json
Viewed user_settings.json:1-27
Viewed verify_free_providers.py:1-116
Listed directory providers
Ran command: `python3 -c "
import os, glob, re

providers_dir = '/Users/ggdayup/ggdayup-syncthing/code/OpenBB/openbb_platform/providers'
free_providers = []
api_required_providers = []

for item in sorted(os.listdir(providers_dir)):
    p = os.path.join(providers_dir, item)
    if os.path.isdir(p) and item != 'tests':
        py_files = glob.glob(f'{p}/**/*.py', recursive=True)
        has_credentials = False
        cred_keys = set()
        for f in py_files:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
                matches = re.findall(r'(\w+_api_key|\w+_token|\w+_key|\w+_secret)', content, re.IGNORECASE)
                if matches:
                    has_credentials = True
                    for m in matches:
                        if 'credentials' in content:
                            cred_keys.add(m.lower())
        if has_credentials and len(cred_keys) > 0:
            api_required_providers.append((item, sorted(list(cred_keys))))
        else:
            free_providers.append(item)

print('=== 免 API Key (免费/公开公开数据源) ===')
for fp in free_providers:
    print('  -', fp)

print('\n=== 需要 API Key (凭证/注册密钥) ===')
for ap, keys in api_required_providers:
    print(f'  - {ap} (keys: {keys})')
"`
Ran command: `python3 -c "
import os, json

manifest = '/Users/ggdayup/ggdayup-syncthing/code/OpenBB/assets/extensions/provider.json'
if os.path.exists(manifest):
    with open(manifest, 'r') as f:
        data = json.load(f)
    print('Found provider manifest with', len(data), 'providers/entries')
    # Check credentials map if present
"`
Ran command: `python3 -c "
import json

manifest = '/Users/ggdayup/ggdayup-syncthing/code/OpenBB/assets/extensions/provider.json'
with open(manifest, 'r') as f:
    data = json.load(f)

no_key_required = []
key_required = {}

for p_name, p_info in data.items():
    creds = p_info.get('credentials', [])
    if not creds:
        no_key_required.append(p_name)
    else:
        key_required[p_name] = creds

print('=== 不需要 API Key 的公开/免费数据源 ===')
for p in sorted(no_key_required):
    print(f'  - {p}')

print('\n=== 需要配置 API Key / Token 的数据源 ===')
for p, creds in sorted(key_required.items()):
    print(f'  - {p}: {creds}')
"`
Ran command: `python3 -c "
import json
manifest = '/Users/ggdayup/ggdayup-syncthing/code/OpenBB/assets/extensions/provider.json'
with open(manifest, 'r') as f:
    data = json.load(f)

for p in data:
    name = p.get('name')
    creds = p.get('credentials', [])
    print(f'{name}: {creds}')
"`
Ran command: `python3 -c "
import json
manifest = '/Users/ggdayup/ggdayup-syncthing/code/OpenBB/assets/extensions/provider.json'
with open(manifest, 'r') as f:
    data = json.load(f)

for p in data:
    # Print non-null fields
    keys = [k for k in p.keys() if k != 'models']
    creds = p.get('credentials', [])
    # Find package/name field
    name = p.get('provider') or p.get('name') or keys
    print(f'{p.get(\"provider\", p.get(\"name\"))}: {creds}')
"`
Ran command: `python3 -c "
import json
manifest = '/Users/ggdayup/ggdayup-syncthing/code/OpenBB/assets/extensions/provider.json'
with open(manifest, 'r') as f:
    data = json.load(f)

for i, p in enumerate(data):
    creds = p.get('credentials', [])
    # Let's inspect keys
    print(f'Item {i}: keys={list(p.keys())[:3]}, creds={creds}')
"`
Ran command: `python3 -c "
import json
manifest = '/Users/ggdayup/ggdayup-syncthing/code/OpenBB/assets/extensions/provider.json'
with open(manifest, 'r') as f:
    data = json.load(f)

free_providers = []
api_providers = {}

for p in data:
    name = p.get('reprName') or p.get('packageName').replace('openbb-', '')
    creds = p.get('credentials', [])
    if not creds:
        free_providers.append(name)
    else:
        api_providers[name] = creds

print('=== 1. 完全免 API Key（开箱即用 / 全免费数据源）===')
for p in sorted(free_providers):
    print(f'  • {p}')

print('\n=== 2. 需要配置 API Key / Token 的数据源 ===')
for p, creds in sorted(api_providers.items()):
    print(f'  • {p:<20} -> Key 名称: {creds}')
"`

在 OpenBB (Platform v4) 架构中，共集成了 **32+ 个内置数据源 (Providers)**。

根据数据源的验证状态与 API Key 要求，具体分类如下：

---

### 一、 完全免 API Key（开箱即用 / 全免费数据源）

这些数据源**不需要注册或配置任何 API Key**，在 OpenBB 安装后即可直接调用：

#### 1. 股票行情与公司基本面
* **Yahoo Finance (`yfinance`)**：支持美股、港股、A 股、加密货币、外汇的历史 K 线、实时行情及基础财务数据（OpenBB 核心降级兜底源）。
* **SEC EDGAR (`sec`)**：美国证券交易委员会官方全量免费 10-K / 10-Q 财报与公司申报文件。
* **FinViz (`finviz`)**：美股 Screener 选股器、热门大盘表现及财经新闻。
* **CBOE (`cboe`)**：芝加哥期权交易所的期权链及波动率指数 (VIX) 数据。
* **TMX (`tmx`)**：多伦多证券交易所 (Canada) 行情数据。
* **AKShare (`akshare`)**：国内全开源金融数据源，支持 A 股、港股、中国期货及宏观数据。

#### 2. 宏观经济与央行/政府机构
* **Federal Reserve (`federal_reserve`)**：美联储官方声明、利率决议与资产负债表。
* **European Central Bank (`ecb`)**：欧洲央行官方宏观经济指标与汇率数据。
* **IMF (`imf`)**：国际货币基金组织全球经济数据库与海运港口追踪。
* **OECD (`oecd`)**：经合组织全球宏观经济统计。
* **Data.gov (`government_us`)**：美国政府公开数据集。
* **FINRA (`finra`)**：美国金融业监管局场外交易与做空数据。
* **multpl (`multpl`)**：标普 500 历史估值指标 (P/E, Shiller PE, 股息率等)。
* **Fama-French (`famafrench`)**：学术界经典的 Fama-French 三因子/五因子模型因子数据。

#### 3. 特殊资产与新闻/暗池
* **Deribit (`deribit`)**：Deribit 头部加密货币期权与永续合约公开行情。
* **Seeking Alpha (`seeking_alpha`)**：美股个股分析文章与市场新闻。
* **WSJ (`wsj`)**：华尔街日报大宗商品与全球指数行情。
* **Stockgrid (`stockgrid`)**：美股暗池 (Darkpool) 与机构大单跟踪。

---

### 二、 需要配置 API Key / Token 的数据源

这些数据源必须在 `user_settings.json` 中配置对应的凭证才能使用。分为**免费 Key** 与 **付费 Key** 两种类型：

#### 1. 免费申请注册即可使用的 Key (有免费额度)
* **FRED (`fred_api_key`)**：St. Louis 联储官方宏观数据库（免费注册即可获取 Key，数据量极其庞大）。
* **BLS (`bls_api_key`)**：美国劳工统计局 CPI/失业率数据（免费申请 API Key）。
* **EIA (`eia_api_key`)**：美国能源信息署原油/天然气能源数据（免费申请 API Key）。
* **Congress.gov (`congress_gov_api_key`)**：美国国会议员持仓与交易披露（免费申请）。
* **CFTC (`cftc_app_token`)**：美国商品期货交易委员会持仓报告 (COT)。
* **Alpha Vantage (`alpha_vantage_api_key`)**：提供美股与技术指标（免费账户每日限制 25 次请求）。
* **Tiingo (`tiingo_token`)**：提供历史行情与加密货币数据（提供免费个人额度）。

#### 2. 付费/商业级 API Key
* **Financial Modeling Prep (`fmp_api_key`)**：美股深度基本面与拆解数据（新账号需付费订阅）。
* **Polygon (`polygon_api_key`)**：美股实时 Tick/分钟级行情。
* **Benzinga (`benzinga_api_key`)**：机构级实时新闻与分析师评级。
* **Intrinio (`intrinio_api_key`)**：机构级财务报表与期权流数据。
* **NASDAQ (`nasdaq_api_key`)**：纳斯达克官方 Data Link 数据集。
* **Tradier (`tradier_api_key`)**：实时期权链与实盘交易。
* **Trading Economics (`tradingeconomics_api_key`)**：全球国家级高频经济指标。
* **EconDB (`econdb_api_key`)** / **BizToc (`biztoc_api_key`)**：经济与新闻数据。

---

### 💡 最佳使用建议
如果希望搭建一个**完全免费、无额度担忧**的 OpenBB 基础设施：
1. 主力行情与基本面选：`yfinance` + `sec` + `finviz`
2. 宏观经济选：`federal_reserve` + 免费申请一个 `fred_api_key`
3. 国内市场选：`akshare`