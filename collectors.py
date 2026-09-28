import os,re,requests,logging
from bs4 import BeautifulSoup
from dateutil import parser as dtparse
from urllib.parse import urljoin
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

UA=os.getenv('USER_AGENT','ProjectExitPlan-CompetitionLab/0.1.2')
TIMEOUT=int(os.getenv('REQUEST_TIMEOUT_SECONDS','20'))
HEAD={'User-Agent':UA}
UK=ZoneInfo('Europe/London')

def get(url):
    r=requests.get(url,headers=HEAD,timeout=TIMEOUT); r.raise_for_status(); return r.text

def _title(soup,url):
    h=soup.find('h1')
    if h:return ' '.join(h.stripped_strings)
    return url.rstrip('/').split('/')[-1].replace('-',' ').title()

def _scope(title,text):
    low=(title+' '+text[:2500]).lower()
    research=['instant win','instant wins','every ticket wins','site credit','golden ticket',
              'worth of tickets','ticket bundle','tickets into','spin to win','cash alternative',
              ' or £',' plus £',' + £']
    if any(x in low for x in research):
        return 'research'
    # Live universe is now deliberately narrow: the named end prize itself must be cash.
    return 'eligible' if re.search(r'win\s*£\s*[\d,]+(?:\.\d+)?\s*(?:tax[- ]?free\s*)?cash\b',title or '',re.I) else 'research'

def _cash_value(title,text):
    # Explicit cash alternative is strongest evidence.
    patterns=[
      r'(?:cash alternative|or)\s*:?[–\-]?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:tax[- ]?free\s*)?cash',
      r'£\s*([\d,]+(?:\.\d+)?)\s*(?:tax[- ]?free\s*)?cash\s*(?:alternative)?',
      r'win\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:tax[- ]?free\s*)?cash',
    ]
    hay=title+' '+text[:4000]
    vals=[]
    for p in patterns:
        for m in re.finditer(p,hay,re.I): vals.append(float(m.group(1).replace(',','')))
    return max(vals) if vals else None

def kilted():
    base='https://www.kiltedcompetitions.co.uk/competitions/'
    soup=BeautifulSoup(get(base),'html.parser'); out=[]; seen=set()
    for a in soup.select('a[href*="/product/"]'):
        url=a.get('href')
        if not url or url in seen: continue
        seen.add(url)
        try:
            ps=BeautifulSoup(get(url),'html.parser'); title=_title(ps,url); text=' '.join(ps.stripped_strings)
            pm=re.search(r'£\s*([\d,.]+)\s*Per Entry',text,re.I)
            # Kilted exposes both "sold < max" and "max tickets available / remaining".
            sr=re.search(r'([\d,]+)\s*<\s*([\d,]+)',text)
            maxm=re.search(r'([\d,]+)\s+tickets available',text,re.I)
            remm=re.search(r'([\d,]+)\s+tickets remaining',text,re.I)
            max_t=int(maxm.group(1).replace(',','')) if maxm else (int(sr.group(2).replace(',','')) if sr else None)
            if sr: sold=int(sr.group(1).replace(',',''))
            elif max_t is not None and remm: sold=max_t-int(remm.group(1).replace(',',''))
            else: sold=None
            cm=re.search(r'Live draw\s*/\s*(.+?\d{4}\s*@\s*\d{1,2}:\d{2}\s*[AP]M)',text,re.I)
            closes=dtparse.parse(cm.group(1).replace('@',' '),dayfirst=True) if cm else None
            if closes is not None and closes.tzinfo is None: closes=closes.replace(tzinfo=UK)
            guaranteed=('if all tickets do not sell out' in text.lower() and 'regardless' in text.lower()) or ('guaranteed draw' in text.lower() and 'no extension' in text.lower())
            scope=_scope(title,text)
            prize=_cash_value(title,'') if scope=='eligible' else None
            out.append(dict(operator='kilted',external_id=url.rstrip('/').split('/')[-1],title=title[:300],url=url,
                prize=prize,price=float(pm.group(1).replace(',','')) if pm else None,sold=sold,max_tickets=max_t,
                closes=closes,guaranteed=guaranteed,scope=scope))
        except Exception as e:
            out.append(dict(operator='kilted',external_id=url.rstrip('/').split('/')[-1],title=url,url=url,error=str(e),scope='research'))
    return out


