#!/usr/bin/env python3
"""
Merges dashboard, deadline, and practice apps into studio-BETA.html
Fixes: double JS execution, missing window expose, duplicate @keyframes
"""
import re, os

BASE = os.path.dirname(os.path.abspath(__file__))

def read(name):
    with open(os.path.join(BASE, name), encoding='utf-8') as f:
        return f.read()

def extract_body(html):
    """Extract everything between <body> and </body>"""
    m = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    return m.group(1).strip() if m else ''

def strip_scripts(html):
    """Remove ALL <script> tags (with and without src) from HTML.
    This prevents JS from executing in global scope from panel HTML."""
    return re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)

def extract_css_blocks(html):
    """Extract all inline <style> block contents"""
    return re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)

def extract_external_scripts(html):
    """Extract <script src="..."></script> tags (no inline content)"""
    return re.findall(r'<script\s[^>]*src=["\'][^"\']+["\'][^>]*>\s*</script>', html)

def extract_all_inline_js(html):
    """Extract inline JS from ALL script blocks (including those mixed with src).
    This captures Electron bridge JS embedded in Chart.js script tag."""
    blocks = []
    # Scripts WITHOUT src attr
    no_src = re.findall(r'<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>', html, re.DOTALL)
    blocks.extend(no_src)
    # Scripts WITH src that also have inline content (invalid but used for Electron bridge)
    with_src = re.findall(r'<script[^>]+src=[^>]+>(.*?)</script>', html, re.DOTALL)
    blocks.extend(with_src)
    return [b for b in blocks if b.strip()]

def scope_css(css, scope, kf_prefix=''):
    """
    Prefix CSS selectors with scope. Skips :root, *, @keyframes blocks.
    kf_prefix: prefix for @keyframes names to avoid duplicates across apps.
    """
    output = []
    i = 0
    full_text = css

    while i < len(full_text):
        # Skip leading whitespace
        ws_match = re.match(r'\s+', full_text[i:])
        if ws_match and not full_text[i:i+ws_match.end()].strip():
            output.append(full_text[i:i+ws_match.end()])
            i += ws_match.end()
            continue

        # @keyframes: rename to avoid conflicts
        kf_match = re.match(
            r'(@(?:-webkit-|-moz-|-o-)?keyframes)\s+(\S+)',
            full_text[i:])
        if kf_match:
            # Find matching closing brace
            brace = full_text.find('{', i + kf_match.end())
            if brace == -1:
                output.append(full_text[i:])
                break
            depth = 1
            j = brace + 1
            while j < len(full_text) and depth > 0:
                if full_text[j] == '{': depth += 1
                elif full_text[j] == '}': depth -= 1
                j += 1
            kf_name = kf_match.group(2)
            new_name = f'{kf_prefix}{kf_name}' if kf_prefix else kf_name
            block = full_text[i:j]
            block = block.replace(
                kf_match.group(1) + ' ' + kf_name,
                kf_match.group(1) + ' ' + new_name, 1)
            output.append(block)
            i = j
            continue

        # @media / @supports: recurse into contents
        at_match = re.match(r'(@(?:media|supports)[^{]+)\{', full_text[i:], re.DOTALL)
        if at_match:
            at_selector = at_match.group(1).strip()
            brace = i + full_text[i:].find('{', at_match.start())
            depth = 1
            j = brace + 1
            while j < len(full_text) and depth > 0:
                if full_text[j] == '{': depth += 1
                elif full_text[j] == '}': depth -= 1
                j += 1
            inner = full_text[brace+1:j-1]
            scoped_inner = scope_css(inner, scope, kf_prefix)
            output.append(f'{at_selector} {{\n{scoped_inner}\n}}\n')
            i = j
            continue

        # Find next {
        brace = full_text.find('{', i)
        if brace == -1:
            output.append(full_text[i:])
            break

        selector_text = full_text[i:brace].strip()
        if not selector_text:
            i = brace + 1
            continue

        # Find matching }
        depth = 1
        j = brace + 1
        while j < len(full_text) and depth > 0:
            if full_text[j] == '{': depth += 1
            elif full_text[j] == '}': depth -= 1
            j += 1

        rule_body = full_text[brace:j]

        # Replace keyframe animation references inside rule body
        if kf_prefix:
            # Replace animation-name and animation shorthand values
            def replace_kf_ref(m):
                # Don't prefix already-prefixed or CSS built-ins
                name = m.group(1)
                builtins = {'none','inherit','initial','unset','ease','linear',
                            'ease-in','ease-out','ease-in-out','step-start','step-end'}
                if name in builtins:
                    return m.group(0)
                return f'animation:{kf_prefix}{name}' if m.group(0).startswith('animation:') else f'animation-name:{kf_prefix}{name}'
            # Simple replace: any animation name that matches a known pattern
            rule_body = re.sub(
                r'(animation(?:-name)?:\s*)([a-zA-Z][\w-]*)',
                lambda m: m.group(1) + kf_prefix + m.group(2)
                    if m.group(2) not in {'none','inherit','initial','unset',
                                          'ease','linear','forwards','backwards',
                                          'both','infinite','paused','running',
                                          'normal','reverse','alternate',
                                          'alternate-reverse'}
                    else m.group(0),
                rule_body
            )

        # Determine if selector needs scoping
        SKIP = (':root', '*', 'html', 'body', '@',
                'from', 'to', '0%', '25%', '50%', '75%', '100%',
                '33%', '66%', '20%', '40%', '60%', '80%')

        parts = selector_text.split(',')
        scoped_parts = []
        for part in parts:
            p = part.strip()
            if not p:
                continue
            if any(p.startswith(s) for s in SKIP):
                scoped_parts.append(p)
            else:
                scoped_parts.append(f'{scope} {p}')

        scoped_selector = ',\n'.join(scoped_parts)
        output.append(f'\n{scoped_selector} {rule_body}\n')
        i = j

    return ''.join(output)


