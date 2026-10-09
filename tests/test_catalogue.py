"""No-network regression tests. Run: python3 -m unittest discover -s tests -v."""
import copy,json,re,sys,tempfile,unittest
from pathlib import Path
from xml.etree import ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import catalogue as c
import check_links as cl
from migrate_catalogue import migrate
class CatalogueTests(unittest.TestCase):
    def setUp(self): self.projects,self.config=c.load()
    def change(self): return copy.deepcopy(self.projects)
    def test_live_catalogue(self): self.assertEqual(c.validate(self.projects,self.config)['total'],len(self.projects))
    def test_duplicate_id(self):
        p=self.change();p[1]['id']=p[0]['id']
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_duplicate_name(self):
        p=self.change();p[1]['name']=p[0]['name'].upper()
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_invalid_status(self):
        p=self.change();p[0]['status'].append('definitely-safe')
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_code_needs_source(self):
        p=self.change();p[0]['source']=None
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_source_is_not_download(self):
        p=self.change()[0];p['status']=['source-available'];self.assertEqual(c.group(p),'development')
    def test_watchlist_not_playable(self):
        p=self.change();p[0]['category']='watchlist'
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_video_only_conflict(self):
        p=self.change();p[0]['status'].append('video-only')
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_unknown_license(self):
        p=self.change();p[0]['license']='NOASSERTION'
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_no_unrecorded_verification(self):
        p=self.change();p[0]['review_basis']='primary-source-review';p[0]['reviewed_at']=None
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_future_review(self):
        p=self.change();p[0]['reviewed_at']='2099-01-01'
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_playtest_needs_evidence(self):
        p=self.change();p[0]['playtest']={'date':'2026-10-05'}
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_active_html_rejected(self):
        p=self.change();p[0]['description']='<script>alert(1)</script>'
        with self.assertRaises(ValueError): c.validate(p,self.config)
    def test_escaping(self): self.assertNotIn('<img',c.paragraph('<img src=x onerror=alert(1)>'))
    def test_unsafe_urls(self):
        for u in ('javascript:alert(1)','file:///etc/passwd','http://localhost/x','http://127.0.0.1/x','http://192.168.1.2/x','https://u:p@github.com/a/b','https://x.local/a','https://github.com/ bad'): self.assertFalse(c.safe_url(u),u)
    def test_safe_urls(self): self.assertTrue(c.safe_url('https://github.com/goonsn/Killcraft'))
    def test_deterministic_readme(self): self.assertEqual(c.readme(self.projects,self.config),c.readme(self.projects,self.config))
    def test_one_detail_anchor_each(self):
        r=c.readme(self.projects,self.config);anchors=re.findall(r'<a name="project-([^"]+)"',r)
        self.assertEqual(set(anchors),{p['id'] for p in self.projects});self.assertEqual(len(anchors),len(self.projects))
    def test_backlinks(self): self.assertEqual(c.readme(self.projects,self.config).count('[Back to project list]'),len(self.projects))
    def test_no_broken_table_gaps(self): self.assertNotRegex(c.readme(self.projects,self.config),r'\|\n\n\| \[')
    def test_four_column_tables(self): self.assertEqual(c.readme(self.projects,self.config).count('| Project | What it is | Status | Demo |'),5)
    def test_no_blanket_verified_count(self): self.assertNotIn('Last verified',c.readme(self.projects,self.config))
    def test_atom_is_valid(self): self.assertTrue(ET.fromstring(c.feed(self.projects,self.config)).tag.endswith('feed'))
    def test_demo_is_distinct(self):
        p=self.change()[0];p.pop('media',None);p['status']=['source-available'];self.assertIsNone(c.demo(p))
    def test_dates_are_catalogue_dates(self):
        p=self.change()[0];p['first_seen']='2026-10-05';p['added_at']=None;self.assertEqual(c.recent([p],self.config),[])
    def test_migration_idempotent(self): self.assertEqual(migrate(self.projects,'',{}),self.projects)
    def test_no_silent_legacy_drop(self):
        with self.assertRaises(ValueError): migrate([{'name':'Unknown'}],'# Empty',{})
    def test_rate_limit_not_success(self): self.assertEqual(cl.classify(429),'unresolved')
    def test_bot_block_not_dead(self): self.assertEqual(cl.classify(403),'unresolved')
    def test_unavailable_status(self): self.assertEqual(cl.classify(404),'unavailable')
    def test_export_contains_every_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);c.website(self.projects,self.config,out)
            self.assertEqual(len(list((out/'projects').glob('*/index.html'))),len(self.projects))
            self.assertEqual(json.loads((out/'data/projects.json').read_text()),self.projects)
            self.assertEqual((out/'index.html').read_text().count('class="project-card"'),len(self.projects))
    def test_see_also_rendered(self):
        cfg=copy.deepcopy(self.config);cfg['see_also']=[{'name':'Example','url':'https://example.org/','description':'A list.'}]
        r=c.readme(self.projects,cfg);self.assertIn('**See also:** [Example](https://example.org/) — A list.',r);self.assertLess(r.index('**See also:**'),r.index('## Contents'))
    def test_see_also_unsafe_url(self):
        cfg=copy.deepcopy(self.config);cfg['see_also']=[{'name':'Bad','url':'javascript:alert(1)'}]
        with self.assertRaises(ValueError): c.validate(self.projects,cfg)
    def test_unknown_featured(self):
        config=copy.deepcopy(self.config);config['featured'].append('not-in-catalogue')
        with self.assertRaises(ValueError): c.validate(self.projects,config)
if __name__=='__main__': unittest.main()
