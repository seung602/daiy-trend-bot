un-trend-bot
succeeded 1 minute ago in 1m 2s
Search logs
3s
Current runner version: '2.336.0'
Runner Image Provisioner
Operating System
Runner Image
GITHUB_TOKEN Permissions
Secret source: Actions
Prepare workflow directory
Prepare all required actions
Getting action download info
Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
Complete job name: run-trend-bot
1s
Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
Run actions/checkout@v4
Syncing repository: seung602/daiy-trend-bot
Getting Git version info
Temporarily overriding HOME='/home/runner/work/_temp/160519b5-8871-4bf4-8a38-847b59522900' before making global git config changes
Adding repository directory to the temporary git global config as a safe directory
/usr/bin/git config --global --add safe.directory /home/runner/work/daiy-trend-bot/daiy-trend-bot
Deleting the contents of '/home/runner/work/daiy-trend-bot/daiy-trend-bot'
Initializing the repository
Disabling automatic garbage collection
Setting up auth
Fetching the repository
Determining the checkout info
/usr/bin/git sparse-checkout disable
/usr/bin/git config --local --unset-all extensions.worktreeConfig
Checking out the ref
/usr/bin/git log -1 --format=%H
2cf8c4798157e5f63c41235b729f3476270520f9
2s
Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
Run actions/setup-python@v5
Installed versions
/opt/hostedtoolcache/Python/3.10.20/x64/bin/pip cache dir
/home/runner/.cache/pip
Cache hit for: setup-python-Linux-x64-24.04-Ubuntu-python-3.10.20-pip-d44e08ac108f3a9ad37298f47c6360bc8913502a4a1ac567dc01be84311a6f4a
(node:2021) [DEP0169] DeprecationWarning: `url.parse()` behavior is not standardized and prone to errors that have security implications. Use the WHATWG URL API instead. CVEs are not issued for `url.parse()` vulnerabilities.
Received 2544800 of 2544800 (100.0%), 33.7 MBs/sec
Cache Size: ~2 MB (2544800 B)
/usr/bin/tar -xf /home/runner/work/_temp/fae4fcc8-88c3-4edd-8cac-af5bc00b95c0/cache.tzst -P -C /home/runner/work/daiy-trend-bot/daiy-trend-bot --use-compress-program unzstd
Cache restored successfully
Cache restored from key: setup-python-Linux-x64-24.04-Ubuntu-python-3.10.20-pip-d44e08ac108f3a9ad37298f47c6360bc8913502a4a1ac567dc01be84311a6f4a
4s
Run python -m pip install --upgrade pip
Requirement already satisfied: pip in /opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages (26.1.2)
Collecting pip
  Using cached pip-26.2.1-py3-none-any.whl.metadata (4.6 kB)
Using cached pip-26.2.1-py3-none-any.whl (1.8 MB)
Installing collected packages: pip
  Attempting uninstall: pip
    Found existing installation: pip 26.1.2
    Uninstalling pip-26.1.2:
      Successfully uninstalled pip-26.1.2
Successfully installed pip-26.2.1
Collecting requests (from -r requirements.txt (line 1))
  Using cached requests-2.34.2-py3-none-any.whl.metadata (4.8 kB)
Collecting charset_normalizer<4,>=2 (from requests->-r requirements.txt (line 1))
  Using cached charset_normalizer-3.4.9-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (41 kB)
Collecting idna<4,>=2.5 (from requests->-r requirements.txt (line 1))
  Using cached idna-3.18-py3-none-any.whl.metadata (6.1 kB)
Collecting urllib3<3,>=1.26 (from requests->-r requirements.txt (line 1))
  Using cached urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
Collecting certifi>=2023.5.7 (from requests->-r requirements.txt (line 1))
  Using cached certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
Using cached requests-2.34.2-py3-none-any.whl (73 kB)
Using cached charset_normalizer-3.4.9-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (223 kB)
Using cached idna-3.18-py3-none-any.whl (65 kB)
Using cached urllib3-2.7.0-py3-none-any.whl (131 kB)
Using cached certifi-2026.7.22-py3-none-any.whl (136 kB)
Installing collected packages: urllib3, idna, charset_normalizer, certifi, requests