def wrap_iife(js, app_name, expose_fns=None, extra_expose=''):
    """Wrap JS in an IIFE and expose specific functions to window"""
    expose_lines = []
    if expose_fns:
        for fn in expose_fns:
            expose_lines.append(
                f'  try{{ window.{fn} = {fn}; }}catch(e){{}}'
            )
    expose = '\n'.join(expose_lines)
    return f"""
(function(){{
// ══ {app_name} APP ══
{js}
// ── expose to window ──
{expose}
{extra_expose}
}})();
"""


# ─── Read source files ───
dash_html = read('d_i75EXu4XuLRneN3r-BETA.html')
dl_html   = read('deadline-BETA.html')
pr_html   = read('practice-BETA.html')

# ─── Extract CSS ───
dash_css = '\n'.join(extract_css_blocks(dash_html))
dl_css   = '\n'.join(extract_css_blocks(dl_html))
pr_css   = '\n'.join(extract_css_blocks(pr_html))

# Scope CSS (with keyframe prefixes to avoid conflicts)
dash_css_scoped = scope_css(dash_css, '#panel-dashboard', 'dash-')
dl_css_scoped   = scope_css(dl_css,   '#panel-deadline',  'dl-')
pr_css_scoped   = scope_css(pr_css,   '#panel-practice',  'pr-')

# ─── Extract body HTML (strip ALL script tags to prevent double execution) ───
dash_body = strip_scripts(extract_body(dash_html))
dl_body   = strip_scripts(extract_body(dl_html))
pr_body   = strip_scripts(extract_body(pr_html))

# ─── Extract external scripts (deduplicated) ───
seen = set()
ext_scripts = []
for s in extract_external_scripts(dash_html) + extract_external_scripts(dl_html) + extract_external_scripts(pr_html):
    src = re.search(r'src=["\']([^"\']+)["\']', s)
    if src and src.group(1) not in seen:
        seen.add(src.group(1))
        ext_scripts.append(s)

# ─── Extract inline JS ───
dash_js = '\n'.join(extract_all_inline_js(dash_html))
dl_js   = '\n'.join(extract_all_inline_js(dl_html))
pr_js   = '\n'.join(extract_all_inline_js(pr_html))

