import os
from flask import Flask,render_template_string,request,redirect,url_for
from db import conn,init_db
from ev import threshold_field
app=Flask(__name__)

INDEX_HTML = r'''<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"><title>Competition Lab</title><style>body{font-family:system-ui;background:#0b0e13;color:#e9edf4;margin:0;padding:24px}a{color:#8ab4ff}.wrap{max-width:1200px;margin:auto}.tiles,.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.tile,.card{background:#151a22;border:1px solid #29313d;border-radius:14px;padding:16px}.n{font-size:28px;font-weight:700}.muted{color:#98a2b3}.good{color:#62d394}.bad{color:#ff7b72}input,button{background:#0e131a;color:#fff;border:1px solid #394454;border-radius:8px;padding:9px}button{cursor:pointer}h1{margin-bottom:4px}.card h3{margin-top:0}</style></head><body><div class=wrap><h1>Project Exit Plan — Competition Lab <span class=muted style="font-size:16px">v0.3.6</span></h1><p class=muted>Today's potential entries · final-hour EV validation · actual-entry tracking</p><div class=tiles><div class=tile><div class=muted>Lifetime staked</div><div class=n>£{{'%.2f'|format(perf.staked|float)}}</div></div><div class=tile><div class=muted>Expected profit</div><div class=n>£{{'%.2f'|format(perf.expected_profit|float)}}</div></div><div class=tile><div class=muted>Winnings</div><div class=n>£{{'%.2f'|format(perf.winnings|float)}}</div></div><div class=tile><div class=muted>Entries</div><div class=n>{{perf.entries}}</div></div></div><p><a href=/entries>Actual entries & settlement →</a></p>{% if not comps %}<div class=card><h3>No important competitions right now</h3><p class=muted>Nothing tracked closes later today. The collector continues recording the four-site market in the background.</p></div>{% endif %}<div class=grid>{% for c in comps %}<div class=card><div class=muted>{{c.operator|upper}} · {{c.health}}</div><h3><a href="{{c.url}}" target=_blank>{{c.title}}</a></h3><p>£{{c.ticket_price_gbp or '?'}} / ticket · Prize £{{c.prize_value_gbp or '?'}}</p><p>Sold: <b>{{c.sold_count or '?'}}</b> / {{c.max_tickets or '?'}}</p><p>Nominal EV: <b>{{ ('%+.1f%%'|format((c.nominal_ev|float)*100)) if c.nominal_ev is not none else '?' }}</b><br>Conservative EV: <b class="{{'good' if c.conservative_ev is not none and c.conservative_ev|float >= th else ''}}">{{ ('%+.1f%%'|format((c.conservative_ev|float)*100)) if c.conservative_ev is not none else '?' }}</b></p><p class=muted>Close: {{c.closes_at or '?'}}<br>Last data: {{c.observed_at or c.health_reason or '?'}}</p>{% if c.close_hours is not none and c.close_hours|float > entry_window %}{% if c.conservative_ev is not none and c.conservative_ev|float >= th %}<p class=good><b>INTERESTING TODAY</b> · final entry check starts inside {{entry_window|int}}h</p>{% else %}<p class=muted>TRACKING TODAY · not currently above EV hurdle</p>{% endif %}{% endif %}{% if c.health=='entry_valid' and c.scope=='eligible' and c.observation_count >= min_obs and c.history_hours is not none and c.history_hours|float >= min_hist and c.close_hours is not none and c.close_hours|float <= entry_window and c.close_hours|float >= 0 and c.conservative_ev is not none and c.conservative_ev|float >= th %}<p class=good><b>ENTRY READY</b> · {{c.observation_count}} observations</p><form method=post action="/enter/{{c.id}}"><input name=tickets type=number min=1 placeholder="Tickets" required><input name=notes placeholder="Notes"><button>I ENTERED</button></form>{% elif c.health=='entry_valid' and c.conservative_ev is not none and c.conservative_ev|float >= th %}<p class=muted><b>HIGH EV — WATCH</b> · {{c.observation_count}}/3 observations</p>{% endif %}</div>{% endfor %}</div><h2 style="margin-top:28px">Tomorrow — Potential Draws</h2>{% if not tomorrow %}<div class=card><p class=muted>No tracked draws ending tomorrow.</p></div>{% endif %}<div class=grid>{% for c in tomorrow %}<div class=card><div class=muted>{{c.operator|upper}} · TOMORROW</div><h3><a href="{{c.url}}" target=_blank>{{c.title}}</a></h3><p>£{{c.ticket_price_gbp or '?'}} / ticket · Prize £{{c.prize_value_gbp or '?'}}</p><p>Sold: <b>{{c.sold_count or '?'}}</b> / {{c.max_tickets or '?'}}</p><p>Current conservative EV: <b class="{{'good' if c.conservative_ev is not none and c.conservative_ev|float >= th else ''}}">{{ ('%+.1f%%'|format((c.conservative_ev|float)*100)) if c.conservative_ev is not none else '?' }}</b></p>{% if c.stake and c.stake['tickets'] > 0 %}<p><b>{{c.stake['label']}}:</b> {{c.stake['tickets']}} ticket{{'' if c.stake['tickets']==1 else 's'}} · <b>£{{'%.2f'|format(c.stake['cost'])}}</b></p>{% elif c.stake and c.stake['label'] != 'NO BUY' %}<p class=muted>{{c.stake['label']}}</p>{% endif %}<p class=muted>Close: {{c.closes_at or '?'}}<br>Early indication only — no entry action until tomorrow's final window.</p>{% if c.conservative_ev is not none and c.conservative_ev|float >= th %}<p class=good><b>POTENTIAL TOMORROW</b></p>{% else %}<p class=muted>TRACKING</p>{% endif %}</div>{% endfor %}</div></div></body></html>
'''

