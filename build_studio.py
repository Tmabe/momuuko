#!/usr/bin/env python3
"""
Merges dashboard, deadline, and practice apps into studio-BETA.html
"""
import re, os

BASE = os.path.dirname(os.path.abspath(__file__))

def read(name):
    with open(os.path.join(BASE, name), encoding='utf-8') as f:
        return f.read()

def extract_between(html, start_tag, end_tag):
    start = html.find(start_tag)
    end = html.find(end_tag, start)
    if start == -1 or end == -1:
        return ''
    return html[start + len(start_tag):end]

def extract_body(html):
    """Extract everything between <body> and </body>"""
    m = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    return m.group(1).strip() if m else ''

def extract_css_blocks(html):
    """Extract all inline <style> block contents"""
    return re.findall(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)

def extract_external_scripts(html):
    """Extract <script src="..."> tags"""
    return re.findall(r'<script\s+src=["\'][^"\']+["\'][^>]*></script>', html)

def extract_inline_scripts(html):
    """Extract inline <script> blocks (no src attribute)"""
    blocks = re.findall(r'<script(?!\s+src)[^>]*>(.*?)</script>', html, re.DOTALL)
    return [b for b in blocks if b.strip()]

def scope_css(css, scope):
    """
    Prefix CSS rules with a scope selector.
    Skips @keyframes, @import, :root, *, html, body selectors.
    """
    result = []
    # Split by } to process rule by rule is complex; use a simpler token approach
    lines = css.split('\n')
    output_lines = []
    in_keyframes = False
    in_media = False
    brace_depth = 0
    current_rule = []

    def flush_rule(rule_lines):
        text = '\n'.join(rule_lines).strip()
        if not text:
            return ''
        # Get selector part (before first {)
        brace_pos = text.find('{')
        if brace_pos == -1:
            return text
        selector = text[:brace_pos].strip()
        body_part = text[brace_pos:]

        # Don't scope these
        skip_prefixes = (':root', '*', 'html', 'body', '@', 'from', 'to', '0%', '25%', '50%', '75%', '100%')
        selector_stripped = selector.strip()
        if any(selector_stripped.startswith(p) for p in skip_prefixes):
            return text
        if not selector_stripped:
            return text

        # Scope each comma-separated selector
        parts = selector_stripped.split(',')
        scoped_parts = []
        for part in parts:
            p = part.strip()
            if not p:
                continue
            if any(p.startswith(s) for s in skip_prefixes):
                scoped_parts.append(p)
            else:
                scoped_parts.append(f'{scope} {p}')

        return ', '.join(scoped_parts) + body_part

    # Simple line-by-line approach with brace counting
    full_text = css

    # Process with regex: find all rule blocks and prefix selectors
    # More reliable: split on top-level { } blocks
    output = []
    i = 0
    while i < len(full_text):
        # Check for @keyframes or @media
        kf_match = re.match(r'\s*(@(?:keyframes|-webkit-keyframes|-moz-keyframes)\s+\S+)\s*\{', full_text[i:], re.DOTALL)
        media_match = re.match(r'\s*(@(?:media|supports)[^{]+)\{', full_text[i:], re.DOTALL)

        if kf_match:
            # Find matching closing brace (nested)
            start = i + kf_match.start()
            end_i = i + kf_match.end() - 1  # position of opening {
            depth = 1
            j = end_i + 1
            while j < len(full_text) and depth > 0:
                if full_text[j] == '{': depth += 1
                elif full_text[j] == '}': depth -= 1
                j += 1
            output.append(full_text[i:j])
            i = j
            continue

        if media_match:
            # Find the opening brace position
            pre = full_text[i:i + media_match.end()]
            brace_pos_in_pre = pre.rfind('{')
            actual_start = i
            actual_brace = i + brace_pos_in_pre
            media_selector = pre[:brace_pos_in_pre].strip()

            # Find the matching closing brace
            depth = 1
            j = actual_brace + 1
            while j < len(full_text) and depth > 0:
                if full_text[j] == '{': depth += 1
                elif full_text[j] == '}': depth -= 1
                j += 1

            # Get the inner content and scope it
            inner = full_text[actual_brace+1:j-1]
            scoped_inner = scope_css(inner, scope)
            output.append(f'{media_selector} {{\n{scoped_inner}\n}}')
            i = j
            continue

        # Find next {
        brace = full_text.find('{', i)
        if brace == -1:
            output.append(full_text[i:])
            break

        # Get selector
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

        rule_body = full_text[brace:j]  # includes braces

        # Skip empty selectors
        if not selector_text:
            output.append(rule_body)
            i = j
            continue

        skip_prefixes = (':root', '*', 'html', 'body', '@', 'from', 'to',
                         '0%', '25%', '50%', '75%', '100%', '33%', '66%')

        # Scope selector parts
        parts = selector_text.split(',')
        scoped_parts = []
        for part in parts:
            p = part.strip()
            if not p:
                continue
            if any(p.startswith(s) for s in skip_prefixes):
                scoped_parts.append(p)
            else:
                scoped_parts.append(f'{scope} {p}')

        scoped_selector = ',\n'.join(scoped_parts)
        output.append(f'\n{scoped_selector} {rule_body}\n')
        i = j

    return ''.join(output)