# Fix calMove conflict: rename deadline's calMove to dlCalMove
dl_js   = re.sub(r'\bcalMove\b', 'dlCalMove', dl_js)
dl_body = re.sub(r'\bcalMove\b', 'dlCalMove', dl_body)

# Fix keyframe animation references in JS (Chart.js datasets etc. don't use CSS anims, safe to skip)
# Prefix animation names in JS strings that match keyframe names
def prefix_js_anims(js, prefix, names):
    """Replace known keyframe name strings in JS with prefixed versions."""
    for name in names:
        js = re.sub(rf"'({name})'", f"'{prefix}\\1'", js)
        js = re.sub(rf'"({name})"', f'"{prefix}\\1"', js)
    return js

dash_kf = ['fadeIn', 'slideUp', 'fadeUp', 'toastIn', 'toastOut', 'shake', 'reveal']
dl_kf   = ['fadeIn', 'fadeUp', 'toastIn', 'toastOut', 'shake', 'slideUp', 'reveal']
pr_kf   = ['fadeIn', 'reveal', 'diagSlide']

dash_js = prefix_js_anims(dash_js, 'dash-', dash_kf)
dl_js   = prefix_js_anims(dl_js,   'dl-',   dl_kf)
pr_js   = prefix_js_anims(pr_js,   'pr-',   pr_kf)

# ─── Expose lists ───
DASH_EXPOSE = [
    'openModal','closeModal','saveModal','deleteComm',
    'openGhModal','closeGhModal','saveGhSettings','testGhToken',
    'deployToGitHub','doLogin','setFilter','exportCSV',
    'openNoticeEdit','closeNoticeModal','saveNotice',
    'openParseModal','closeParseModal','confirmParse',
    'renderCards','scheduleSync','autoSyncData',
]
DASH_EXTRA = """
  window.studioApp = window.studioApp || {};
  window.studioApp.getDashboardStats = function(){
    try{
      var active = commissions.filter(function(c){ return c.stage < 7; }).length;
      var today2 = new Date(); today2.setHours(0,0,0,0);
      var week = commissions.filter(function(c){
        if(c.stage >= 7 || !c.deadline) return false;
        var d = new Date(c.deadline); d.setHours(0,0,0,0);
        var diff = Math.round((d-today2)/86400000);
        return diff >= 0 && diff <= 7;
      }).length;
      return { active: active, week: week };
    }catch(e){ return { active: 0, week: 0 }; }
  };
"""

DL_EXPOSE = [
    'addItem','toggleDone','deleteItem','showDeleteConfirm','hideDeleteConfirm',
    'dlCalMove','syncNow','saveSyncUrl','renderAll',
]
DL_EXTRA = """
  window.studioApp = window.studioApp || {};
  window.studioApp.syncDeadlines = function(){ try{ syncNow(); }catch(e){} };
"""

PR_EXPOSE = [
    'timerToggle','timerReset','enterFocus','exitFocus',
    'checkInToday','calMove','addTask','clearDoneTasks',
    'openWorklogModal','addWorklog','closeWorklogModal',
    'openWeakModal','closeWeakModal','saveWeak','deleteWeak',
    'addIdea','clearDoneIdeas','openIncomeModal','closeIncomeModal',
    'addIncome','deleteIncome','showChart',
    'togglePin','minWin','closeWin',
    # Daily quest functions
    'switchTaskTab','addDQ','toggleDQ','deleteDQ','renderDQ',
]
PR_EXTRA = """
  window.studioApp = window.studioApp || {};
  window.studioApp.getPracticeStats = function(){
    try{
      var stored = localStorage.getItem('mm_practice_checkins');
      var checkins = stored ? JSON.parse(stored) : [];
      if(!checkins.length) return { streak: 0 };
      checkins.sort();
      var streak = 0;
      var d = new Date(); d.setHours(0,0,0,0);
      for(var i=0; i<365; i++){
        var str = d.toISOString().slice(0,10);
        if(checkins.indexOf(str) === -1) break;
        streak++;
        d.setDate(d.getDate()-1);
      }
      return { streak: streak };
    }catch(e){ return { streak: 0 }; }
  };
"""

