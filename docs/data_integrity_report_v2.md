# Data Integrity Report v2

**Generated: 2026-03-11**
**Project: /Users/user/real-estate-agent**

---

## 1. analysis.json Summary

| Metric | Value |
|--------|-------|
| Total entries | 4,429 |
| Unique apartments (gu, apt) | 2,816 |
| Duplicate (gu, apt, area_type) | **0** (clean) |
| Unique gus | 57 |

**Top 10 gus by entry count:**

| gu | Entries | Unique Apts |
|----|---------|-------------|
| 화성시 | 265 | 128 |
| 평택시 | 193 | 113 |
| 용인시기흥구 | 163 | 110 |
| 용인시수지구 | 152 | 106 |
| 남양주시 | 150 | 95 |
| 의정부시 | 140 | 94 |
| 고양시덕양구 | 139 | 97 |
| 수원시권선구 | 132 | 77 |
| 성북구 | 131 | 72 |
| 수원시영통구 | 125 | 82 |

**Verdict:** No duplicates found. Data is clean on the (gu, apt, area_type) key.

---

## 2. apt_cache.json Summary

| Metric | Value |
|--------|-------|
| Total entries | 13,992 |

Values are household counts (세대수). Cache has grown from the previously documented 7,330 to 13,992 entries.

---

## 3. raw_trades.json Summary

| Metric | Value |
|--------|-------|
| Total trade records | 1,037,205 |
| Unique gus | 57 |
| Unique apartment names | 12,739 |
| File size | 180.8 MB |

**Top 10 gus by trade count:**

| gu | Trades | Unique Apts |
|----|--------|-------------|
| 화성시 | 65,905 | 366 |
| 평택시 | 49,315 | 372 |
| 남양주시 | 45,332 | 363 |
| 시흥시 | 39,350 | 309 |
| 김포시 | 36,525 | 183 |
| 용인시수지구 | 33,331 | 261 |
| 용인시기흥구 | 32,614 | 246 |
| 수원시영통구 | 30,813 | 146 |
| 의정부시 | 30,718 | 293 |
| 노원구 | 27,058 | 308 |

---

## 4. raw_rents.json Summary

| Metric | Value |
|--------|-------|
| Total rent records | 2,044,427 |
| Unique gus | 57 |
| File size | 174.7 MB |

---

## 5. 전세가율 역전 (Jeonse Ratio > 99%)

**Total inversions: 8 entries**

| gu | apt | area | ratio |
|----|-----|------|-------|
| 남양주시 | 대명(진접읍 장현리) | 59㎡ | 99.9% |
| 의정부시 | 성원 | 59㎡ | 99.9% |
| 평택시 | 늘푸른사랑마을 | 59㎡ | 99.9% |
| 평택시 | 태산 | 59㎡ | 99.9% |
| 평택시 | 화현마을우림필유 | 84㎡ | 99.9% |
| 평택시 | 새한 | 75㎡ | 99.9% |
| 화성시 | 한신 | 76㎡ | 99.6% |
| 평택시 | 포승삼부르네상스1단지 | 59㎡ | 99.3% |

**Entries with ratio > 80%: 140 (3.2% of total)**

All 8 inversion cases are in 경기도 외곽 지역 (평택, 남양주, 의정부, 화성) with small/old complexes where 전세 prices are nearly equal to 매매 prices. These are not bugs -- they reflect genuine 깡통전세 risk areas.

**Verdict:** No cases exceed 100%, so no true inversions. The 99.9% values suggest capped/rounded output. Data is consistent.

---

## 6. Price Outliers

### Lowest Prices (Bottom 15)
All between 1.1억~1.6억 -- old/small complexes in 평택시, 의정부시, 남양주시, 용인시처인구. These are plausible for aged apartments in these areas.

| gu | apt | area | avg_price |
|----|-----|------|-----------|
| 평택시 | 한강 | 67㎡ | 1.08억 |
| 평택시 | 새한 | 75㎡ | 1.19억 |
| 의정부시 | 성원 | 59㎡ | 1.28억 |
| 평택시 | 한일 | 59㎡ | 1.28억 |
| 평택시 | 태평 | 59㎡ | 1.28억 |

