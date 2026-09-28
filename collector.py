import json, logging, os, time
from datetime import datetime, timezone
from collectors import COLLECTORS
from db import conn, init_db
from ev import nominal_ev, project_final, hours_to_close

TH=float(os.getenv('MIN_CONSERVATIVE_EV','.40'))
INTERVAL=max(60,int(os.getenv('COLLECTOR_INTERVAL_SECONDS','900')))
RUN_ONCE=os.getenv('COLLECTOR_RUN_ONCE','0').lower() in {'1','true','yes'}
ENTRY_WINDOW_HOURS=float(os.getenv('ENTRY_WINDOW_HOURS','2'))
DASHBOARD_WINDOW_HOURS=float(os.getenv('DASHBOARD_WINDOW_HOURS','2'))
MIN_HISTORY_HOURS=float(os.getenv('MIN_ENTRY_HISTORY_HOURS','.75'))
MIN_ENTRY_OBSERVATIONS=max(3,int(os.getenv('MIN_ENTRY_OBSERVATIONS','4')))
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO').upper(),format='%(asctime)sZ %(levelname)s %(message)s',datefmt='%Y-%m-%dT%H:%M:%S')
log=logging.getLogger('competition-lab')

def operator_name(fn): return getattr(fn,'__name__','collector').replace('_',' ').title()