dash_js_wrapped = wrap_iife(dash_js, 'DASHBOARD', DASH_EXPOSE, DASH_EXTRA)
dl_js_wrapped   = wrap_iife(dl_js,   'DEADLINE',  DL_EXPOSE,   DL_EXTRA)
pr_js_wrapped   = wrap_iife(pr_js,   'PRACTICE',  PR_EXPOSE,   PR_EXTRA)

# ─── Shell CSS ───
SHELL_CSS = """
/* ══ STUDIO SHELL ══ */
*::-webkit-scrollbar{display:none}
*{scrollbar-width:none;-ms-overflow-style:none;box-sizing:border-box;margin:0;padding:0}
:root{
  --Y:#3D8EF0;--Y2:#1A6AD4;
  --display:'Bebas Neue',sans-serif;
  --cond:'Barlow Condensed',sans-serif;
  --mono:'DM Mono',monospace;
}
body{
  --bg:#1A1A22;--bg2:#1F1F28;--bg3:#25252F;
  --card:#22222C;--card2:#25252F;
  --border:rgba(255,255,255,.12);--border2:rgba(255,255,255,.24);
  --text:#F0EEE8;--text2:#B8B4AC;--text3:#7A7870;
  --red:#e05040;--green:#60c080;--orange:#f07030;
  background:var(--bg);color:var(--text);
  font-family:'Noto Sans KR',sans-serif;min-height:100vh;overflow-x:hidden;
}
body::before{
  content:'';position:fixed;inset:0;z-index:0;pointer-events:none;
  background:repeating-linear-gradient(-45deg,transparent,transparent 40px,
    rgba(61,142,240,.02) 40px,rgba(61,142,240,.02) 41px);
}
.studio-panel{position:relative;z-index:1;min-height:calc(100vh - 50px);}

/* Shell header */
#shell-header{
  position:sticky;top:0;z-index:500;
  background:rgba(34,34,44,.97);
  border-bottom:1px solid var(--border);
  backdrop-filter:blur(12px);
  padding:0 24px;
  display:flex;align-items:center;justify-content:space-between;
  height:50px;gap:16px;
}
.shell-logo{
  font-family:var(--display);font-size:18px;color:var(--Y);
  letter-spacing:1.5px;flex-shrink:0;
}
.tab-nav{display:flex;gap:2px;}
.tab-btn{
  padding:5px 16px;border-radius:8px;border:none;
  background:transparent;color:var(--text3);
  font-family:var(--cond);font-size:13px;font-weight:700;letter-spacing:.5px;
  cursor:pointer;transition:all .15s;white-space:nowrap;
}
.tab-btn:hover{color:var(--text2);background:rgba(255,255,255,.05);}
.tab-btn.active{background:rgba(61,142,240,.15);color:var(--Y);}
.shell-stats{
  display:flex;gap:16px;align-items:center;
  font-family:var(--mono);font-size:11px;color:var(--text3);
  flex-shrink:0;
}
.shell-stat b{color:var(--text2);}
@media(max-width:768px){
  .shell-stats{display:none;}
  .tab-btn{padding:5px 10px;font-size:12px;}
}
"""

SHELL_HEADER_HTML = """
<header id="shell-header">
  <div class="shell-logo">STUDIO</div>
  <nav class="tab-nav">
    <button class="tab-btn active" data-tab="dashboard">대시보드</button>
    <button class="tab-btn" data-tab="deadline">마감 캘린더</button>
    <button class="tab-btn" data-tab="practice">연습 트래커</button>
  </nav>
  <div class="shell-stats">
    <div class="shell-stat">진행 <b id="ss-active">-</b>건</div>
    <div class="shell-stat">이번주 마감 <b id="ss-week">-</b>건</div>
    <div class="shell-stat">스트릭 <b id="ss-streak">-</b>일 🔥</div>
  </div>
</header>
"""