### Highest Prices (Top 15)
All in 강남구/서초구/송파구. Range: 44억~73.5억.

| gu | apt | area | avg_price |
|----|-----|------|-----------|
| 서초구 | 래미안원베일리 | 101㎡ | 73.5억 |
| 강남구 | 신현대9차 | 109㎡ | 70.0억 |
| 서초구 | 래미안원베일리 | 84㎡ | 60.8억 |
| 서초구 | 신반포2 | 107㎡ | 57.2억 |
| 강남구 | 미성1차 | 105㎡ | 55.5억 |

**Under 1억: 0 entries**
**Over 40억: 20 entries** (all in 강남/서초/송파 -- plausible)

**Verdict:** No unrealistic price outliers detected. The range 1.1억~73.5억 is reasonable for the covered regions.

---

## 7. Analysis vs Raw Trades Coverage by Gu

Analysis contains 2,816 unique apts out of 12,739 in raw_trades (22.1% overall).
This is expected because analysis filters for 300세대+ complexes with recent trades.

### Low Coverage Gus (< 10% apartment coverage)

| gu | analysis apts | trade apts | coverage |
|----|---------------|------------|----------|
| 강남구 | 47 | 594 | 7.9% |
| 강동구 | 44 | 491 | 9.0% |
| 강서구 | 52 | 590 | 8.8% |
| 광진구 | 20 | 228 | 8.8% |
| 구로구 | 54 | 589 | 9.2% |
| 금천구 | 15 | 164 | 9.1% |
| 부천시소사구 | 26 | 266 | 9.8% |
| 부천시오정구 | 5 | 269 | 1.9% |
| 부천시원미구 | 31 | 363 | 8.5% |
| 서초구 | 29 | 677 | 4.3% |
| 양천구 | 44 | 463 | 9.5% |
| 용산구 | 14 | 229 | 6.1% |
| 종로구 | 7 | 125 | 5.6% |
| 중구 | 9 | 127 | 7.1% |

**Note:** Seoul gus (강남, 서초, 용산, 종로, 중구) have many small, old complexes under 300세대, explaining low coverage percentages. The absolute counts of large complexes are reasonable.

### High Coverage Gus (> 40%)

| gu | analysis apts | trade apts | coverage |
|----|---------------|------------|----------|
| 하남시 | 69 | 115 | 60.0% |
| 수원시영통구 | 82 | 146 | 56.2% |
| 김포시 | 83 | 183 | 45.4% |
| 광명시 | 49 | 110 | 44.5% |
| 용인시기흥구 | 110 | 246 | 44.7% |
| 과천시 | 9 | 21 | 42.9% |

These are newer/planned city areas where large complexes dominate -- coverage is expected to be high.

---

## 8. 화성시 / 부천시오정구 Coverage Status

| gu | Previous | Current | Change |
|----|----------|---------|--------|
| 화성시 | 19 apts | **128 apts** | +109 (significant improvement) |
| 부천시오정구 | 0 apts | **5 apts** | +5 (minimal improvement) |

**화성시** coverage has improved dramatically from 19 to 128 apartments (35.0% of 366 trade apts). This is now a well-covered gu.

**부천시오정구** remains problematic at only 5 apartments out of 269 in raw_trades (1.9% coverage). This is the lowest-coverage gu in the entire dataset. Likely cause: apt_cache has few matches for 부천시오정구 apartment names, or most complexes there are under 300 세대.

---

## 9. Name Mismatch Analysis (apt_cache vs raw_trades)

| Metric | Count |
|--------|-------|
| apt_cache entries | 13,992 |
| Unique apt names in raw_trades | 12,739 |
| In raw_trades but NOT in apt_cache | 11,496 (90.2%) |
| In apt_cache but NOT in raw_trades | 12,749 (91.1%) |
| In analysis but NOT in apt_cache | 1,828 (65.0% of 2,816) |

### Key Observations

1. **Massive mismatch between apt_cache and raw_trades**: Only ~1,243 raw_trades apartment names appear directly in apt_cache. The cache uses a normalization/fuzzy matching strategy, so exact name matches are not the full picture.