def _parse_generic_product(operator,url,guarantee_phrases=()):
    ps=BeautifulSoup(get(url),'html.parser'); title=_title(ps,url); raw=' '.join(ps.stripped_strings)
    # Price variants used across UK competition sites.
    pm=(re.search(r'£\s*([\d,.]+)\s*(?:Per Entry|per entry|each)',raw,re.I)
        or re.search(r'(?:Entry|Ticket Price|Price)\s*:?\s*£\s*([\d,.]+)',raw,re.I))
    # Exact sold/max pairs.
    sr=(re.search(r'Tickets Sold\s*:?\s*([\d,]+)\s*(?:of|/)\s*([\d,]+)',raw,re.I)
        or re.search(r'Sold\s*:?\s*([\d,]+)\s*/\s*([\d,]+)',raw,re.I))
    sold=int(sr.group(1).replace(',','')) if sr else None
    max_t=int(sr.group(2).replace(',','')) if sr else None
    if max_t is None:
        tm=re.search(r'(?:Tickets|Entries)\s*:?\s*([\d,]+)\s*(?:entries\s+in\s+total|in total|total)',raw,re.I)
        if tm: max_t=int(tm.group(1).replace(',',''))
    rem=re.search(r'(?:Tickets Remaining|Remaining Tickets)\s*:?\s*([\d,]+)',raw,re.I)
    if sold is None and max_t is not None and rem:
        sold=max_t-int(rem.group(1).replace(',',''))
    # Scheduled close/draw.
    cm=(re.search(r'(?:Ticket sales end|Competition closes on|This competition will close on|Live draw date)\s*:?\s*([^|]+?(?:\d{1,2}:\d{2}\s*(?:am|pm)|\d{1,2}\s*(?:am|pm)))',raw,re.I)
        or re.search(r'(?:Auto Draw|Draw)\s*:?\s*(\d{1,2}/\d{1,2}/\d{4}\s*[-@]\s*\d{1,2}:\d{2}\s*(?:am|pm)?)',raw,re.I))
    closes=None
    if cm:
        try: closes=dtparse.parse(cm.group(1).replace('@',' '),dayfirst=True,fuzzy=True)
        except Exception: closes=None
    low=raw.lower()
    guaranteed=any(p.lower() in low for p in guarantee_phrases)
    prize=_cash_value(title,raw)
    scope=_scope(title,raw)
    return dict(operator=operator,external_id=url.rstrip('/').split('/')[-1] or operator,title=title[:300],url=url,
                prize=prize,price=float(pm.group(1).replace(',','')) if pm else None,sold=sold,max_tickets=max_t,
                closes=closes,guaranteed=guaranteed,scope=scope)

def _crawl_products(operator,base,href_fragment,guarantee_phrases=(),limit=120):
    out=[]; seen=set()
    try:
        soup=BeautifulSoup(get(base),'html.parser')
        links=[]
        for a in soup.select('a[href]'):
            u=a.get('href','')
            if href_fragment in u:
                if u.startswith('/'):
                    from urllib.parse import urljoin
                    u=urljoin(base,u)
                if u not in seen:
                    seen.add(u); links.append(u)
        for url in links[:limit]:
            try: out.append(_parse_generic_product(operator,url,guarantee_phrases))
            except Exception as e:
                out.append(dict(operator=operator,external_id=url.rstrip('/').split('/')[-1],title=url,url=url,error=str(e),scope='research'))
    except Exception as e:
        out.append(dict(operator=operator,external_id='discovery',title=f'{operator} discovery adapter',url=base,error=str(e),scope='research'))
    return out

def click():
    return _crawl_products('click','https://www.clickcompetitions.co.uk/competitions/','/competition/',
        ('guaranteed draw regardless of sellout','guaranteed draw regardless of sell out','draw takes place regardless of tickets sold'))

