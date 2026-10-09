#!/usr/bin/env python3
"""Build the catalogue, README, static website and Atom feed. Python 3.12+, stdlib only."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, html, ipaddress, json, re, shutil
from pathlib import Path
from urllib.parse import urlsplit, quote
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
CATEGORIES={'core','watchlist','adjacent'}
STATUSES={'released','source-available','experimental','verified-wip','tech-demo','video-only','unverified','adjacent','archived','dead'}
URL_FIELDS={'source':'Source code','release':'Release / download','media':'Watch demo','creator_post':'Creator post','project_page':'Project page','verification':'Supporting source','latest_update':'Update','discussion':'Discussion','creator_url':'Creator profile'}
LABELS={'released':'Released','source-available':'Code available','experimental':'Experimental','verified-wip':'In development','tech-demo':'Demo','video-only':'Video only','unverified':'Unconfirmed','adjacent':'Related','archived':'Archived','dead':'Unavailable'}
GROUPS=[('play','Available to play'),('development','Code, demos and projects in development'),('watchlist','Unconfirmed sightings'),('adjacent','Related projects')]
NOTICE='Listed availability is not a play-test or safety certification. Source code is not automatically a ready-to-install download. Unconfirmed sightings and related projects are counted separately.'

def load(root=ROOT):
    return json.loads((root/'data/projects.json').read_text()),json.loads((root/'data/site.json').read_text())

def safe_url(value):
    try:
        u=urlsplit(value)
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or re.search(r'[\s<>"\\]',value): return False
        h=u.hostname.lower()
        if h=='localhost' or '.' not in h or h.endswith(('.localhost','.local','.internal','.lan')): return False
        try:
            if not ipaddress.ip_address(h).is_global: return False
        except ValueError: pass
        return True
    except (TypeError,ValueError): return False

def group(p):
    if p['category']!='core': return p['category']
    return 'play' if 'released' in p['status'] and 'dead' not in p['status'] else 'development'

def status(p):
    parts=[LABELS[s] for s in p['status'] if s!='adjacent']
    if p['category']=='watchlist' and 'Unconfirmed' not in parts: parts.append('Unconfirmed')
    if p['category']=='adjacent': parts.append('Related')
    return ' · '.join(parts)

def demo(p):
    if p.get('media'): return p['media']
    if 'video-only' in p['status']: return p.get('creator_post')
    return None

def links(p):
    out=[];seen=set()
    for key,label in URL_FIELDS.items():
        u=p.get(key)
        if u and u not in seen: out.append({'label':label,'url':u});seen.add(u)
    for link in p.get('extra_links',[]):
        if link['url'] not in seen: out.append(link);seen.add(link['url'])
    return out

def plain(text):
    text=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',text or '')
    return re.sub(r'[*`_]', '', text)

def esc(text): return html.escape(str(text or ''),quote=True)
def md(text): return str(text or '').replace('|','\\|').replace('\n',' ')
def paragraph(text): return ''.join('<p>'+esc(plain(p)).replace('\n','<br>')+'</p>' for p in re.split(r'\n\s*\n',text or '') if p.strip())

def validate(projects,config):
    errors=[];ids=set();names=set()
    if not isinstance(projects,list) or not projects: raise ValueError('Catalogue must be a nonempty JSON array')
    today=dt.date.today()
    for p in projects:
        n=p.get('name','<unnamed>');prefix=f'{n}: '
        for k in ('id','name','summary','description','host','guest','creator','category','status','added_at','reviewed_at','review_basis','platforms','playtest','extra_links'):
            if k not in p: errors.append(prefix+'missing '+k)
        ident=p.get('id','')
        if not isinstance(ident,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',ident): errors.append(prefix+'invalid stable id')
        if ident in ids: errors.append(prefix+'duplicate id')
        ids.add(ident)
        if not isinstance(n,str) or n.casefold() in names: errors.append(prefix+'duplicate/invalid name')
        names.add(str(n).casefold())
        if p.get('category') not in CATEGORIES: errors.append(prefix+'invalid category')
        s=p.get('status',[])
        if not isinstance(s,list) or not s or not set(s)<=STATUSES or len(s)!=len(set(s)): errors.append(prefix+'invalid statuses');continue
        for key in ('summary','description','host'):
            if not isinstance(p.get(key),str) or not p[key].strip(): errors.append(prefix+'invalid '+key)
        if len(p.get('summary',''))>400 or '\n' in p.get('summary',''): errors.append(prefix+'summary must be one short line')
        for k in ('guest','platforms'):
            if not isinstance(p.get(k),list) or not all(isinstance(v,str) and v for v in p[k]): errors.append(prefix+'invalid '+k)
        if 'source-available' in s and not p.get('source'): errors.append(prefix+'source-available needs source URL')
        if 'released' in s and not (p.get('release') or p.get('project_page') or p.get('source')): errors.append(prefix+'released needs an acquisition source')
        if 'video-only' in s and 'released' in s: errors.append(prefix+'video-only conflicts with released')
        if p.get('category')=='watchlist' and ('released' in s or 'source-available' in s): errors.append(prefix+'watchlist cannot assert available release/code')
        if p.get('category')=='core' and 'unverified' in s: errors.append(prefix+'unverified belongs on watchlist')
        if p.get('license')=='NOASSERTION': errors.append(prefix+'NOASSERTION is not a licence; use null')
        if p.get('review_basis') not in ('legacy-record','primary-source-review','creator-confirmation','playtest'): errors.append(prefix+'invalid review basis')
        for k in ('added_at','reviewed_at'):
            if p.get(k):
                try:
                    date=dt.date.fromisoformat(p[k])
                    if date>today: errors.append(prefix+k+' is in the future')
                except (TypeError,ValueError): errors.append(prefix+'invalid date '+k)
        if p.get('review_basis')!='legacy-record' and not p.get('reviewed_at'): errors.append(prefix+'dated review required')
        if p.get('playtest') is not None:
            t=p['playtest']
            if not isinstance(t,dict) or not all(t.get(k) for k in ('date','version','platform','evidence')): errors.append(prefix+'playtest requires date/version/platform/evidence')
        try:
            ls=links(p)
            if not ls: errors.append(prefix+'missing evidence link')
            for link in ls:
                if not safe_url(link['url']): errors.append(prefix+'unsafe/malformed URL '+str(link['url']))
        except (KeyError,TypeError): errors.append(prefix+'malformed links')
        for field in ('summary','description','notes','approach'):
            if re.search(r'<\s*(?:script|iframe|object|embed)\b',p.get(field) or '',re.I): errors.append(prefix+'active HTML is not catalogue text')
    if config.get('schema_version')!=2: errors.append('site.json: schema_version must be 2')
    if not safe_url(config.get('site_url','')) or not safe_url(config.get('repository','')): errors.append('site.json: invalid URLs')
    try: dt.date.fromisoformat(config['updated_at'])
    except (KeyError,ValueError,TypeError): errors.append('site.json: invalid updated_at')
    see=config.get('see_also',[])
    if not isinstance(see,list) or not all(isinstance(x,dict) and isinstance(x.get('name'),str) and x['name'].strip() and safe_url(x.get('url','')) and isinstance(x.get('description',''),str) for x in see): errors.append('site.json: see_also entries need name, safe url and optional description')
    featured=config.get('featured',[])
    if len(featured)!=len(set(featured)) or not set(featured)<=ids: errors.append('site.json: invalid featured IDs')
    if any(p['id'] in featured and p['category']!='core' for p in projects): errors.append('Featured entries must be core, not unconfirmed')
    if errors: raise ValueError('\n'.join(errors))
    return {'total':len(projects),'core':sum(p['category']=='core' for p in projects),'released_core':sum(group(p)=='play' for p in projects),'watchlist':sum(p['category']=='watchlist' for p in projects),'related':sum(p['category']=='adjacent' for p in projects),'demos':sum(bool(demo(p)) for p in projects),'dated_source_reviews':sum(bool(p.get('reviewed_at')) for p in projects),'recorded_playtests':sum(bool(p.get('playtest')) for p in projects)}

def recent(projects,config,days=7):
    cutoff=dt.date.fromisoformat(config['updated_at'])-dt.timedelta(days=days-1)
    return sorted([p for p in projects if p.get('added_at') and cutoff<=dt.date.fromisoformat(p['added_at'])<=dt.date.fromisoformat(config['updated_at'])],key=lambda p:(p['added_at'],p['name'].casefold()),reverse=True)

def readme(projects,config):
    stats=validate(projects,config);repo=config['repository']
    site_link=('[Browse the visual site]('+config['site_url']+'/)') if config.get('site_enabled') else '[Visual site build & deployment](docs/MAINTENANCE.md#publishing-the-site)'
    out=['# Awesome Game Mashups','','> Games rebuilt **inside other games**.','',f"**{stats['total']} entries:** {stats['core']} core projects, {stats['watchlist']} unconfirmed sightings and {stats['related']} related projects. Not all entries are verified releases.",'','[**Made one? Submit your project**]('+repo+'/issues/new?template=new-project.yml) · [Report a correction]('+repo+'/issues/new?template=correction.yml) · '+site_link,'',]+([f"**See also:** "+' · '.join(f"[{md(x['name'])}]({x['url']})"+(f" — {md(x['description'])}" if x.get('description') else '') for x in config['see_also']),''] if config.get('see_also') else [])+['**Catalogue updated:** '+config['updated_at']+'. This is an editorial update date, not a blanket verification date.','',NOTICE,'','## Contents','','- [Featured projects](#featured-projects)','- [New to the catalogue](#new-to-the-catalogue)','- [Browse projects](#browse-projects)','- [Unconfirmed sightings](#unconfirmed-sightings)','- [Related projects](#related-projects)','- [Project details](#project-details)','- [About this list](#what-belongs-here)','','## Featured projects','',config['featured_note'],'','| Project | What it is | Status | Demo |','|---|---|---|---|']
    byid={p['id']:p for p in projects}
    def row(p): return f"| [{md(p['name'])}](#project-{p['id']}) | {md(p['summary'])} | {md(status(p))} | "+(f"[Watch]({demo(p)})" if demo(p) else '—')+' |'
    out += [row(byid[k]) for k in config['featured']]
    out += ['','## New to the catalogue','','Added to this index within seven days of the editorial update; not necessarily newly released games.','']
    r=recent(projects,config)
    out += [' · '.join(f"[{md(p['name'])}](#project-{p['id']})" for p in r[:8]) if r else 'No dated additions in this window.']
    out += ['','[Full weekly digest](docs/promote/weekly-digest.md) · [Atom feed]('+config['site_url']+'/feed.xml)','','## Browse projects']
    for key,title in GROUPS:
        out += ['',('### ' if key in ('play','development') else '## ')+title,'']
        if key=='watchlist': out += ['These are leads, not confirmed downloads. Footage does not prove wider implementation claims.','']
        if key=='development': out += ['Public code can still require compilation. Video-only entries have no public build listed.','']
        out += ['| Project | What it is | Status | Demo |','|---|---|---|---|']
        out += [row(p) for p in sorted(projects,key=lambda p:p['name'].casefold()) if group(p)==key]
    out += ['','## Project details','','Descriptions are sourced from project material; a listing does not mean this catalogue has run the software.']
    for p in projects:
        out += ['',f'<a name="project-{p["id"]}"></a>','',f"### {p['name']}",'',f"**Guest:** {', '.join(p['guest'])}  ",f"**Host:** {p['host']}  ",f"**Creator:** {p.get('creator') or 'Not established'}  ",f"**Status:** {status(p)}  "]
        if p.get('approach'): out += ['**Approach:** '+p['approach']+'  ']
        if p.get('scope_note'): out += ['**Scope note:** '+p['scope_note']+'  ']
        out += ['',p['description'],'']
        if p.get('requirements'): out += ['**Requirements:** '+p['requirements'],'']
        if p.get('platforms'): out += ['**Platforms documented:** '+', '.join(p['platforms']),'']
        out += [f"- [{l['label']}]({l['url']})" for l in links(p)]
        out += ['','**Dated source review:** '+(p['reviewed_at'] if p.get('reviewed_at') else 'Not recorded for this inherited entry.')]
        if p.get('playtest'): out += ['**Play-test evidence:** '+p['playtest']['evidence']]
        else: out += ['**Catalogue play-test:** Not recorded.']
        out += ['','[Back to project list](#browse-projects)','','---']
    out += ['','## Creator clusters','',config.get('creator_clusters_markdown','See each project’s original sources for upstream credits.')]
    out += ['','## What belongs here?','','Substantial cross-game runtime integration, meaningful gameplay-system recreations, embedded emulation, and technically significant cross-game bridges. Skins, ordinary asset swaps and map imports alone do not qualify. Historical projects can remain useful even when archived.','','Implementation type and inclusion quality are separate questions. Two processes do not automatically make a project less substantial; the actual interaction and gameplay matter. Watchlist entries are never promoted solely because a video or URL exists.','','## Contributing','','Edit `data/projects.json`, then run `python3 scripts/catalogue.py build` and `python3 scripts/catalogue.py check`. Do not independently edit generated README entries. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [maintenance contract](.github/CATALOGUE_MAINTENANCE.md).','','Creators: demo links, corrections and documented requirements are welcome. A demo link does not grant permission to re-upload the footage. See [the media and sharing guide](docs/promote/README.md).','','## Attribution and trademarks','','Independent community catalogue. Game names and trademarks belong to their owners. The catalogue, original site code and original promotional layouts use [CC0-1.0](LICENSE); linked projects and creator media retain their own terms. This is AI-assisted curation with documented evidence limits, not an official Awesome-directory endorsement.','','<!-- Generated from data/projects.json and data/site.json. -->','']
    return '\n'.join(out)

def actions(p,cls='actions'):
    pairs=[]
    if demo(p): pairs.append(('Watch demo',demo(p)))
    if p.get('release'): pairs.append(('Release',p['release']))
    if p.get('source'): pairs.append(('Source',p['source']))
    if not pairs and links(p): pairs.append(('Original source',links(p)[0]['url']))
    return '<div class="'+cls+'">'+''.join(f'<a href="{esc(url)}" rel="noopener noreferrer">{esc(label)} <span aria-hidden="true">↗</span></a>' for label,url in pairs)+'</div>'

def page(title,body,config,depth='',description='',canonical='',script=False):
    canon=config['site_url'].rstrip('/')+'/'+canonical
    desc=description or 'Discover games inside other games. Browse releases, source code, creator demos and clearly labelled work in progress.'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><meta name="description" content="{esc(desc)}">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-src https://www.youtube-nocookie.com; media-src 'self'">
<title>{esc(title)} · Awesome Game Mashups</title><link rel="canonical" href="{esc(canon)}">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canon)}">
<meta name="twitter:card" content="summary"><link rel="stylesheet" href="{depth}assets/style.css"><link rel="icon" href="{depth}assets/icon.svg" type="image/svg+xml">
<link rel="alternate" type="application/atom+xml" href="{depth}feed.xml" title="New catalogue entries">
</head><body><a class="skip" href="#main">Skip to content</a><header class="top"><a class="brand" href="{depth}index.html"><span class="brandmark" aria-hidden="true">M×</span><span>AWESOME<br>GAME MASHUPS</span></a><nav aria-label="Main"><a href="{depth}index.html#browse">Browse</a><a href="{depth}updates/">Updates</a><a href="{esc(config['repository'])}">GitHub ↗</a></nav></header>
<main id="main">{body}</main><footer><strong>Real projects. Clear evidence.</strong><p>{esc(NOTICE)}</p><p>Catalogue updated {esc(config['updated_at'])}. No ads, analytics, cookies or third-party media requests on page load. Demo buttons link to creators.</p><a href="{esc(config['repository'])}/issues/new?template=new-project.yml">Submit your project ↗</a> · <a href="{esc(config['repository'])}/blob/main/CONTRIBUTING.md">Contribution guide</a> · <a href="{depth}data/projects.json">JSON data</a>{''.join(f' · <a href="{esc(x["url"])}" rel="noopener noreferrer">See also: {esc(x["name"])} ↗</a>' for x in config.get('see_also',[]))}</footer>
{f'<script src="{depth}assets/app.js" defer></script>' if script else ''}</body></html>'''

def card(p,featured=False):
    ident=p['id'];g=group(p);title=p['name'];d=bool(demo(p))
    attrs=f'data-search="{esc(p["name"]+" "+str(p.get("creator") or "")+" "+p["summary"]+" "+p["host"]+" "+" ".join(p["guest"]))}" data-id="{ident}" data-name="{esc(title.casefold())}" data-host="{esc(p["host"])}" data-guests="{esc(json.dumps(p["guest"]))}" data-group="{g}" data-status="{esc(" ".join(p["status"]))}" data-demo="{str(d).lower()}" data-added="{esc(p.get("added_at") or "")}"'
    cls='feature' if featured else 'project-card'
    art=f'<div class="game-pair" aria-hidden="true"><span>{esc(p["guest"][0])}</span><b>×</b><span>{esc(p["host"])}</span></div>'
    return f'<article class="{cls}" {attrs}>{art}<div class="card-body"><p class="eyebrow">{esc(dict(GROUPS)[g])}</p><h3><a href="projects/{ident}/">{esc(title)}</a></h3><p class="summary">{esc(p["summary"])}</p><p class="status">{esc(status(p))}</p>{actions(p)}<a class="detail-link" href="projects/{ident}/">Details &amp; requirements <span aria-hidden="true">→</span></a></div></article>'

def website(projects,config,out):
    out.mkdir(parents=True,exist_ok=True);(out/'assets').mkdir(exist_ok=True);(out/'data').mkdir(exist_ok=True)
    stats=validate(projects,config);byid={p['id']:p for p in projects}
    host_options=''.join(f'<option value="{esc(h)}">{esc(h)}</option>' for h in sorted({p['host'] for p in projects},key=str.casefold))
    guest_options=''.join(f'<option value="{esc(h)}">{esc(h)}</option>' for h in sorted({g for p in projects for g in p['guest']},key=str.casefold))
    body=f'''<section class="hero"><div><p class="eyebrow">THE CROSS-GAME CATALOGUE</p><h1>Games where<br>they don’t <em>belong.</em></h1><p class="lede">Minecraft in ULTRAKILL. Skate 3 in Garry’s Mod.<br>Discover the projects, watch the demos, find the original source.</p><a class="button primary" href="#browse">Explore the catalogue ↓</a><a class="button" href="{config['repository']}/issues/new?template=new-project.yml">Made one? Add it ↗</a></div><aside class="hero-note"><span class="big-number">{stats['total']}</span><span class="eyebrow">CATALOGUED PROJECTS &amp; LEADS</span><div class="stats"><p><b>{stats['released_core']}</b> core projects with a listed playable version</p><p><b>{stats['demos']}</b> linked creator demos / footage posts</p><p><b>{stats['watchlist']}</b> unconfirmed sightings, kept separate</p></div><p class="muted">Source-backed curation. Not a claim that every project has been independently played.</p></aside></section>
<section id="featured"><div class="section-head"><div><p class="eyebrow">START EXPLORING</p><h2>A few good collisions.</h2></div><p>{esc(config['featured_note'])}</p></div><div class="featured-grid">{''.join(card(byid[x],True) for x in config['featured'])}</div></section>
<section id="browse"><div class="section-head"><div><p class="eyebrow">FIND YOUR NEXT RABBIT HOLE</p><h2>The full catalogue.</h2></div><p id="result-count" role="status" aria-live="polite">{stats['total']} entries</p></div>
<div class="filters" id="filters" hidden><label class="search-label">Search games, projects or creators<input id="search" type="search" placeholder="Try Minecraft, Skate or Fallout…" autocomplete="off"></label><label>Host game<select id="host"><option value="">All hosts</option>{host_options}</select></label><label>Guest game<select id="guest"><option value="">All guests</option>{guest_options}</select></label><label>Availability<select id="status"><option value="">All entries</option><option value="play">Playable versions</option><option value="source-available">Public source</option><option value="development">In development / demos</option><option value="video-only">Video only</option><option value="watchlist">Unconfirmed sightings</option><option value="adjacent">Related projects</option></select></label><label>Sort<select id="sort"><option value="name">Name A–Z</option><option value="newest">New to catalogue</option></select></label><label class="check"><input id="demo" type="checkbox"> Has a demo / footage link</label><button id="reset" type="button">Reset filters</button></div>
<noscript><p>All projects are shown below. JavaScript is only needed for filtering; details and source links still work.</p></noscript><p class="muted">Release ≠ source-only. Demo ≠ download. Unconfirmed ≠ verified.</p><p id="no-results" hidden>No matching projects. Try fewer filters or use Reset filters.</p><div class="catalogue-grid" id="catalogue">{''.join(card(p) for p in sorted(projects,key=lambda p:p['name'].casefold()))}</div></section>'''
    (out/'index.html').write_text(page('Games inside other games',body,config,script=True))
    for p in projects:
        folder=out/'projects'/p['id'];folder.mkdir(parents=True,exist_ok=True)
        primary=''.join(f'<li><a href="{esc(l["url"])}" rel="noopener noreferrer">{esc(l["label"])} ↗</a></li>' for l in links(p))
        metadata=[('Guest',', '.join(p['guest'])),('Host',p['host']),('Creator',p.get('creator') or 'Not established'),('Availability',status(p)),('Recorded licence',p.get('license') or 'Not established'),('Platforms documented',', '.join(p.get('platforms',[])) or 'See the creator’s requirements'),('Added to catalogue',p.get('added_at') or 'Not recorded'),('Dated source review',p.get('reviewed_at') or 'Not recorded for this inherited entry'),('Catalogue play-test','Recorded; see evidence' if p.get('playtest') else 'Not recorded')]
        facts='<dl>'+''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in metadata)+'</dl>'
        body=f'<article class="project-page"><a class="back" href="../../index.html#browse">← Back to catalogue</a><p class="eyebrow">{esc(dict(GROUPS)[group(p)])}</p><h1>{esc(p["name"])}</h1><p class="lede">{esc(p["summary"])}</p>{actions(p)}<div class="project-layout"><section><h2>What it does</h2>{paragraph(p["description"])}'+(f'<h2>How it works</h2>{paragraph(p["approach"])}' if p.get('approach') else '')+f'<h2>Requirements &amp; limitations</h2>{paragraph(p.get("requirements") or "Requirements vary by release. Read the original project documentation before installing. This catalogue has not independently established a complete compatibility matrix.")}<h2>Original sources</h2><ul class="source-list">{primary}</ul><h2>Evidence limits</h2>{paragraph(p.get("review_note") or NOTICE)}<p>Code and releases are linked, not hosted here. Game files and footage retain their owners’ rights.</p></section><aside>{facts}<a class="button" href="{esc(config["repository"])}/issues/new?template=correction.yml&amp;title={quote("Correction: "+p["name"])}">Report a correction ↗</a></aside></div></article>'
        (folder/'index.html').write_text(page(p['name'],body,config,'../../',p['summary'],'projects/'+p['id']+'/'))
    updates=out/'updates';updates.mkdir(exist_ok=True)
    updates_body='<section class="project-page"><p class="eyebrow">NEW TO THE CATALOGUE</p><h1>The latest additions.</h1><p>Added to this index during the seven-day editorial window ending '+esc(config['updated_at'])+'. These are not necessarily new releases.</p><p><a href="../feed.xml">Subscribe with Atom</a></p><ul class="source-list">'+''.join('<li><a href="../projects/'+p['id']+'/">'+esc(p['name'])+'</a> — '+esc(p['summary'])+' <small>'+esc(p.get('added_at'))+'</small></li>' for p in recent(projects,config))+'</ul><a href="../index.html#browse">Back to catalogue</a></section>'
    (updates/'index.html').write_text(page('New to the catalogue',updates_body,config,'../',canonical='updates/'))
    (out/'404.html').write_text(page('Page not found','<section class="hero"><div><h1>Wrong universe.</h1><p>This page is not in the catalogue.</p><a href="'+esc(config['site_url'])+'/">Back to the catalogue</a></div></section>',config,canonical='404.html'))
    (out/'data/projects.json').write_text(json.dumps(projects,ensure_ascii=False,indent=2)+'\n')
    (out/'.nojekyll').write_text('')
    return stats

def feed(projects,config):
    ns='http://www.w3.org/2005/Atom';ET.register_namespace('',ns)
    f=ET.Element('{'+ns+'}feed')
    def add(parent,key,value='',**attrs):
        el=ET.SubElement(parent,'{'+ns+'}'+key,attrs);el.text=value;return el
    url=config['site_url'].rstrip('/')
    add(f,'title','Awesome Game Mashups — new catalogue entries');add(f,'id',url+'/');add(f,'updated',config['updated_at']+'T00:00:00Z')
    add(f,'link',href=url+'/feed.xml',rel='self');add(f,'link',href=url+'/')
    author=add(f,'author');add(author,'name','Awesome Game Mashups contributors')
    for p in recent(projects,config,days=365)[:50]:
        e=add(f,'entry');add(e,'title',p['name']);add(e,'id',url+'/projects/'+p['id']+'/');add(e,'link',href=url+'/projects/'+p['id']+'/');add(e,'updated',p['added_at']+'T00:00:00Z');add(e,'summary',p['summary']+' Status: '+status(p)+'. Added to catalogue; not necessarily a new game release.')
    return ET.tostring(f,encoding='unicode',xml_declaration=True)

def weekly(projects,config):
    out=['# New to Awesome Game Mashups','','Week ending '+config['updated_at']+'. These are additions to the index, not necessarily new releases.','']
    for p in recent(projects,config): out.append(f"- **[{p['name']}]({config['repository']}#project-{p['id']})** — {p['summary']} ({status(p)})")
    if len(out)==4: out+=['No dated additions in this window.']
    return '\n'.join(out)+'\n'

def build(root=ROOT,check=False):
    projects,config=load(root);stats=validate(projects,config)
    generated={'README.md':readme(projects,config),'docs/promote/weekly-digest.md':weekly(projects,config)}
    if check:
        bad=[p for p,s in generated.items() if not (root/p).exists() or (root/p).read_text()!=s]
        if bad: raise ValueError('Generated files differ. Run python3 scripts/catalogue.py build: '+', '.join(bad))
    else:
        for p,s in generated.items(): (root/p).parent.mkdir(parents=True,exist_ok=True);(root/p).write_text(s)
    out=root/'_site'
    if out.exists(): shutil.rmtree(out)
    website(projects,config,out)
    for p in (root/'site').glob('*'):
        if p.is_file(): shutil.copyfile(p,out/'assets'/p.name)
    (out/'feed.xml').write_text(feed(projects,config))
    urls=[config['site_url']+'/',config['site_url']+'/updates/']+[config['site_url']+'/projects/'+p['id']+'/' for p in projects]
    (out/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+esc(u)+'</loc></url>' for u in urls)+'</urlset>')
    (out/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+config['site_url']+'/sitemap.xml\n')
    stats['catalogue_sha256']=hashlib.sha256((root/'data/projects.json').read_bytes()).hexdigest()
    stats['scope']='Structural validation; inherited source claims are not new play-tests.'
    (out/'build-info.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(json.dumps(stats,indent=2));return stats

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['build','check','validate']);parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    try:
        if args.command=='validate': print(json.dumps(validate(*load(args.root)),indent=2))
        else: build(args.root,args.command=='check')
    except (ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as e: parser.exit(1,str(e)+'\n')
if __name__=='__main__': main()