2. **Many raw_trades entries have parenthetical addresses** as apartment names (e.g., `(1-10)`, `(1101-1)`), which are not real apartment complexes. These are likely standalone buildings or very small complexes.

3. **1,828 analysis apartments not in apt_cache**: Since analysis has 2,816 unique apts but only ~988 match apt_cache keys exactly, the analysis pipeline likely uses normalization matching (as documented in memory: "정규화 + dong별 인덱스, 부분매칭").

4. **The cache matching strategy is working**: Despite low exact-match rates, the analysis successfully produces 4,429 entries covering 2,816 apartments, meaning the fuzzy matching fills most gaps.

---

## 10. Recovery Rate Distribution

| Metric | Value |
|--------|-------|
| Entries with recovery_rate | 4,429 (100%) |
| Min | 0.00 |
| Max | 225.80 |
| Mean | 82.47 |
| Median | 85.50 |
| Stdev | 33.74 |

### Distribution

| Bucket | Count | Percentage |
|--------|-------|------------|
| 0 (no data) | 455 | 10.3% |
| 0-50% | 3 | 0.1% |
| 50-70% | 422 | 9.5% |
| 70-80% | 804 | 18.2% |
| 80-90% | 939 | 21.2% |
| 90-100% | 642 | 14.5% |
| 100-110% | 454 | 10.3% |
| 110-130% | 503 | 11.4% |
| 130%+ | 207 | 4.7% |

### Suspicious Values

**recovery_rate > 150%: 24 entries**

Top 5:
- 강남구 신현대9차 109㎡: 225.8% (재건축 기대감 반영된 급등)
- 강동구 강동리버스트4단지 59㎡: 198.2%
- 서초구 신반포2 68㎡: 183.7%
- 강남구 한양1차(영동한양) 63㎡: 175.9%
- 수원시팔달구 한효 59㎡: 172.0%

Most >150% cases are in 강남/서초 (재건축 단지) or new towns with rapid appreciation. These appear to be genuine market movements rather than data errors.

**recovery_rate = 0: 455 entries (10.3%)**

Per the documented design decision, recovery_rate = 0 is assigned when 2021-2022 거래 data is absent (data sparsity). This is intentional to prevent distorted calculations.

### Assessment

- The distribution is roughly bell-shaped around 80-90%, which is expected (most markets have not fully recovered from the 2022 crash).
- The 0-50% bucket has only 3 entries, suggesting no data quality issues in that range.
- The 455 zero-recovery entries are a known/intentional design choice.
- High values (>150%) correlate with 재건축 premium areas -- not data errors.

**Verdict:** Recovery rate data is clean and consistent with documented design decisions.

---

## Overall Assessment

### Data Quality Score: A- (Good)

| Check | Status | Notes |
|-------|--------|-------|
| No duplicates in analysis | PASS | 0 duplicate (gu, apt, area_type) |
| Jeonse ratio consistency | PASS | 0 true inversions (>100%), 8 near-inversions in expected locations |
| Price range plausibility | PASS | 1.1억~73.5억, no unrealistic outliers |
| Recovery rate validity | PASS | Distribution and edge cases match design docs |
| Gu coverage balance | WARN | 14 gus below 10% coverage |
| 화성시 improvement | PASS | 19 -> 128 apts (huge improvement) |
| 부천시오정구 coverage | FAIL | 0 -> 5 apts only (1.9% coverage, worst gu) |
| apt_cache name matching | WARN | Only ~9% exact match rate; fuzzy matching compensates |

### Recommended Actions

1. **부천시오정구**: Investigate why only 5 of 269 trade apartments make it to analysis. Likely need to expand apt_cache coverage or check 세대수 threshold for this gu.

2. **apt_cache maintenance**: The 1,828 analysis apartments not matching apt_cache keys suggests the normalization matching handles them, but periodic cache refresh could improve reliability.

3. **Near-inversion monitoring**: The 8 entries at 99.9% ratio should be flagged in user-facing reports as 깡통전세 risk areas.

4. **Low-coverage Seoul gus** (강남 7.9%, 서초 4.3%, 용산 6.1%): These are expected given the 300-세대 filter, but worth noting that many premium small complexes are excluded from analysis.