def seven_days():
    return _crawl_products('7days','https://7daysperformance.co.uk/competitions/','/product/',
        ('draw takes place regardless of tickets sold',))

def elite():
    return _crawl_products('elite','https://elitecompetitions.co.uk/competitions/','/competitions/',
        ('guaranteed draw regardless of ticket sales',))

def just_my_luck():
    return _crawl_products('justmyluck','https://www.justmyluck.co.uk/','/competition/',
        ('guaranteed draws no extensions','guaranteed draw','no extensions'))

def hot_comps():
    return _crawl_products('hotcomps','https://hotcomps.com/','/competition/',
        ('guaranteed winners','no extensions','guaranteed end date'))

def competitions365():
    return _crawl_products('365competitions','https://www.365competition.co.uk/','/competition/',
        ('automatically runs a draw','guaranteed draw'))

def boony():
    return _crawl_products('boony','https://boonycompetitions.co.uk/','/competition/',
        ('automated draw','guaranteed draw'))



def _uk_close_from_words(text):
    """Parse Today/Tomorrow or an explicit UK draw date into an aware datetime."""
    now=datetime.now(UK)
    m=re.search(r'(?:Closes|Automated Draw|Draw On|Ends?)\s*(Today|Tomorrow)\s*,?\s*(\d{1,2}:\d{2})',text,re.I)
    if m:
        d=now.date() + timedelta(days=1 if m.group(1).lower()=='tomorrow' else 0)
        hh,mm=map(int,m.group(2).split(':'))
        return datetime(d.year,d.month,d.day,hh,mm,tzinfo=UK)
    patterns=[
      r'(?:Automated Draw|Draw On|Ends?)\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?\s+\d{1,2}:\d{2}\s*(?:am|pm)?)',
      r'guaranteed auto draw on\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?\s+\d{1,2}:\d{2}\s*(?:am|pm)?)'
    ]
    for pat in patterns:
        m=re.search(pat,text,re.I)
        if m:
            try:
                dt=dtparse.parse(m.group(1),dayfirst=True,fuzzy=True,default=now.replace(month=1,day=1,hour=0,minute=0,second=0,microsecond=0))
                if dt.year < now.year: dt=dt.replace(year=now.year)
                return dt.replace(tzinfo=UK) if dt.tzinfo is None else dt
            except Exception: pass
    return None


def _dream_cash_value(title):
    m=re.search(r'(?:WIN\s*)?£\s*([\d,]+(?:\.\d+)?)\s*(?:TAX[- ]?FREE\s*)?CASH',title or '',re.I)
    return float(m.group(1).replace(',','')) if m else None

def _dream_listing_close(card_text, now=None):
    """Near-term Dream closing time from the dedicated Cash listing."""
    now=(now or datetime.now(UK)).astimezone(UK)
    m=re.search(r'(?:Closes|Automated Draw)\s+(Today|Tomorrow)\s*,?\s*(\d{1,2}:\d{2})',card_text or '',re.I)
    if not m: return None
    day=now.date()+timedelta(days=1 if m.group(1).lower()=='tomorrow' else 0)
    hh,mm=map(int,m.group(2).split(':'))
    return datetime(day.year,day.month,day.day,hh,mm,tzinfo=UK)

