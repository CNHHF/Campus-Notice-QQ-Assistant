import unittest
import re
from unittest.mock import patch
import crawl
import sources

class ColumnTests(unittest.TestCase):
    def test_relative_links_and_trailing_whitespace_keep_column_and_url(self):
        html='<li><a href=" ../info/1042/5139.htm  " title="关于入党积极分子的公示">公示</a><span>2026-10-27</span></li>'
        rows=crawl.parse_listing(html,'https://info.zufedfc.edu.cn/dqzj/zzjs.htm','static')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['url'],'https://info.zufedfc.edu.cn/info/1042/5139.htm')
        self.assertEqual(rows[0]['column'],'栏目1042')
        self.assertEqual(rows[0]['date'],'2026-10-27')
        rows=crawl.parse_listing(html.replace('../info/','info/'),'https://gqt.zufedfc.edu.cn/tzgg.htm','static')
        self.assertEqual(len(rows),1)

    def test_split_date_layout_is_exact(self):
        html='<a href="../info/1021/3552.htm" title="关于奖学金名单的公示"><div class="time"><h3>14</h3><h6>2026.10</h6></div></a>'
        row=crawl.parse_listing(html,'http://wy.zufedfc.edu.cn/xsgz/jczd.htm','static')[0]
        self.assertEqual(row['date'],'2026-10-14')
        self.assertTrue(row['date_exact'])

    def test_discovery_includes_party_columns_but_skips_login(self):
        html='<a href="dqzj/zzjs.htm">组织建设</a><a href="kcfw/xkjs.htm">学科竞赛</a><a href="hy-login.jsp?x=1">通知公告</a><a href="javascript:alert(1)">公示</a>'
        cols=crawl.discover_columns(html,'https://info.zufedfc.edu.cn/','static')
        self.assertEqual(cols,['https://info.zufedfc.edu.cn/dqzj/zzjs.htm','https://info.zufedfc.edu.cn/kcfw/xkjs.htm'])

    def test_coverage_preserves_keys_and_fits_configured_limit(self):
        cfg=next(c for c in sources.SOURCES if c['key']=='info')
        self.assertIn('/dqzj/zzjs.htm',cfg['lists'])
        self.assertEqual(len(sources.SOURCES),22)
        self.assertTrue(all(len(c['lists'])<=sources.MAX_LIST_PER_SOURCE for c in sources.SOURCES))
        self.assertNotIn('item',cfg)
        self.assertIn('item',next(c for c in sources.SOURCES if c['key']=='jy'))

    def test_cross_protocol_deduplication_uses_clean_url(self):
        self.assertEqual(crawl.canon('http://info.zufedfc.edu.cn/info/1042/5139.htm'),crawl.canon('https://info.zufedfc.edu.cn/info/1042/5139.htm'))

if __name__=='__main__':unittest.main()