def wrap_iife(js, app_name, expose_fns=None, extra_expose=''):
    """Wrap JS in an IIFE and expose specific functions to window"""
    expose = ''
    if expose_fns:
        expose = '\n'.join([f'  window.{fn} = typeof {fn} !== "undefined" ? {fn} : window.{fn};'
                           for fn in expose_fns])
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

# Remove the shared base rules from each (they'll be in shared CSS)
# Scope each
dash_css_scoped = scope_css(dash_css, '#panel-dashboard')
dl_css_scoped   = scope_css(dl_css,   '#panel-deadline')
pr_css_scoped   = scope_css(pr_css,   '#panel-practice')

# ─── Extract body HTML ───
dash_body = extract_body(dash_html)
dl_body   = extract_body(dl_html)
pr_body   = extract_body(pr_html)

# ─── Extract external scripts ───
dash_ext = extract_external_scripts(dash_html)
dl_ext   = extract_external_scripts(dl_html)
pr_ext   = extract_external_scripts(pr_html)

# Deduplicate external scripts
seen = set()
ext_scripts = []
for s in dash_ext + dl_ext + pr_ext:
    src = re.search(r'src=["\']([^"\']+)["\']', s)
    if src and src.group(1) not in seen:
        seen.add(src.group(1))
        ext_scripts.append(s)

# ─── Extract inline JS ───
dash_js_blocks = extract_inline_scripts(dash_html)
dl_js_blocks   = extract_inline_scripts(dl_html)
pr_js_blocks   = extract_inline_scripts(pr_html)

dash_js = '\n'.join(dash_js_blocks)
dl_js   = '\n'.join(dl_js_blocks)
pr_js   = '\n'.join(pr_js_blocks)

# Fix calMove conflict: rename deadline's calMove to dlCalMove
dl_js   = re.sub(r'\bcalMove\b', 'dlCalMove', dl_js)
dl_body = re.sub(r'\bcalMove\b', 'dlCalMove', dl_body)

# Dashboard expose list (functions called from HTML onclick)
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

# Deadline expose list
DL_EXPOSE = [
    'addItem','toggleDone','deleteItem','showDeleteConfirm','hideDeleteConfirm',
    'dlCalMove','syncNow','saveSyncUrl',
]
DL_EXTRA = """
  window.studioApp = window.studioApp || {};
  window.studioApp.syncDeadlines = function(){ if(typeof syncNow === 'function') syncNow(); };
  window.studioApp.getDeadlineStats = function(){
    try{
      var data = JSON.parse(localStorage.getItem('momuuko_deadlines')||'[]');
      var today2 = new Date(); today2.setHours(0,0,0,0);
      var active = data.filter(function(x){ return !x.done; }).length;
      return { active: active };
    }catch(e){ return { active: 0 }; }
  };
"""

# Practice expose list (functions called from HTML onclick)
PR_EXPOSE = [
    'timerToggle','timerReset','enterFocus','exitFocus',
    'checkInToday','calMove','addTask','clearDoneTasks',
    'openWorklogModal','addWorklog','closeWorklogModal',
    'openWeakModal','closeWeakModal','saveWeak','deleteWeak',
    'addIdea','clearDoneIdeas','openIncomeModal','closeIncomeModal',
    'addIncome','deleteIncome','showChart',
    'togglePin','minWin','closeWin',
]
PR_EXTRA = """
  window.studioApp = window.studioApp || {};
  window.studioApp.getPracticeStats = function(){
    try{
      var checkins = JSON.parse(localStorage.getItem('mm_practice_checkins')||'[]');
      if(!checkins.length) return { streak: 0 };
      checkins.sort();
      var streak = 0;
      var d = new Date(); d.setHours(0,0,0,0);
      while(true){
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
.studio-panel{position:relative;z-index:1;}

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

# ─── Shell HTML header ───
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

# ─── Shell JS ───
SHELL_JS = """
// Tab switching
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

# ─── Assemble final HTML ───
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