def dreamcar():
    """Dream cash collector with stage diagnostics."""
    base='https://dreamcargiveaways.co.uk/competitions/cash'
    out=[]; seen=set()
    stats=dict(anchors=0,unique_urls=0,cards_with_close=0,fetched=0,cash_title=0,
               price=0,soldmax=0,close=0,accepted=0)
    rejects=[]
    try:
        soup=BeautifulSoup(get(base),'html.parser')
        anchors=soup.select('a[href*="/competitions/"]')
        stats['anchors']=len(anchors)
        candidates=[]
        for a in anchors:
            u=urljoin(base,a.get('href','')).split('?')[0]
            if u.rstrip('/')==base.rstrip('/') or u in seen: continue
            seen.add(u); stats['unique_urls']+=1
            node=a; card=''
            for _ in range(10):
                if node is None: break
                txt=' '.join(node.stripped_strings)
                if re.search(r'(?:Closes|Automated Draw)\s+(?:Today|Tomorrow)\s*,?\s*\d{1,2}:\d{2}',txt,re.I):
                    card=txt; break
                node=node.parent
            if card:
                stats['cards_with_close']+=1
                candidates.append((u,card))
            elif len(rejects)<8:
                rejects.append(f"NO_CARD_CLOSE {u}")

        # If Dream changed its card nesting, don't throw all links away:
        # fetch unique cash-page competition links and let individual parsing decide.
        if not candidates:
            candidates=[(u,'') for u in seen]
            log.warning("[Dreamcar] no card close labels found; diagnostic fallback will inspect %d unique links",len(candidates))

        for url,card in candidates[:120]:
            try:
                ps=BeautifulSoup(get(url),'html.parser')
                stats['fetched']+=1
                title=_title(ps,url)
                text=' '.join(ps.stripped_strings)
                title_low=title.lower()

                if any(x in title_low for x in ('instant win','every ticket wins','site credit','dream points')):
                    if len(rejects)<8: rejects.append(f"EXCLUDED_STRUCTURE {title[:70]}")
                    continue

                prize=_dream_cash_value(title)
                if prize is None:
                    if len(rejects)<8: rejects.append(f"NO_CASH_TITLE {title[:70]}")
                    continue
                stats['cash_title']+=1

                pm=(re.search(r'Enter from\s*£\s*([\d,.]+)',text,re.I)
                    or re.search(r'£\s*([\d,.]+)\s*(?:per entry|each)',text,re.I))
                if not pm:
                    if len(rejects)<8: rejects.append(f"NO_PRICE {title[:70]}")
                    continue
                stats['price']+=1

                sr=(re.search(r'([\d,]+)\s*/\s*([\d,]+)\s*Tickets?\s+sold',text,re.I)
                    or re.search(r'currently\s+has\s+([\d,]+)\s+entries.*?maximum\s+number\s+of\s+([\d,]+)\s+entries',text,re.I))
                if not sr:
                    if len(rejects)<8: rejects.append(f"NO_SOLDMAX {title[:70]}")
                    continue
                stats['soldmax']+=1

                # Use the individual competition page only. Dream exposes a
                # competition-specific "Automated Draw Today/Tomorrow, HH:MM" beside
                # its countdown. Never use the cash-category/listing card timer.
                closes=None
                cm=re.search(r'Competition closes in.*?Automated Draw\s+(Today|Tomorrow)\s*,?\s*(\d{1,2}:\d{2})',text,re.I)
                if cm:
                    now=datetime.now(UK)
                    day=now.date()+timedelta(days=1 if cm.group(1).lower()=='tomorrow' else 0)
                    hh,mm=map(int,cm.group(2).split(':'))
                    closes=datetime(day.year,day.month,day.day,hh,mm,tzinfo=UK)
                if closes is None:
                    # Some Dream pages expose an absolute competition-specific draw date.
                    dm=re.search(r'(?:draw date for this competition is|Draw Date)\s*:?\s*([^.|]+)',text,re.I)
                    if dm:
                        try:
                            closes=dtparse.parse(dm.group(1),dayfirst=True,fuzzy=True)
                            if closes.tzinfo is None: closes=closes.replace(tzinfo=UK)
                        except Exception:
                            closes=None
                if closes is None:
                    if len(rejects)<8: rejects.append(f"NO_CLOSE {title[:70]}")
                    continue
                stats['close']+=1

                out.append(dict(
                    operator='dreamcar',external_id=url.rstrip('/').split('/')[-1],
                    title=title[:300],url=url,prize=prize,
                    price=float(pm.group(1).replace(',','')),
                    sold=int(sr.group(1).replace(',','')),
                    max_tickets=int(sr.group(2).replace(',','')),
                    closes=closes,guaranteed=True,scope='eligible'
                ))
                stats['accepted']+=1
            except Exception as e:
                if len(rejects)<8: rejects.append(f"FETCH/PARSE {url} :: {type(e).__name__}: {e}")

    except Exception as e:
        log.exception("[Dreamcar] discovery failure: %s",e)
        out.append(dict(operator='dreamcar',external_id='discovery',
                        title='Dream cash discovery adapter',url=base,error=str(e),scope='research'))

    log.info("[Dreamcar] stages anchors=%d unique_urls=%d cards_with_close=%d fetched=%d cash_title=%d price=%d soldmax=%d close=%d accepted=%d",
             stats['anchors'],stats['unique_urls'],stats['cards_with_close'],stats['fetched'],
             stats['cash_title'],stats['price'],stats['soldmax'],stats['close'],stats['accepted'])
    for reason in rejects[:8]:
        log.info("[Dreamcar] reject sample: %s",reason)
    return out