SHELL_JS = """
(function(){
  var panels = { dashboard: null, deadline: null, practice: null };
  ['dashboard','deadline','practice'].forEach(function(id){
    panels[id] = document.getElementById('panel-'+id);
  });

  document.querySelectorAll('.tab-btn').forEach(function(btn){
    btn.addEventListener('click', function(){
      var tab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('active'); });
      btn.classList.add('active');
      Object.keys(panels).forEach(function(k){
        if(panels[k]) panels[k].style.display = (k === tab) ? 'block' : 'none';
      });
      if(tab === 'deadline' && window.studioApp && window.studioApp.syncDeadlines){
        window.studioApp.syncDeadlines();
      }
      updateShellStats();
    });
  });

  function updateShellStats(){
    try{
      var ds = window.studioApp && window.studioApp.getDashboardStats
        ? window.studioApp.getDashboardStats() : null;
      var ps = window.studioApp && window.studioApp.getPracticeStats
        ? window.studioApp.getPracticeStats() : null;
      if(ds){
        document.getElementById('ss-active').textContent = ds.active;
        document.getElementById('ss-week').textContent   = ds.week;
      }
      if(ps){
        document.getElementById('ss-streak').textContent = ps.streak;
      }
    }catch(e){}
  }
  window.updateShellStats = updateShellStats;
  setInterval(updateShellStats, 8000);
  window.addEventListener('load', function(){ setTimeout(updateShellStats, 800); });
})();
"""

# ─── Assemble ───
ext_script_tags = '\n'.join(ext_scripts)

output = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>모무꼬 스튜디오</title>
<meta name="theme-color" content="#1A1A22">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Barlow+Condensed:ital,wght@0,300;0,400;0,600;0,700;0,800;0,900;1,700&family=Noto+Sans+KR:wght@300;400;700;900&family=DM+Mono:wght@300;400;500&family=Cormorant+Garamond:ital,wght@1,300;1,400;1,600&family=Playfair+Display:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
{ext_script_tags}
<style>
{SHELL_CSS}
</style>
<style id="css-dashboard">
/* ══ DASHBOARD CSS ══ */
{dash_css_scoped}
</style>
<style id="css-deadline">
/* ══ DEADLINE CSS ══ */
{dl_css_scoped}
</style>
<style id="css-practice">
/* ══ PRACTICE CSS ══ */
{pr_css_scoped}
</style>
</head>
<body>
{SHELL_HEADER_HTML}

<div id="panel-dashboard" class="studio-panel">
{dash_body}
</div>

<div id="panel-deadline" class="studio-panel" style="display:none">
{dl_body}
</div>

<div id="panel-practice" class="studio-panel" style="display:none">
{pr_body}
</div>

<script>
{SHELL_JS}
</script>
<script>
{dash_js_wrapped}
</script>
<script>
{dl_js_wrapped}
</script>
<script>
{pr_js_wrapped}
</script>
</body>
</html>"""

out_path = os.path.join(BASE, 'studio-BETA.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(output)

size_kb = os.path.getsize(out_path) // 1024
print(f"Done! studio-BETA.html written ({size_kb} KB)")

# Quick verification
with open(out_path, encoding='utf-8') as f:
    content = f.read()

issues = []
# Check no raw <script> in panel divs
panels_html = re.search(r'<div id="panel-dashboard".*?(?=<script>)', content, re.DOTALL)
if panels_html and '<script' in panels_html.group(0):
    issues.append("WARNING: <script> tags found in panel HTML (double execution risk)")

# Check daily quest functions exposed
for fn in ['switchTaskTab','addDQ','toggleDQ','deleteDQ']:
    if f'window.{fn} = {fn}' not in content:
        issues.append(f"WARNING: {fn} not exposed to window")

# Check no duplicate keyframe names (dash- prefix should be there)
kf_names = re.findall(r'@keyframes\s+(\S+)', content)
dupes = [n for n in set(kf_names) if kf_names.count(n) > 1]
if dupes:
    issues.append(f"WARNING: duplicate @keyframes: {dupes}")

if issues:
    print("Issues found:")
    for i in issues: print(" ", i)
else:
    print("Verification passed: no obvious issues detected")