ENTRIES_HTML = r'''<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>body{font-family:system-ui;background:#0b0e13;color:#e9edf4;padding:24px}a{color:#8ab4ff}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #29313d;text-align:left}input,button{padding:7px;background:#151a22;color:#fff;border:1px solid #394454}</style></head><body><h1>Actual Entries</h1><p><a href=/>← Dashboard</a></p><table><tr><th>Entered</th><th>Competition</th><th>Tickets / Stake</th><th>EV at entry</th><th>Expected profit</th><th>Result</th></tr>{% for e in rows %}<tr><td>{{e.entered_at}}</td><td>{{e.operator}} · {{e.title}}</td><td>{{e.tickets}} / £{{'%.2f'|format(e.stake_gbp|float)}}</td><td>{{'%+.1f%%'|format((e.conservative_ev_at_entry|float)*100)}}</td><td>£{{'%.2f'|format(e.expected_profit_gbp|float)}}</td><td>{% if e.settled_at %}£{{e.winnings_gbp}}{% else %}<form method=post action="/settle/{{e.id}}"><input name=winnings type=number step=.01 min=0 placeholder="Winnings"><button>Settle</button></form>{% endif %}</td></tr>{% endfor %}</table></body></html>
'''


def stake_recommendation(row, monthly_budget=200.0):
    """Bankroll-aware display sizing; never changes entry eligibility."""
    try:
        c=dict(row)
        ev=c.get('conservative_ev')
        price=c.get('ticket_price_gbp')
        close_h=c.get('close_hours')
        ev=float(ev) if ev is not None else None
        price=float(price) if price is not None else None
        close_h=float(close_h) if close_h is not None else None
        threshold=float(os.getenv('MIN_CONSERVATIVE_EV','.40'))
        if ev is None or price is None or price <= 0 or ev < threshold:
            return {'tickets':0,'cost':0.0,'label':'NO BUY'}
        frac=.05 if ev < .60 else (.075 if ev < 1.0 else (.10 if ev < 1.50 else .125))
        target=min(monthly_budget*frac,25.0)
        if price > target*1.35:
            return {'tickets':0,'cost':0.0,'label':'PASS — ticket too large for allocation'}
        tickets=max(1,int(target/price))
        cost=round(tickets*price,2)
        entry_window=float(os.getenv('ENTRY_WINDOW_HOURS','2'))
        label='BUY SIZE' if close_h is not None and 0 <= close_h <= entry_window else 'PLANNED SIZE'
        return {'tickets':tickets,'cost':cost,'label':label}
    except Exception:
        return {'tickets':0,'cost':0.0,'label':'NO BUY'}

@app.before_request
def boot(): init_db()
@app.get('/health')
def health():
 try:
  with conn() as c:c.execute('select 1')
  return {'ok':True},200
 except Exception as e:return {'ok':False,'error':str(e)},503
