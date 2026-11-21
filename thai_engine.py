# -*- coding: utf-8 -*-
"""THAI LOTTERY AI - Thai Government Lottery statistical research engine.

Ranking logic is based on the LAO DEVELOPMENT AI statistical engine.
Thai lottery prize fields are parsed independently and kept in their own CSV.
Scores are relative ranking scores, not probabilities or guarantees.
"""
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAO DEVELOPMENT AI v1.3 WEEKDAY - Monday-Friday ThaiORC statistical research engine.

Keeps all fetched data and filters Monday-Friday for summaries, rankings, and backtests.
This program ranks historical patterns; it does not predict or guarantee lottery results.
SSL certificate verification remains enabled.
"""
import argparse
import csv
import itertools
import math
import re
import ssl
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen

START_URL = 'https://thaiorc.com/lotto/lao/stats/lottery-years10.php'
FALLBACK_URLS = [
    'https://lotto.thaiorc.com/lao/last3/stats-years10.php',
    'https://lotto.thaiorc.com/lao/stats/lottery-years10.php',
]
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 Chrome/120 Safari/537.36'

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None; self.links=[]; self._href=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag == 'table': self.table=[]
        elif tag == 'tr' and self.table is not None: self.row=[]
        elif tag in ('td','th') and self.row is not None: self.cell=[]
        if tag == 'a' and a.get('href'): self._href=a['href']
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        elif tag == 'tr' and self.row is not None:
            if self.row: self.table.append(self.row)
            self.row=None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table); self.table=None
        elif tag == 'a' and self._href:
            self.links.append(self._href); self._href=None

def parse_date(value):
    m=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', str(value))
    if not m: raise ValueError('รูปแบบวันที่ไม่ถูกต้อง: '+str(value))
    d,mo,y=map(int,m.groups())
    return datetime(y-543 if y>2400 else y,mo,d)

def make_row(date_text, six):
    six=str(six).strip()
    if not re.fullmatch(r'\d{6}',six): return None
    dt=parse_date(date_text)
    return {'date':dt,'six':six,'top3':six[-3:],'top2':six[-2:],'bottom2':six[-4:-2]}

def extract_rows(html):
    parser=PageParser(); parser.feed(html); found=[]
    for table in parser.tables:
        for row in table:
            if len(row)<5: continue
            if not re.search(r'\d{1,2}/\d{1,2}/\d{4}',row[0]): continue
            r=make_row(row[0],row[1])
            if not r: continue
            # Verify the page's published derived columns before accepting a row.
            supplied=[re.sub(r'\D','',x) for x in row[2:5]]
            expected=[r['top3'],r['top2'],r['bottom2']]
            if all(supplied) and [x.zfill(len(e)) for x,e in zip(supplied,expected)] != expected:
                continue
            found.append(r)
    return found, parser.links

def fetch(url, context):
    req=Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html,application/xhtml+xml'})
    with urlopen(req,timeout=25,context=context) as response:
        return response.read().decode('utf-8','replace'), response.geturl()

def from_web(years=10, max_pages=50):
    context=ssl.create_default_context()
    try:
        import certifi
        context=ssl.create_default_context(cafile=certifi.where())
    except ImportError: pass
    base=START_URL if years==10 else START_URL.replace('years10',f'years{years}')
    errors=[]; rows_by_date={}; successful_base=None
    # Try canonical page first, then known ThaiORC legacy mirrors.
    for candidate in [base]+FALLBACK_URLS:
        try:
            html, final_url=fetch(candidate,context)
            page_rows, links=extract_rows(html)
            if page_rows:
                successful_base=final_url; rows_by_date.update({r['date']:r for r in page_rows}); break
            errors.append(f'{candidate}: ไม่พบตารางผลรางวัล')
        except Exception as exc: errors.append(f'{candidate}: {exc}')
    if not successful_base:
        raise RuntimeError('เชื่อมต่อ/อ่านข้อมูล ThaiORC ไม่สำเร็จ\n'+'\n'.join(errors))

    # Follow explicit pagination links when available; also probe common pg/page parameters.
    parser_links=[]
    try:
        first_html,_=fetch(successful_base,context); _,parser_links=extract_rows(first_html)
    except Exception: pass
    pagination=[]
    for href in parser_links:
        absolute=urljoin(successful_base,href)
        q=parse_qs(urlparse(absolute).query)
        if ('pg' in q or 'page' in q) and urlparse(absolute).netloc==urlparse(successful_base).netloc:
            pagination.append(absolute)
    candidates=list(dict.fromkeys(pagination))
    if not candidates:
        clean=successful_base.split('?')[0]
        candidates=[f'{clean}?pg={i}' for i in range(2,max_pages+1)]
        candidates += [f'{clean}?page={i}' for i in range(2,max_pages+1)]
    seen_urls={successful_base}; empty_streak=0
    for page_url in candidates:
        if page_url in seen_urls: continue
        seen_urls.add(page_url)
        try:
            html,_=fetch(page_url,context); page_rows,_=extract_rows(html)
            new=0
            for r in page_rows:
                if r['date'] not in rows_by_date: rows_by_date[r['date']]=r; new+=1
                elif rows_by_date[r['date']]['six'] != r['six']:
                    raise ValueError('ผลรางวัลวันที่ซ้ำแต่เลขไม่ตรงกัน: '+r['date'].strftime('%d/%m/%Y'))
            empty_streak=empty_streak+1 if new==0 else 0
            if empty_streak>=2: break
            time.sleep(0.15)
        except (HTTPError,URLError,TimeoutError):
            # Page beyond the available range is normal; stop probing after a failed page.
            if not pagination: break
        except Exception as exc:
            print(f'[คำเตือน] ข้ามหน้า {page_url}: {exc}',file=sys.stderr)
    rows=sorted(rows_by_date.values(),key=lambda r:r['date'])
    if not rows: raise RuntimeError('ไม่พบข้อมูลงวด')
    # Keep draws in the requested rolling year range, based on latest draw date.
    cutoff=rows[-1]['date'].replace(year=rows[-1]['date'].year-years)
    rows=[r for r in rows if r['date']>=cutoff]
    return rows, successful_base

def from_csv(path):
    rows=[]
    with open(path,encoding='utf-8-sig',newline='') as f:
        for item in csv.DictReader(f):
            date=item.get('date_be') or item.get('date')
            six=item.get('first_prize') or item.get('six_digits') or item.get('six')
            if not date or not six: raise ValueError('CSV ต้องมีคอลัมน์ date_be และ first_prize (เลข 6 หลัก)')
            r=make_row(date,six)
            if not r: raise ValueError('เลขรางวัลต้องเป็นตัวเลข 6 หลัก: '+str(six))
            rows.append(r)
    return dedupe(rows)

def dedupe(rows):
    data={}
    for r in rows:
        if r['date'] in data and data[r['date']]['six']!=r['six']:
            raise ValueError('พบผลรางวัลวันที่ซ้ำแต่ไม่ตรงกัน')
        data[r['date']]=r
    return sorted(data.values(),key=lambda r:r['date'])

def kind(s):
    c=Counter(s)
    max_count=max(c.values())
    # Correctly classify repeated patterns by the length of the number.
    if len(s)==2 and max_count==2: return 'เบิ้ล'
    if len(s)==3 and max_count==3: return 'ตอง'
    if len(s)>=4 and len(c)==1: return 'เหมือนกันทั้งหมด'
    if max_count>=3: return 'มีตอง'
    if sum(v==2 for v in c.values())>=2: return 'เบิ้ลคู่'
    if max_count==2: return 'เบิ้ล'
    return 'เลขเดี่ยว'

def build_model(rows, field):
    seq=[r[field] for r in rows]; k=len(seq[0]); n=len(seq)
    pos=[Counter(s[i] for s in seq) for i in range(k)]
    all_digits=Counter(''.join(seq)); recent_seq=seq[-min(30,n):]
    recent_pos=[Counter(s[i] for s in recent_seq) for i in range(k)]
    pair_counts=[Counter(s[i:i+2] for s in seq) for i in range(k-1)]
    double_counts=Counter(kind(s) for s in seq)
    transition=[Counter() for _ in range(k)]
    for a,b in zip(seq,seq[1:]):
        for i in range(k): transition[i][(a[i],b[i])]+=1
    return {'seq':seq,'k':k,'n':n,'pos':pos,'all':all_digits,'recent_pos':recent_pos,
            'pairs':pair_counts,'double':double_counts,'transition':transition,'last':seq[-1]}

def raw_score(s,m):
    n=m['n']; k=m['k']; recent_n=min(30,n); terms=[]
    freq=sum(math.log((m['pos'][i][d]+1)/(n+10)) for i,d in enumerate(s))/k
    recent=sum(math.log((m['recent_pos'][i][d]+1)/(recent_n+10)) for i,d in enumerate(s))/k
    pair=sum(math.log((m['pairs'][i][s[i:i+2]]+1)/(n+100)) for i in range(k-1))/max(1,k-1)
    trans=sum(math.log((m['transition'][i][(m['last'][i],d)]+1)/(n+10)) for i,d in enumerate(s))/k
    # A modest, explicit double-pattern contribution; it does not force doubles into every list.
    double=math.log((m['double'][kind(s)]+1)/(n+5))
    return .45*freq + .25*recent + .15*pair + .10*trans + .05*double

def candidates_for(k, beam_size=1800):
    if k<=3: return (''.join(p) for p in itertools.product('0123456789',repeat=k))
    beam=['']
    for pos in range(k):
        expanded=[prefix+d for prefix in beam for d in '0123456789']
        if pos==k-1: return iter(expanded)
        # Broad, deterministic beam; partial scoring will be applied by rank_sets.
        beam=expanded[:]
        if len(beam)>beam_size:
            # Keep broad digit/position diversity rather than only one repeated prefix.
            beam=sorted(beam,key=lambda x:(sum(int(ch) for ch in x)%17,x))[:beam_size]
    return iter(beam)

def rank_sets(rows, field, limit=10, beam_size=1800):
    m=build_model(rows,field); k=m['k']
    if k<=3: pool=list(candidates_for(k))
    else:
        # Generate a manageable beam using per-position frequencies and pair co-occurrence.
        beam=['']
        for i in range(k):
            expanded=[p+d for p in beam for d in '0123456789']
            if i==k-1: beam=expanded; break
            def partial(s):
                val=0.0
                for j,d in enumerate(s): val+=math.log((m['pos'][j][d]+1)/(m['n']+10))
                for j in range(len(s)-1): val+=.35*math.log((m['pairs'][j][s[j:j+2]]+1)/(m['n']+100))
                # Preserve repeat structures as valid candidates, not as mandatory choices.
                return val
            beam=sorted(expanded,key=lambda s:(-partial(s),s))[:beam_size]
        pool=beam
    scored=[(s,raw_score(s,m)) for s in pool]
    scored.sort(key=lambda x:(-x[1],x[0]))
    top=scored[:limit]
    vals=[v for _,v in scored]
    lo=min(vals); hi=max(vals)
    # Relative ranking score (0-100) among candidates in this run; not a probability.
    out=[]
    for s,v in top:
        normalized=50.0 if math.isclose(hi,lo) else 100*(v-lo)/(hi-lo)
        out.append({'number':s,'raw':v,'score':round(normalized,1),'type':kind(s)})
    return out

def digit_summary(rows, field='six'):
    seq=[r[field] for r in rows]; n=len(seq); k=len(seq[0])
    pos=[Counter(s[i] for s in seq) for i in range(k)]
    overall=Counter(''.join(seq))
    ranked=overall.most_common()
    return pos,overall,ranked

def backtest(rows, windows=(20,40,60,100), top_n=10):
    print('\n'+'='*72+'\nWALK-FORWARD BACKTEST | ไม่ใช้ข้อมูลงวดอนาคต')
    print('วัดผล exact match ของ Top 10; เป็นการทดสอบย้อนหลัง ไม่ใช่การรับประกัน')
    for window in windows:
        available=min(window,max(0,len(rows)-30))
        if available<1:
            print(f'ช่วง {window} งวด: ข้อมูลไม่พอ (มี {len(rows)} งวด; ต้องมีอย่างน้อย 31 งวด)')
            continue
        start=len(rows)-available; print(f'\nช่วงทดสอบล่าสุด {available} งวด (ตั้งค่าขอ {window})')
        for field,label in [('top2','2 ตัวบน'),('bottom2','2 ตัวล่าง'),('top3','3 ตัวบน')]:
            hits=0; tested=0
            for idx in range(start,len(rows)):
                train=rows[:idx]
                picks={x['number'] for x in rank_sets(train,field,top_n,beam_size=450)}
                hits += rows[idx][field] in picks; tested += 1
            print(f'  {label}: {hits}/{tested} = {hits/tested:.2%} | baseline สุ่ม Top {top_n}: {top_n/(10**len(rows[0][field])):.2%}')


def normalize_scores(scored):
    """Convert raw scores to relative 0-100 ranks for one candidate pool."""
    if not scored:
        return []
    vals=[v for _,v in scored]
    lo,hi=min(vals),max(vals)
    out=[]
    for number,value in sorted(scored,key=lambda x:(-x[1],x[0])):
        score=50.0 if math.isclose(hi,lo) else 100.0*(value-lo)/(hi-lo)
        out.append({'number':number,'raw':value,'score':round(score,1),'type':kind(number)})
    return out


def rank_daily_sets(rows, field, limit=10, window=20):
    """Daily-only ranking: recent rolling window, anchored to the latest known draw."""
    clean=dedupe(rows)
    if len(clean)<5:
        raise ValueError("ข้อมูลไม่เพียงพอสำหรับ Daily Engine (ต้องมีอย่างน้อย 5 งวด)")
    recent=clean[-min(window,len(clean)):]
    model=build_model(recent,field)
    k=model['k']
    if k<=3:
        pool=list(candidates_for(k))
    else:
        # Use the same candidate generation policy as the original engine.
        beam=['']
        beam_size=1800
        for pos in range(k):
            expanded=[prefix+d for prefix in beam for d in '0123456789']
            if pos==k-1:
                beam=expanded
                break
            def partial(s):
                val=0.0
                for j,d in enumerate(s):
                    val += math.log((model['pos'][j][d]+1)/(model['n']+10))
                for j in range(len(s)-1):
                    val += .35*math.log((model['pairs'][j][s[j:j+2]]+1)/(model['n']+100))
                return val
            beam=sorted(expanded,key=lambda s:(-partial(s),s))[:beam_size]
        pool=beam
    return normalize_scores([(s,raw_score(s,model)) for s in pool[:]] )[:limit]


def rank_hybrid_sets(historical_rows, all_rows, field, limit=10, window=20,
                     historical_weight=.60):
    """Blend selected-weekday history with the rolling all-weekday Daily Engine."""
    hist=dedupe(historical_rows)
    all_clean=dedupe(all_rows)
    if len(hist)<5 or len(all_clean)<5:
        raise ValueError("ข้อมูลไม่เพียงพอสำหรับ Hybrid Engine")
    recent=all_clean[-min(window,len(all_clean)):]
    hist_model=build_model(hist,field)
    daily_model=build_model(recent,field)
    k=hist_model['k']
    if k<=3:
        pool=list(candidates_for(k))
    else:
        # Candidate pool is seeded from both engines to avoid excluding a daily signal.
        pool=set()
        for model in (hist_model,daily_model):
            beam=['']
            for pos in range(k):
                expanded=[prefix+d for prefix in beam for d in '0123456789']
                if pos==k-1:
                    beam=expanded
                    break
                def partial(s, m=model):
                    val=0.0
                    for j,d in enumerate(s):
                        val += math.log((m['pos'][j][d]+1)/(m['n']+10))
                    for j in range(len(s)-1):
                        val += .35*math.log((m['pairs'][j][s[j:j+2]]+1)/(m['n']+100))
                    return val
                beam=sorted(expanded,key=lambda s:(-partial(s),s))[:1800]
            pool.update(beam)
        pool=sorted(pool)
    scored=[]
    for number in pool:
        hs=raw_score(number,hist_model)
        ds=raw_score(number,daily_model)
        scored.append((number,historical_weight*hs+(1-historical_weight)*ds))
    return normalize_scores(scored)[:limit]


def run_engine_comparison(rows, selected_rows, window=20, top_n=10, test_count=30):
    """Walk-forward comparison. Each test draw is predicted only from earlier rows."""
    all_rows=dedupe(rows)
    selected=dedupe(selected_rows)
    selected_dates={r['date'] for r in selected}
    eligible=[i for i,r in enumerate(all_rows) if r['date'] in selected_dates]
    eligible=eligible[-min(test_count,len(eligible)):]
    metrics={name:{field:[0,0] for field in ('top2','bottom2','top3')}
             for name in ('Historical','Daily','Hybrid')}
    for idx in eligible:
        if idx<10:
            continue
        train_all=all_rows[:idx]
        target=all_rows[idx]
        train_selected=[r for r in train_all if r['date'].weekday()==target['date'].weekday()]
        if len(train_selected)<5:
            continue
        for field in ('top2','bottom2','top3'):
            try:
                picks={
                    'Historical':{x['number'] for x in rank_sets(train_selected,field,top_n,beam_size=450)},
                    'Daily':{x['number'] for x in rank_daily_sets(train_all,field,top_n,window=window)},
                    'Hybrid':{x['number'] for x in rank_hybrid_sets(train_selected,train_all,field,top_n,window=window)}
                }
            except (ValueError, IndexError):
                continue
            for engine in metrics:
                metrics[engine][field][1]+=1
                metrics[engine][field][0]+=int(target[field] in picks[engine])
    return metrics


def print_rank(label, rows, field, limit=10):
    print(f'\n{label} | TOP {limit} | รวมเลขซ้ำ/เบิ้ล')
    for i,x in enumerate(rank_sets(rows,field,limit),1):
        print(f" {i:2}. {x['number']}  score={x['score']:5.1f}/100  [{x['type']}]")

def save_csv(rows,path):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['date_be','first_prize','top3','top2','bottom2'])
        for r in rows:
            d=r['date']; w.writerow([f'{d.day:02d}/{d.month:02d}/{d.year+543}',r['six'],r['top3'],r['top2'],r['bottom2']])

WEEKDAY_NAMES = ['วันจันทร์','วันอังคาร','วันพุธ','วันพฤหัสบดี','วันศุกร์',
                 'วันเสาร์','วันอาทิตย์']

def filter_weekday(rows, weekday):
    """Filter Python weekday 0..4; 'all' means Monday-Friday combined."""
    clean = dedupe(rows)
    if weekday == 'all':
        return [r for r in clean if r['date'].weekday() < 5]
    return [r for r in clean if r['date'].weekday() == int(weekday)]

def weekday_counts(rows):
    counts=Counter(r['date'].weekday() for r in rows)
    return [(WEEKDAY_NAMES[i],counts[i]) for i in range(5)]

# Thai Government Lottery source configuration
THAI_START_URL = "https://lotto.thaiorc.com/thai/stats/lottery-years10.php"
THAI_FALLBACK_URLS = [
    "https://lotto.thaiorc.com/thai/lottery.php",
]
THAI_USER_AGENT = USER_AGENT

def make_thai_row(date_text, cells):
    """Parse one ThaiORC row: date, first prize, last2, two front3, two back3."""
    dt = parse_date(date_text)
    vals = [re.sub(r"\s+", "", str(x)) for x in cells]
    vals = [x for x in vals if x]
    if len(vals) < 4:
        return None
    six = re.sub(r"\D", "", vals[0])
    last2 = re.sub(r"\D", "", vals[1])
    front = re.findall(r"\d{3}", vals[2])
    back = re.findall(r"\d{3}", vals[3])
    # Some page layouts split the two 3-digit prizes into separate cells.
    if len(vals) >= 7:
        front = re.findall(r"\d{3}", " ".join(vals[2:4]))
        back = re.findall(r"\d{3}", " ".join(vals[4:6]))
    if len(six) != 6 or len(last2) != 2 or len(front) < 2 or len(back) < 2:
        return None
    return {
        "date": dt, "six": six, "last2": last2,
        "front3_1": front[0], "front3_2": front[1],
        "back3_1": back[0], "back3_2": back[1],
        "top3": six[-3:], "top2": six[-2:], "bottom2": last2,
    }

def extract_thai_rows(html):
    parser = PageParser()
    parser.feed(html)
    found = []
    for table in parser.tables:
        for row in table:
            if len(row) < 5 or not re.search(r"\d{1,2}/\d{1,2}/\d{4}", row[0]):
                continue
            # ThaiORC table columns: date | first prize | last 2 | front 3 (2 prizes) | back 3 (2 prizes)
            cells = row[1:]
            parsed = make_thai_row(row[0], cells)
            if parsed:
                found.append(parsed)
    return found, parser.links

def fetch_thai(url, context):
    req = Request(url, headers={"User-Agent": THAI_USER_AGENT,
                                "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=25, context=context) as response:
        return response.read().decode("utf-8", "replace"), response.geturl()

def dedupe_thai(rows):
    data = {}
    for r in rows:
        key = r["date"]
        if key in data and data[key]["six"] != r["six"]:
            raise ValueError("พบวันที่ซ้ำแต่ผลรางวัลที่ 1 ไม่ตรงกัน")
        data[key] = r
    return sorted(data.values(), key=lambda x: x["date"])

def from_thai_web(years=10, max_pages=50):
    context = ssl.create_default_context()
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    errors, rows_by_date, successful_base = [], {}, None
    for candidate in [THAI_START_URL] + THAI_FALLBACK_URLS:
        try:
            html, final_url = fetch_thai(candidate, context)
            page_rows, _ = extract_thai_rows(html)
            if page_rows:
                successful_base = final_url
                rows_by_date.update({r["date"]: r for r in page_rows})
                break
            errors.append(f"{candidate}: ไม่พบตารางผลหวยไทย")
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    if not successful_base:
        raise RuntimeError("ดึงข้อมูล ThaiORC ไม่สำเร็จ\n" + "\n".join(errors))

    # ThaiORC exposes historical year-range pages. Probe common pagination parameters.
    clean = successful_base.split("?")[0]
    candidates = []
    for param in ("pg", "page"):
        candidates.extend(f"{clean}?{param}={i}" for i in range(2, max_pages + 1))
    seen, empty_streak = {successful_base}, 0
    for page_url in candidates:
        if page_url in seen:
            continue
        seen.add(page_url)
        try:
            html, _ = fetch_thai(page_url, context)
            page_rows, _ = extract_thai_rows(html)
            new = 0
            for r in page_rows:
                if r["date"] not in rows_by_date:
                    rows_by_date[r["date"]] = r
                    new += 1
                elif rows_by_date[r["date"]]["six"] != r["six"]:
                    raise ValueError("ผลรางวัลวันที่ซ้ำแต่ไม่ตรงกัน")
            empty_streak = empty_streak + 1 if new == 0 else 0
            if empty_streak >= 2:
                break
            time.sleep(0.12)
        except (HTTPError, URLError, TimeoutError):
            break
        except Exception as exc:
            print(f"[คำเตือน] ข้ามหน้า {page_url}: {exc}", file=sys.stderr)

    rows = dedupe_thai(list(rows_by_date.values()))
    if not rows:
        raise RuntimeError("ไม่พบข้อมูลงวดหวยรัฐบาลไทย")
    cutoff = rows[-1]["date"].replace(year=rows[-1]["date"].year - years)
    return [r for r in rows if r["date"] >= cutoff], successful_base

def from_thai_csv(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for item in csv.DictReader(f):
            date = item.get("date_be") or item.get("date")
            six = item.get("first_prize") or item.get("six")
            last2 = item.get("last2") or item.get("last_2_digits")
            front1 = item.get("front3_1") or item.get("front3_a")
            front2 = item.get("front3_2") or item.get("front3_b")
            back1 = item.get("back3_1") or item.get("back3_a")
            back2 = item.get("back3_2") or item.get("back3_b")
            if not all([date, six, last2, front1, front2, back1, back2]):
                raise ValueError("CSV ต้องมี date_be, first_prize, last2, front3_1, front3_2, back3_1, back3_2")
            cells = [six, last2, f"{front1} {front2}", f"{back1} {back2}"]
            row = make_thai_row(date, cells)
            if not row:
                raise ValueError(f"ข้อมูลรางวัลไม่ถูกต้องในวันที่ {date}")
            rows.append(row)
    return dedupe_thai(rows)

def save_thai_csv(rows, path):
    close_after = False
    if isinstance(path, (str, Path)):
        f = open(path, "w", encoding="utf-8-sig", newline="")
        close_after = True
    else:
        f = path
    try:
        writer = csv.writer(f)
        writer.writerow(["date_be", "first_prize", "last2", "front3_1", "front3_2",
                         "back3_1", "back3_2"])
        for r in dedupe_thai(rows):
            d = r["date"]
            writer.writerow([f"{d.day:02d}/{d.month:02d}/{d.year+543}",
                             r["six"], r["last2"], r["front3_1"], r["front3_2"],
                             r["back3_1"], r["back3_2"]])
    finally:
        if close_after:
            f.close()

def expand_prize_rows(rows, field):
    """Flatten the two front/back 3-digit prizes into independent observations."""
    if field in ("front3", "back3"):
        return [{**r, "value": r[field + "_1"]} for r in rows] + [
            {**r, "value": r[field + "_2"]} for r in rows
        ]
    if field == "last2":
        return [{**r, "value": r["last2"]} for r in rows]
    if field == "top2":
        # 2 ตัวบน is derived from the final two digits of the first prize.
        return [{**r, "value": r["six"][-2:]} for r in rows]
    if field == "six":
        return [{**r, "value": r["six"]} for r in rows]
    if field in ("suffix5", "suffix4"):
        n = 5 if field == "suffix5" else 4
        return [{**r, "value": r["six"][-n:]} for r in rows]
    raise ValueError("ประเภทเลขไม่รองรับ: " + field)

def rank_thai(rows, field, limit=10, mode="historical", window=20):
    data = expand_prize_rows(rows, field)
    if len(data) < 5:
        raise ValueError("ข้อมูลไม่เพียงพอสำหรับการวิเคราะห์ (อย่างน้อย 5 รายการ)")
    model_rows = [{**r, "analysis": r["value"]} for r in data]
    if mode == "daily":
        return rank_daily_sets(model_rows, "analysis", limit, window)
    if mode == "hybrid":
        return rank_hybrid_sets(model_rows, model_rows, "analysis", limit, window, .60)
    return rank_sets(model_rows, "analysis", limit)

def thai_backtest(rows, top_n=10, test_count=30):
    """Walk-forward exact-match tests for each prize group."""
    clean = dedupe_thai(rows)
    result = {}
    fields = [("รางวัลที่ 1", "six"), ("2 ตัวบน (ท้ายรางวัลที่ 1)", "top2"),
              ("เลขท้าย 2 ตัว (รางวัลจริง)", "last2"),
              ("เลขหน้า 3 ตัว", "front3"), ("เลขท้าย 3 ตัว", "back3")]
    for label, field in fields:
        hits = tested = 0
        start = max(10, len(clean) - test_count)
        for idx in range(start, len(clean)):
            train = clean[:idx]
            target = clean[idx]
            try:
                picks = {x["number"] for x in rank_thai(train, field, top_n, "historical")}
            except (ValueError, IndexError):
                continue
            actual = ([target["six"]] if field == "six" else
                      [target["six"][-2:]] if field == "top2" else
                      [target["last2"]] if field == "last2" else
                      [target[field + "_1"], target[field + "_2"]])
            hits += int(any(x in picks for x in actual))
            tested += 1
        result[label] = (hits, tested)
    return result