def run_cycle():
    started=datetime.now(timezone.utc); init_db(); log.info('Competition Lab collector cycle starting; database ready')
    totals={'operators':0,'rows':0,'research_valid':0,'entry_valid':0,'unhealthy':0,'snapshots':0,'qualifying':0,'errors':0}
    with conn() as c:
      for fn in COLLECTORS:
        name=operator_name(fn); totals['operators']+=1; log.info('[%s] scanning...',name)
        try: rows=fn() or []; log.info('[%s] discovered %d row(s)',name,len(rows))
        except Exception as e: totals['errors']+=1; log.exception('[%s] collector failed: %s',name,e); continue
        for x in rows:
          totals['rows']+=1; err=x.get('error'); scope=x.get('scope','research')
          research_required=['price','sold','max_tickets','closes']
          fields_present=(not err and all(x.get(k) is not None for k in research_required))
          sane=False
          sanity_reason=None
          if fields_present:
            try:
              price=float(x['price']); sold=int(x['sold']); max_tickets=int(x['max_tickets'])
              if price <= 0: sanity_reason='ticket price must be > 0'
              elif sold < 0: sanity_reason='sold count must be >= 0'
              elif max_tickets <= 0: sanity_reason='max tickets must be > 0'
              elif sold > max_tickets: sanity_reason='sold count exceeds max tickets'
              elif x.get('prize') is not None and float(x['prize']) <= 0: sanity_reason='prize must be > 0'
              else: sane=True
            except (TypeError,ValueError): sanity_reason='non-numeric price/sold/max/prize'
          research_valid=(fields_present and sane)
          entry_valid=(research_valid and scope=='eligible' and x.get('prize') is not None and bool(x.get('guaranteed')))
          health='entry_valid' if entry_valid else ('research_valid' if research_valid else 'unhealthy')
          totals[health]+=1
          reason=err
          if not reason and not fields_present: reason='missing price/sold/max/close data'
          elif not reason and not sane: reason='invalid competition data: '+str(sanity_reason)
          elif not reason and not entry_valid: reason='research-only format or prize/guarantee not verified'
          vals=(x['operator'],x['external_id'],x['title'],x['url'],x.get('prize'),x.get('price'),x.get('max_tickets'),x.get('closes'),x.get('guaranteed'),scope,health,reason,started)
          r=c.execute('''INSERT INTO competitions(operator,external_id,title,url,prize_value_gbp,ticket_price_gbp,max_tickets,closes_at,guaranteed,scope,health,health_reason,last_seen_at)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(operator,external_id) DO UPDATE SET title=EXCLUDED.title,url=EXCLUDED.url,prize_value_gbp=EXCLUDED.prize_value_gbp,ticket_price_gbp=EXCLUDED.ticket_price_gbp,max_tickets=EXCLUDED.max_tickets,closes_at=EXCLUDED.closes_at,guaranteed=EXCLUDED.guaranteed,scope=EXCLUDED.scope,health=EXCLUDED.health,health_reason=EXCLUDED.health_reason,last_seen_at=EXCLUDED.last_seen_at,updated_at=now() RETURNING id''',vals).fetchone()
          if not research_valid:
            log.warning('[%s] unhealthy: %s | %s',name,x.get('title','unknown'),reason); continue
          sold=x['sold']; vel=0.0
          hist=c.execute('SELECT sold_count,observed_at FROM snapshots WHERE competition_id=%s ORDER BY observed_at DESC LIMIT 8',(r['id'],)).fetchall()
          observations=len(hist)+1
          history_hours=0.0
          if hist:
            oldest=hist[-1]['observed_at']
            history_hours=max(0.0,(started-oldest).total_seconds()/3600)
          if hist and hist[0]['sold_count'] is not None:
            h=(started-hist[0]['observed_at']).total_seconds()/3600
            if h>0: vel=max(0,(sold-hist[0]['sold_count'])/h)
          close_hours=hours_to_close(x['closes'],started)
          try:
            proj=min(x['max_tickets'],project_final(sold,x['closes'],started,vel,observations))
            nev=nominal_ev(x.get('prize'),x['price'],sold) if x.get('prize') else None
            cev=nominal_ev(x.get('prize'),x['price'],proj) if x.get('prize') else None
          except Exception as e:
            totals['errors']+=1
            log.exception('[%s] row EV calculation failed: %s | %s',name,x.get('title','unknown'),e)
            continue
          c.execute('INSERT INTO snapshots(competition_id,sold_count,remaining_count,nominal_ev,conservative_final_field,conservative_ev,sales_velocity_per_hour,data_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(r['id'],sold,x['max_tickets']-sold,nev,proj,cev,vel,json.dumps(x,default=str)))
          totals['snapshots']+=1
          if entry_valid and cev is not None and float(cev)>=TH:
            ready=(observations>=MIN_ENTRY_OBSERVATIONS and history_hours>=MIN_HISTORY_HOURS
                   and close_hours is not None and 0 <= close_hours<=ENTRY_WINDOW_HOURS)
            if not ready and close_hours is not None and 0 <= close_hours <= DASHBOARD_WINDOW_HOURS:
              log.info('[%s] HIGH EV - WATCH %.1f%% | %s | sold=%s projected=%s obs=%s history=%.2fh close=%.2fh velocity=%.2f/h',
                       name,float(cev)*100,x['title'],sold,proj,observations,history_hours,close_hours,vel)
            elif ready:
              totals['qualifying']+=1
              log.info('[%s] ENTRY READY %.1f%% conservative EV | %s | sold=%s projected=%s obs=%s history=%.2fh close=%.2fh velocity=%.2f/h',
                       name,float(cev)*100,x['title'],sold,proj,observations,history_hours,close_hours,vel)
        c.commit()
    elapsed=(datetime.now(timezone.utc)-started).total_seconds()
    log.info('Cycle complete in %.1fs | operators=%d rows=%d research_valid=%d entry_valid=%d unhealthy=%d snapshots=%d qualifying=%d errors=%d',elapsed,totals['operators'],totals['rows'],totals['research_valid'],totals['entry_valid'],totals['unhealthy'],totals['snapshots'],totals['qualifying'],totals['errors'])

def main():
    log.info('Competition Lab Collector v0.3.5 starting | interval=%ss | threshold=+%.0f%%',INTERVAL,TH*100)
    while True:
      try: run_cycle()
      except Exception as e: log.exception('Collector cycle failed: %s',e)
      if RUN_ONCE:return
      log.info('Sleeping %ss until next collection cycle',INTERVAL); time.sleep(INTERVAL)
if __name__=='__main__': main()
