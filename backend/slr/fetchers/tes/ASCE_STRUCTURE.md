"""
ASCE Library Search Results Structure Documentation
===================================================

Berdasarkan inspeksi browser real (Chrome), struktur HTML ASCE Library adalah:

URL Pattern:
-----------
https://ascelibrary.org/action/doSearch?AllField={query}&pageSize={limit}&startPage={page}

Search Results Container:
------------------------
- Main container: list [ref=e105]
- Each result: listitem [ref=e106, e155, e205, ...]

Paper Item Structure:
--------------------
listitem
  └─ generic
      ├─ checkbox (untuk select item)
      └─ generic (main content)
          ├─ generic (metadata header)
          │   ├─ generic: "Technical Papers|"
          │   ├─ generic: "May 13, 2023|"
          │   └─ generic: "Editor's Choice" (optional)
          │
          ├─ generic (paper details)
          │   ├─ link (title link)
          │   │   └─ heading[level=5]: Paper Title
          │   │       URL: /doi/10.1061/...
          │   │
          │   ├─ list[authors]
          │   │   └─ listitem (multiple)
          │   │       └─ link: Author Name
          │   │           URL: /authored-by/...
          │   │
          │   └─ paragraph
          │       ├─ text: "Journal Name"
          │       └─ generic: "Volume X, Issue Y"
          │
          └─ generic (actions)
              ├─ link "Abstract"
              └─ list
                  ├─ listitem: link to /doi/abs/...
                  ├─ listitem: link "Full text" to /doi/full/...
                  └─ listitem: link "PDF" to /doi/epdf/...

CSS Selectors yang Bekerja:
---------------------------
1. All results: 'list > listitem' atau 'li[role="listitem"]'
2. Title: 'heading[level="5"]' atau 'h5'
3. Title link: 'a[href*="/doi/"]' (yang mengandung heading)
4. Authors: 'list[aria-label="authors"] listitem a'
5. Journal: 'paragraph' (dalam paper details)
6. DOI: extract dari URL title link (/doi/10.1061/...)
7. Date: generic yang berisi pattern tanggal
8. Type: generic pertama dalam metadata header

Accessibility Tree Selectors (untuk Playwright):
-----------------------------------------------
- Results list: role=list
- Each result: role=listitem
- Title: role=heading[level=5]
- Authors: role=list[name="authors"]
- Links: role=link

Example Data:
------------
Title: "Leveraging Machine Learning for Pipeline Condition Assessment"
URL: /doi/10.1061/JPSEA2.PSENG-1464
Authors: ["Hongfang Lu", "Zhao-Dong Xu", "Xulei Zang", ...]
Journal: "Journal of Pipeline Systems Engineering and Practice"
Volume: "Volume 14, Issue 3"
Date: "May 13, 2023"
Type: "Technical Papers"
DOI: 10.1061/JPSEA2.PSENG-1464

Total Results Info:
------------------
Located in: generic [ref=e66]
Format: "1 - 20 of 14486 result for ' machine learning '"

Notes:
------
1. Cloudflare protection BLOCKS headless Playwright
2. Real Chrome browser successfully bypasses Cloudflare
3. Need to use stealth techniques or connect to real browser
4. Alternative: Use MCP Playwright browser tools instead of standalone Playwright
"""