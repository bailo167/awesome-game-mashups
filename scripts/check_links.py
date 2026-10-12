#!/usr/bin/env python3
"""HTTP reachability, not gameplay or safety verification. No credentials sent."""
from __future__ import annotations
import argparse,concurrent.futures,ipaddress,json,socket,sys
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from catalogue import ROOT,links,load,safe_url

def public_destination(url):
    if not safe_url(url): raise ValueError('Rejected non-public or malformed URL')
    u=urlsplit(url)
    addresses=socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise ValueError('Rejected non-public network destination')

class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_destination(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def classify(code):
    if 200<=code<300: return 'reachable'
    if code in (404,410): return 'unavailable'
    return 'unresolved'

OUTCOMES=('reachable','unavailable','known-dead','unresolved')

def settle(rows,projects):
    """An unavailable link is expected, not a failure, when every entry using it is already marked dead."""
    for r in rows:
        owners=[projects.get(i) for i in r.get('projects',[])]
        if r['outcome']=='unavailable' and owners and all(p and 'dead' in p.get('status',[]) for p in owners): r['outcome']='known-dead'
    return rows

def check(url):
    try:
        public_destination(url);opener=build_opener(PublicRedirect())
        for method in ('HEAD','GET'):
            headers={'User-Agent':'Awesome-Game-Mashups-LinkAudit/2.0'}
            if method=='GET': headers['Range']='bytes=0-1023'
            req=Request(url,method=method,headers=headers)
            try:
                with opener.open(req,timeout=15) as r: return {'url':url,'status':r.status,'outcome':classify(r.status),'final_url':r.url}
            except HTTPError as e:
                if method=='HEAD' and e.code in (403,404,405,501): continue
                return {'url':url,'status':e.code,'outcome':classify(e.code)}
        return {'url':url,'outcome':'unresolved','reason':'No response'}
    except (OSError,URLError,ValueError) as e: return {'url':url,'outcome':'unresolved','reason':type(e).__name__+': '+str(e)[:160]}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'build/link-report.json');parser.add_argument('--limit',type=int);args=parser.parse_args()
    projects,config=load();owners={}
    for p in projects:
        for l in links(p): owners.setdefault(l['url'],[]).append(p['id'])
    urls=sorted(owners)
    if args.limit is not None: urls=urls[:max(args.limit,0)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(check,urls))
    for r in rows: r['projects']=owners[r['url']]
    settle(rows,{p['id']:p for p in projects})
    counts={k:sum(r['outcome']==k for r in rows) for k in OUTCOMES}
    report={'scope':'HTTP reachability only; no play-testing, safety review or source claim verification.','total_unique_urls':len(owners),'attempted':len(rows),'coverage':'complete' if len(rows)==len(owners) else 'partial','outcome':'FAILURES' if counts['unavailable'] else ('INCOMPLETE' if counts['unresolved'] or len(rows)<len(owners) else 'REACHABILITY CHECK COMPLETE'),'counts':counts,'results':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
    if counts['unresolved']: print('::warning::Link audit has unresolved responses (bot blocks, rate limits or timeouts). Inspect link-report.json; do not call all links verified.')
    if counts['known-dead']: print(f"::notice::{counts['known-dead']} unavailable link(s) belong only to entries already marked dead; kept for history.")
    for r in rows:
        if r['outcome']=='unavailable': print(f"::error::Newly unavailable link ({r.get('status')}): {r['url']} — used by {', '.join(r['projects'])}. Fix the link or mark the entry dead.")
    if counts['unavailable']: sys.exit(1)
if __name__=='__main__': main()