def _cash_prize_from_title(title):
    """Strict immediate cash end-prize parser for cash-only lanes."""
    t=title or ''
    pats=[
      r'(?:win\\s*)?£\\s*([\\d,]+(?:\\.\\d+)?)\\s*(?:tax[- ]?free\\s*)?cash\\b',
      r'£\\s*([\\d,]+(?:\\.\\d+)?)\\s*(?:enter|[-–—])',
      r'£\\s*([\\d,]+(?:\\.\\d+)?)\\s*$',
    ]
    for p in pats:
        m=re.search(p,t,re.I)
        if m:return float(m.group(1).replace(',',''))
    return None

def bounty():
    """Bounty cash-only collector.

    The old adapter crawled /lists/ links, but Bounty's current site exposes live
    competitions directly under /category/cash and /competition/<slug>.
    """
    base='https://bountycompetitions.co.uk/category/cash'
    out=[]; seen=set()
    try:
        soup=BeautifulSoup(get(base),'html.parser')
        links=[]
        for a in soup.select('a[href*="/competition/"]'):
            u=urljoin(base,a.get('href','')).split('?')[0]
            if u not in seen:
                seen.add(u); links.append(u)
        log.info("[Bounty] cash category competition links=%d",len(links))
        for url in links[:120]:
            try:
                ps=BeautifulSoup(get(url),'html.parser')
                title=_title(ps,url); text=' '.join(ps.stripped_strings)
                tl=title.lower()
                if any(x in tl for x in ('instant win','tickets into','odds booster','ticket into')):
                    continue
                prize=_cash_prize_from_title(title)
                if prize is None: continue

                pm=(re.search(r'£\\s*([\\d,.]+)\\s*(?:A TICKET|PER TICKET|Per Entry)',text,re.I)
                    or re.search(r'([\\d,.]+)p\\s*(?:A TICKET|PER TICKET|Per Entry)',text,re.I))
                price=None
                if pm:
                    price=float(pm.group(1).replace(',',''))
                    if 'p' in pm.group(0).lower() and '£' not in pm.group(0): price/=100.0

                maxm=(re.search(r'([\\d,]+)\\s*TOTAL TICKETS',text,re.I)
                      or re.search(r'Max Tickets\\s*([\\d,]+)',text,re.I))
                max_t=int(maxm.group(1).replace(',','')) if maxm else None

                # Current product pages expose the confirmed entry list and Total Tickets.
                soldm=(re.search(r'Total Tickets:\\s*([\\d,]+)',text,re.I)
                       or re.search(r'Tickets Sold\\s*([\\d,]+)',text,re.I))
                sold=int(soldm.group(1).replace(',','')) if soldm else None

                closes=_uk_close_from_words(text)
                if closes is None:
                    # Category card often has the close even when product body changes.
                    # Find the matching link's surrounding card.
                    for a in soup.select('a[href]'):
                        if urljoin(base,a.get('href','')).split('?')[0]==url:
                            node=a
                            for _ in range(7):
                                if node is None: break
                                closes=_uk_close_from_words(' '.join(node.stripped_strings))
                                if closes: break
                                node=node.parent
                            if closes: break

                if None in (price,sold,max_t,closes):
                    log.info("[Bounty] reject %s price=%s sold=%s max=%s close=%s",title[:60],price,sold,max_t,bool(closes))
                    continue
                out.append(dict(operator='bounty',external_id=url.rstrip('/').split('/')[-1],
                    title=title[:300],url=url,prize=prize,price=price,sold=sold,max_tickets=max_t,
                    closes=closes,guaranteed=True,scope='eligible'))
            except Exception as e:
                log.info("[Bounty] parse error %s :: %s",url,e)
    except Exception as e:
        log.exception("[Bounty] discovery failure: %s",e)
    return out