@app.get('/')
def home():
 with conn() as c:
  base_sql='''SELECT c.*,s.sold_count,s.nominal_ev,s.conservative_ev,s.conservative_final_field,s.observed_at,
   (SELECT count(*) FROM snapshots sx WHERE sx.competition_id=c.id) observation_count,
   (SELECT EXTRACT(EPOCH FROM (max(observed_at)-min(observed_at)))/3600 FROM snapshots sx WHERE sx.competition_id=c.id) history_hours,
   EXTRACT(EPOCH FROM (c.closes_at-now()))/3600 close_hours,
   (SELECT count(*) FROM entries e WHERE e.competition_id=c.id) entry_count
   FROM competitions c LEFT JOIN LATERAL (SELECT * FROM snapshots WHERE competition_id=c.id ORDER BY observed_at DESC LIMIT 1)s ON true
   WHERE c.status='open' AND c.closes_at IS NOT NULL AND c.closes_at >= now()\n     AND c.last_seen_at >= now() - interval '45 minutes'\n     AND c.health IN ('research_valid','entry_valid')
     AND (c.closes_at AT TIME ZONE 'Europe/London')::date = ((now() AT TIME ZONE 'Europe/London')::date + %s)
   ORDER BY c.closes_at ASC, s.conservative_ev DESC NULLS LAST'''
  th=float(os.getenv('MIN_CONSERVATIVE_EV','.40'))
  comps=c.execute(base_sql,(0,)).fetchall()
  tomorrow=c.execute(base_sql,(1,)).fetchall()
  comps=[dict(x) for x in comps]
  tomorrow=[dict(x) for x in tomorrow]
  for x in comps: x['stake']=stake_recommendation(x)
  for x in tomorrow: x['stake']=stake_recommendation(x)
  # Action surface: negative EV remains in research DB but is not useful to display.
  def _displayable(x):
      try:
          return x.get('conservative_ev') is not None and float(x['conservative_ev']) >= 0
      except Exception:
          return False
  comps=[x for x in comps if _displayable(x)]
  tomorrow=[x for x in tomorrow if _displayable(x)]
  perf=c.execute('SELECT COALESCE(sum(stake_gbp),0) staked,COALESCE(sum(expected_profit_gbp),0) expected_profit,COALESCE(sum(winnings_gbp),0) winnings,count(*) entries FROM entries').fetchone()
 return render_template_string(INDEX_HTML,comps=comps,tomorrow=tomorrow,perf=perf,
  th=float(os.getenv('MIN_CONSERVATIVE_EV','.40')),
  min_obs=max(3,int(os.getenv('MIN_ENTRY_OBSERVATIONS','4'))),
  min_hist=float(os.getenv('MIN_ENTRY_HISTORY_HOURS','.75')),
  entry_window=float(os.getenv('ENTRY_WINDOW_HOURS','2')))
@app.post('/enter/<int:cid>')
def enter(cid):
 tickets=int(request.form['tickets']); notes=request.form.get('notes','')
 with conn() as c:
  x=c.execute('''SELECT c.*,s.sold_count,s.nominal_ev,s.conservative_ev,s.conservative_final_field,
   (SELECT count(*) FROM snapshots sx WHERE sx.competition_id=c.id) observation_count,
   (SELECT EXTRACT(EPOCH FROM (max(observed_at)-min(observed_at)))/3600 FROM snapshots sx WHERE sx.competition_id=c.id) history_hours,
   EXTRACT(EPOCH FROM (c.closes_at-now()))/3600 close_hours
   FROM competitions c JOIN LATERAL(SELECT * FROM snapshots WHERE competition_id=c.id ORDER BY observed_at DESC LIMIT 1)s ON true WHERE c.id=%s''',(cid,)).fetchone()
  th=float(os.getenv('MIN_CONSERVATIVE_EV','.40'))
  min_obs=max(3,int(os.getenv('MIN_ENTRY_OBSERVATIONS','4')))
  min_hist=float(os.getenv('MIN_ENTRY_HISTORY_HOURS','.75'))
  entry_window=float(os.getenv('ENTRY_WINDOW_HOURS','2'))
  if (not x or x['health']!='entry_valid' or x['scope']!='eligible' or x['observation_count']<min_obs
      or x['history_hours'] is None or float(x['history_hours'])<min_hist
      or x['close_hours'] is None or float(x['close_hours'])<0 or float(x['close_hours'])>entry_window
      or x['conservative_ev'] is None or float(x['conservative_ev'])<th):
   return ('Entry blocked: opportunity is not ENTRY READY.',409)
  stake=float(x['ticket_price_gbp'])*tickets; final_field=max(int(x['conservative_final_field']),int(x['sold_count'])+tickets); expected=float(x['prize_value_gbp'])*tickets/final_field; ep=expected-stake
  c.execute('''INSERT INTO entries(competition_id,tickets,stake_gbp,sold_count_at_entry,nominal_ev_at_entry,conservative_ev_at_entry,conservative_final_field_at_entry,expected_prize_gbp,expected_profit_gbp,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(cid,tickets,stake,x['sold_count'],x['nominal_ev'],x['conservative_ev'],x['conservative_final_field'],expected,ep,notes));c.commit()
 return redirect(url_for('home'))
@app.get('/entries')
def entries():
 with conn() as c: rows=c.execute('SELECT e.*,c.title,c.operator FROM entries e JOIN competitions c ON c.id=e.competition_id ORDER BY entered_at DESC').fetchall()
 return render_template_string(ENTRIES_HTML,rows=rows)
@app.post('/settle/<int:eid>')
def settle(eid):
 with conn() as c:c.execute('UPDATE entries SET winnings_gbp=%s,settled_at=now() WHERE id=%s',(float(request.form['winnings']),eid));c.commit()
 return redirect(url_for('entries'))
