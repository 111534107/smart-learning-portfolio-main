import re, sys, os, urllib.parse
root = sys.argv[1]
pat = re.compile(r'\]\(([^)\s]+)\)')
bad = []
for dp, dn, fn in os.walk(root):
    if '.git' in dp or 'superpowers' in dp: continue
    for f in fn:
        if not f.endswith('.md'): continue
        p = os.path.join(dp, f)
        for m in pat.finditer(open(p, encoding='utf-8', errors='ignore').read()):
            t = urllib.parse.unquote(m.group(1).split('#')[0])
            if not t or '://' in t or t.startswith('mailto:'): continue
            if not os.path.exists(os.path.normpath(os.path.join(dp, t))):
                bad.append(f"{os.path.relpath(p, root)} -> {t}")
print(len(bad))
print("\n".join(bad))
