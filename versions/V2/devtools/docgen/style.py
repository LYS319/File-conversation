CSS = r"""
:root{
  --bg:#f4f6fa;--card:#ffffff;--ink:#1b2432;--muted:#566275;--line:#dde2ea;--accent:#2d6bd6;
  --kid-bg:#fff6dc;--kid-line:#f0b429;--warn-bg:#fdecec;--warn-line:#d64545;--ok-bg:#e6f6ec;--ok-line:#2f9e5b;
  --code-bg:#0f1727;--code-ink:#e6edf7;--gutter:#6b7d99;--tc:#8aa1bd;--ts:#a5d6a7;--tk:#82aaff;--tn:#f78c6c;
  --n1:#e3edff;--s1:#9db8ee;--n2:#e2f5e9;--s2:#8fcfa5;--n3:#fff0dc;--s3:#f1c58a;--n4:#fde6ee;--s4:#eea1ba;--n5:#eef0f4;--s5:#c3c9d4;
  --edge:#4b5a72;--gfill:#fafbfd;--gfill2:#f0f5ff;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0d1320;--card:#151d2e;--ink:#e7edf7;--muted:#9db0c8;--line:#26334b;--accent:#7aa7ff;
  --kid-bg:#2b2511;--kid-line:#d9a21b;--warn-bg:#331a1c;--warn-line:#e06666;--ok-bg:#12301f;--ok-line:#47b574;
  --code-bg:#0a101c;--n1:#1c2b4b;--s1:#3d5a96;--n2:#16342a;--s2:#2f7a58;--n3:#3a2c15;--s3:#9a6e22;--n4:#3b1d2a;--s4:#9a3f5f;--n5:#232b3b;--s5:#46536c;
  --edge:#9fb2cc;--gfill:#101827;--gfill2:#16223a;}}
:root[data-theme="dark"]{
  --bg:#0d1320;--card:#151d2e;--ink:#e7edf7;--muted:#9db0c8;--line:#26334b;--accent:#7aa7ff;
  --kid-bg:#2b2511;--kid-line:#d9a21b;--warn-bg:#331a1c;--warn-line:#e06666;--ok-bg:#12301f;--ok-line:#47b574;
  --code-bg:#0a101c;--n1:#1c2b4b;--s1:#3d5a96;--n2:#16342a;--s2:#2f7a58;--n3:#3a2c15;--s3:#9a6e22;--n4:#3b1d2a;--s4:#9a3f5f;--n5:#232b3b;--s5:#46536c;
  --edge:#9fb2cc;--gfill:#101827;--gfill2:#16223a;}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:64px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 "Pretendard","Noto Sans KR","Malgun Gothic",system-ui,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--accent)}
code,kbd{font:0.92em ui-monospace,Consolas,"D2Coding",monospace;background:color-mix(in srgb,var(--accent) 12%,transparent);padding:1px 6px;border-radius:5px}
nav.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--card) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
nav.top .in{max-width:1040px;margin:0 auto;padding:0 16px;display:flex;gap:4px;overflow-x:auto;white-space:nowrap;align-items:center}
nav.top a{padding:12px 10px;text-decoration:none;color:var(--muted);font-size:14px;font-weight:600}
nav.top a:hover{color:var(--accent)}
nav.top .brand{color:var(--ink);font-weight:800;margin-right:8px}
main{max-width:1040px;margin:0 auto;padding:0 16px 80px}
header.hero{padding:44px 0 18px}
.hero h1{font-size:clamp(28px,5vw,42px);line-height:1.25;margin:0 0 10px;letter-spacing:-.02em}
.hero p{margin:0;color:var(--muted);font-size:17px;max-width:46em}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:13.5px;color:var(--muted)}
.chip b{color:var(--ink)}
section{margin-top:56px}
section>h2{font-size:clamp(22px,3.4vw,28px);margin:0 0 14px;display:flex;align-items:center;gap:12px;letter-spacing:-.01em}
.num{display:inline-grid;place-items:center;min-width:36px;height:36px;border-radius:10px;background:var(--accent);color:#fff;font-size:17px;font-weight:800;padding:0 8px}
h3{font-size:21px;margin:34px 0 10px;padding-top:6px;border-top:1px dashed var(--line)}
h3 .sub{font-size:14px;font-weight:600;color:var(--muted);margin-left:8px}
h4{font-size:16px;margin:22px 0 8px;color:var(--muted);letter-spacing:.02em}
p{margin:10px 0}
.kid{background:var(--kid-bg);border-left:6px solid var(--kid-line);border-radius:0 14px 14px 0;padding:14px 18px;margin:14px 0}
.kid .kh{font-weight:800;margin-bottom:4px}
.kid p:first-of-type{margin-top:2px}.kid p:last-child{margin-bottom:2px}
.tip{background:var(--ok-bg);border-left:6px solid var(--ok-line);border-radius:0 12px 12px 0;padding:10px 16px;margin:14px 0}
.warn{background:var(--warn-bg);border-left:6px solid var(--warn-line);border-radius:0 12px 12px 0;padding:10px 16px;margin:14px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin:16px 0}
.cardx{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px 18px}
.cardx .em{font-size:30px;line-height:1}
.cardx h5{margin:8px 0 4px;font-size:17px}
.cardx p{margin:4px 0;color:var(--muted);font-size:15px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:15px;margin:14px 0}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:color-mix(in srgb,var(--accent) 9%,var(--card));font-size:13.5px;letter-spacing:.02em}
tr:last-child td{border-bottom:0}
.tw{overflow-x:auto}
.dgwrap{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px;margin:16px 0;overflow-x:auto}
.dg{display:block;width:100%;min-width:680px;height:auto}
.dgcap{font-size:14px;color:var(--muted);margin:6px 4px 0}
.nd{stroke-width:1.5}.n1{fill:var(--n1);stroke:var(--s1)}.n2{fill:var(--n2);stroke:var(--s2)}.n3{fill:var(--n3);stroke:var(--s3)}.n4{fill:var(--n4);stroke:var(--s4)}.n5{fill:var(--n5);stroke:var(--s5)}
.gp{stroke-width:1.2}.g1{fill:var(--gfill);stroke:var(--line)}.g2{fill:var(--gfill2);stroke:var(--line)}
.gt{font-weight:700;font-size:14px;fill:var(--ink)}
.tb{font-weight:700;font-size:15px;fill:var(--ink)}.ts{font-size:13px;fill:var(--muted)}.el{font-size:12.5px;fill:var(--ink);font-weight:600}
.ed{stroke:var(--edge);stroke-width:1.8}.ed.bad{stroke:#d64545}.ahp{fill:var(--edge)}.ahpx{fill:#d64545}
.life{stroke:var(--line);stroke-width:1.5;stroke-dasharray:4 4}
.code{background:var(--code-bg);border-radius:14px;overflow:hidden;margin:14px 0;border:1px solid #1d2a42}
.code .ch{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:8px 14px;background:#16223a;color:#c9d6ea;font-size:13px}
.code .ch b{font-family:ui-monospace,Consolas,monospace}.code .ch span{color:#8fa4c4}
.code pre{margin:0;padding:10px 0;overflow-x:auto;color:var(--code-ink);font:13px/1.6 ui-monospace,Consolas,"D2Coding","Malgun Gothic",monospace;tab-size:4}
.code code{background:none;padding:0;border-radius:0;font:inherit;color:inherit}
.l{display:block;white-space:pre;padding-right:18px}
.l.hl{background:rgba(240,180,41,.11)}
.g{display:inline-block;min-width:6.2em;text-align:right;padding-right:10px;margin-right:12px;color:var(--gutter);user-select:none;border-right:1px solid #243452;font-style:normal}
.g::before{content:attr(data-b);color:#f0b429;font-weight:800;margin-right:.5em}
.g::after{content:attr(data-ln)}
.tc{color:var(--tc)}.ts2{color:var(--ts)}.tk{color:var(--tk)}.tn{color:var(--tn)}
.tc,.tk,.tn{font-style:normal}.ts,.tk{}
span.ts{color:var(--ts);font-size:inherit}
.notes{list-style:none;margin:0;padding:14px 18px 8px;background:var(--card);color:var(--ink);border-top:1px solid var(--line)}
.notes li{display:flex;gap:10px;margin:0 0 10px;font-size:15px;line-height:1.65}
.notes li>div{flex:1;min-width:0}
.bd{color:#b7791f;font-size:1.1em;line-height:1.5}
@media (prefers-color-scheme:dark){.bd{color:#f0b429}}
.step{counter-reset:s}
.step li{list-style:none;position:relative;padding:8px 12px 8px 52px;margin:8px 0;background:var(--card);border:1px solid var(--line);border-radius:12px}
.step li::before{counter-increment:s;content:counter(s);position:absolute;left:12px;top:9px;width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:800;font-size:14px}
.step{padding:0}
.qa dt{font-weight:800;margin-top:16px}.qa dd{margin:4px 0 0 0;color:var(--muted)}
.tree{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;font:13.5px/1.7 ui-monospace,Consolas,"D2Coding","Malgun Gothic",monospace;overflow-x:auto;white-space:pre}
.tree i{color:var(--muted);font-style:normal}
footer{margin-top:60px;color:var(--muted);font-size:14px;border-top:1px solid var(--line);padding-top:14px}
details.fold{margin:12px 0}details.fold>summary{cursor:pointer;font-weight:700;padding:8px 0}
@media print{nav.top{display:none}body{background:#fff}.code,.dgwrap,.kid,.cardx{break-inside:avoid}}
"""