Successfully installed certifi-2026.7.22 charset_normalizer-3.4.9 idna-3.18 requests-2.34.2 urllib3-2.7.0
0s
Run echo "Checking model configuration in main.py:"
Checking model configuration in main.py:
39:GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
48s
Run python main.py
2026-08-11 05:50:34,048 - INFO - === Daily Cosmetics Trend Bot Started ===
2026-08-11 05:50:34,049 - INFO - SQLite database initialized: beauty_trends.db
2026-08-11 05:50:34,049 - INFO - Today's TikTok queries: ['sunscreen', 'sun stick', 'spf skincare']
2026-08-11 05:50:34,049 - INFO - Today's Instagram scraper tags: ['pdrn', 'polynucleotide', 'peptide', 'exosomeskincare', 'ceramide', 'ectoin', 'centella', 'cica', 'snailmucin', 'propolis']
2026-08-11 05:50:34,050 - INFO - Today's Google groups: ['problem', 'product']
2026-08-11 05:50:34,050 - INFO - Collecting independent Google beauty signals...
2026-08-11 05:50:34,050 - INFO - Google independent discovery: autocomplete_jobs=12 (hard cap=12)
2026-08-11 05:50:49,041 - INFO - Google autocomplete accepted signals [NL]: 47
2026-08-11 05:50:49,041 - INFO - Google autocomplete accepted signals [DE]: 54
2026-08-11 05:50:49,736 - INFO - Fetching TikTok...
2026-08-11 05:50:50,258 - INFO - TikTok query 'sunscreen' returned 0 items despite HTTP 200. Raw response (first 300 chars): {'backtrace': '', 'cursor': 12, 'extra': {'now': 1786427450129, 'logid': '20260811135049B8FF19F2E5BC6C062024', 'search_request_id': ''}, 'has_more': 0, 'item_list': [], 'log_pb': {'impr_id': '20260811135049B8FF19F2E5BC6C062024'}, 'status_code': 0}
2026-08-11 05:50:51,217 - INFO - TikTok query 'sun stick' returned 0 items despite HTTP 200. Raw response (first 300 chars): {'backtrace': '', 'cursor': 12, 'extra': {'now': 1786427451066, 'logid': '20260811135050225A6F1ADDAC0A054368', 'search_request_id': ''}, 'has_more': 0, 'item_list': [], 'log_pb': {'impr_id': '20260811135050225A6F1ADDAC0A054368'}, 'status_code': 0}
2026-08-11 05:50:52,134 - INFO - TikTok query 'spf skincare' returned 0 items despite HTTP 200. Raw response (first 300 chars): {'backtrace': '', 'cursor': 12, 'extra': {'now': 1786427452007, 'logid': '20260811135051B3CF2A10B3454408B627', 'search_request_id': ''}, 'has_more': 0, 'item_list': [], 'log_pb': {'impr_id': '20260811135051B3CF2A10B3454408B627'}, 'status_code': 0}
2026-08-11 05:50:52,134 - INFO - TikTok calls=3/3, count_per_call=50, valid samples=0
2026-08-11 05:50:52,134 - INFO - Fetching Amazon...
2026-08-11 05:50:54,190 - INFO - Amazon query 'acne skincare' -> 48 products (rating samples e.g. 9982)
2026-08-11 05:50:56,454 - INFO - Amazon query 'blemish serum' -> 48 products (rating samples e.g. 1230)
2026-08-11 05:50:58,602 - INFO - Amazon query 'pore care' -> 48 products (rating samples e.g. 736)
2026-08-11 05:50:58,602 - INFO - Amazon calls=3/3, count_per_call<=50, valid samples=144
2026-08-11 05:50:58,602 - INFO - Fetching Instagram (Scraper2)...
2026-08-11 05:50:58,866 - WARNING - Instagram Scraper2 #pdrn HTTP 204: 
2026-08-11 05:50:58,884 - WARNING - Instagram Scraper2 #polynucleotide HTTP 204: 
2026-08-11 05:50:58,912 - WARNING - Instagram Scraper2 #peptide HTTP 204: 
2026-08-11 05:50:58,931 - WARNING - Instagram Scraper2 #exosomeskincare HTTP 429: {"message":"You have exceeded the rate limit per minute for your plan, BASIC, by the API provider"}
2026-08-11 05:50:58,950 - WARNING - Instagram Scraper2 #ceramide HTTP 429: {"message":"You have exceeded the rate limit per minute for your plan, BASIC, by the API provider"}
2026-08-11 05:50:58,963 - WARNING - Instagram Scraper2 #ectoin HTTP 429: {"message":"You have exceeded the rate limit per minute for your plan, BASIC, by the API provider"}
2026-08-11 05:50:58,983 - WARNING - Instagram Scraper2 #centella HTTP 429: {"message":"You have exceeded the rate limit per minute for your plan, BASIC, by the API provider"}
2026-08-11 05:50:59,003 - WARNING - Instagram Scraper2 #cica HTTP 429: {"message":"You have exceeded the rate limit per minute for your plan, BASIC, by the API provider"}
2026-08-11 05:50:59,023 - WARNING - Instagram Scraper2 #snailmucin HTTP 429: {"message":"You have exceeded the rate limit per minute for your plan, BASIC, by the API provider"}
2026-08-11 05:50:59,048 - WARNING - Instagram Scraper2 #propolis HTTP 429: {"message":"You have exceeded the rate limit per minute for your plan, BASIC, by the API provider"}
2026-08-11 05:50:59,048 - INFO - Instagram Scraper2 calls=10/10, count_per_call=50, valid samples=0
2026-08-11 05:50:59,139 - INFO - Generating Gemini report...
2026-08-11 05:51:20,603 - INFO - Sending report section 1/3
2026-08-11 05:51:21,191 - INFO - Sending report section 2/3
2026-08-11 05:51:21,522 - INFO - Sending report section 3/3
2026-08-11 05:51:21,838 - INFO - === Daily Cosmetics Trend Bot Completed Successfully ===
1s
Run git config --local user.email "github-actions[bot]@users.noreply.github.com"
[main 685157c] auto: update beauty_trends.db [skip ci]
 1 file changed, 0 insertions(+), 0 deletions(-)
To https://github.com/seung602/daiy-trend-bot
   2cf8c47..685157c  main -> main
1s
Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
Post job cleanup.
Cache hit occurred on the primary key setup-python-Linux-x64-24.04-Ubuntu-python-3.10.20-pip-d44e08ac108f3a9ad37298f47c6360bc8913502a4a1ac567dc01be84311a6f4a, not saving cache.
(node:2133) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
0s
Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
Post job cleanup.
/usr/bin/git version
git version 2.54.0
Temporarily overriding HOME='/home/runner/work/_temp/9665a49e-4a97-4a28-b5f0-036a40d721a5' before making global git config changes
Adding repository directory to the temporary git global config as a safe directory
/usr/bin/git config --global --add safe.directory /home/runner/work/daiy-trend-bot/daiy-trend-bot
/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
http.https://github.com/.extraheader
/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
0s
Cleaning up orphan processes
Warning: Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