def rev():
    """Rev cash-only collector using live prize links rather than entry-list discovery."""
    base='https://www.revcomps.com/'
    out=[]; seen=set()
    try:
        soup=BeautifulSoup(get(base),'html.parser')
        links=[]
        for a in soup.select('a[href]'):
            label=' '.join(a.stripped_strings)
            u=urljoin(base,a.get('href','')).split('?')[0]
            if 'revcomps.com' not in u or u.rstrip('/')==base.rstrip('/') or u in seen: continue
            # Rev prize pages are top-level slugs. Restrict discovery to anchors that
            # visibly advertise cash, avoiding account/help/navigation URLs.
            if 'cash' not in label.lower() and '£' not in label: continue
            seen.add(u); links.append(u)
        log.info("[Rev] candidate cash links=%d",len(links))

        for url in links[:150]:
            try:
                ps=BeautifulSoup(get(url),'html.parser')
                title=_title(ps,url); text=' '.join(ps.stripped_strings); low=text.lower()
                if any(x in title.lower() for x in ('instant win','credit','ticket into','tickets into')):
                    continue
                if re.search(r'\\bClosed\\b',text,re.I) or 'draw conducted' in low: continue
                prize=_cash_prize_from_title(title)
                if prize is None: continue

                pm=(re.search(r'£\\s*([\\d,.]+)\\s*(?:PER TICKET|A TICKET)',text,re.I)
                    or re.search(r'£\\s*([\\d,.]+)\\s*(?:ENTRY|COMPETITION)',text,re.I))
                if not pm: continue
                price=float(pm.group(1).replace(',',''))
                if price <= 0: continue

                sr=(re.search(r'Remaining\\s*:?\\s*([\\d,]+).*?Sold\\s*:?\\s*([\\d,]+)',text,re.I)
                    or re.search(r'Sold\\s*:?\\s*([\\d,]+).*?Remaining\\s*:?\\s*([\\d,]+)',text,re.I))
                if not sr: continue
                if sr.re.pattern.lower().startswith('remaining'):
                    remaining=int(sr.group(1).replace(',','')); sold=int(sr.group(2).replace(',',''))
                else:
                    sold=int(sr.group(1).replace(',','')); remaining=int(sr.group(2).replace(',',''))
                maxm=re.search(r'(?:max(?:imum)?(?: of)?|max of)\\s*([\\d,]+)\\s*tickets',text,re.I)
                max_t=int(maxm.group(1).replace(',','')) if maxm else sold+remaining

                cm=(re.search(r'(?:Guaranteed Auto Draw|Auto Draw|Draw)\\s*(?:at|on)?\\s*([^|]+?\\d{4})',text,re.I)
                    or re.search(r'(?:at\\s*)?(\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:am|pm)?\\s*,?\\s*\\d{1,2}(?:ST|ND|RD|TH)?\\s+[A-Za-z]{3,9}\\s+\\d{4})',text,re.I))
                closes=None
                if cm:
                    try:
                        closes=dtparse.parse(cm.group(1),dayfirst=True,fuzzy=True)
                        if closes.tzinfo is None: closes=closes.replace(tzinfo=UK)
                    except Exception: closes=None
                if closes is None: closes=_uk_close_from_words(text)

                if closes is None:
                    log.info("[Rev] reject close %s",title[:70]); continue
                out.append(dict(operator='rev',external_id=url.rstrip('/').split('/')[-1],
                    title=title[:300],url=url,prize=prize,price=price,sold=sold,max_tickets=max_t,
                    closes=closes,guaranteed=True,scope='eligible'))
            except Exception as e:
                log.info("[Rev] parse error %s :: %s",url,e)
    except Exception as e:
        log.exception("[Rev] discovery failure: %s",e)
    return out

COLLECTORS=[kilted,dreamcar,bounty,rev]
