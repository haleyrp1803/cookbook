#!/usr/bin/env python3
"""Build generated/recipes.js from editable Markdown files in recipes/."""
from __future__ import annotations
import argparse, html, json, re, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RECIPES=ROOT/'recipes'
OUTPUT=ROOT/'generated'/'recipes.js'


def unquote(value: str) -> str:
    value=value.strip()
    if not value: return ''
    if value[0] in {'"', "'"}:
        try: return str(json.loads(value))
        except Exception: return value.strip('"\'')
    return value


def parse_file(path: Path):
    text=path.read_text(encoding='utf-8-sig')
    if not text.startswith('---\n'):
        raise ValueError('missing opening YAML frontmatter delimiter')
    try:
        front, body=text[4:].split('\n---\n',1)
    except ValueError:
        raise ValueError('missing closing YAML frontmatter delimiter')
    meta={}; current_list=None
    for raw in front.splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'): continue
        if raw.startswith('  - ') and current_list:
            meta[current_list].append(unquote(raw[4:]))
            continue
        if ':' not in raw: raise ValueError(f'invalid metadata line: {raw}')
        key,value=raw.split(':',1); key=key.strip(); value=value.strip()
        if value=='': meta[key]=[]; current_list=key
        else: meta[key]=unquote(value); current_list=None
    return meta,body


def inline(text: str) -> str:
    text=html.escape(text,quote=False)
    text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2" target="_blank" rel="noopener">\1</a>',text)
    text=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)',r'<em>\1</em>',text)
    return text


def markdown_to_html(md: str) -> str:
    out=[]; para=[]; list_type=None
    def flush_para():
        nonlocal para
        if para:
            out.append('<p>'+inline(' '.join(x.strip() for x in para))+'</p>'); para=[]
    def close_list():
        nonlocal list_type
        if list_type: out.append(f'</{list_type}>'); list_type=None
    for raw in md.splitlines():
        s=raw.strip()
        if not s: flush_para(); close_list(); continue
        if s.startswith('### '): flush_para(); close_list(); out.append('<h3>'+inline(s[4:])+'</h3>'); continue
        if s.startswith('## '): flush_para(); close_list(); out.append('<h2>'+inline(s[3:])+'</h2>'); continue
        m=re.match(r'^[-*]\s+(.+)$',s)
        if m:
            flush_para()
            if list_type!='ul': close_list(); out.append('<ul>'); list_type='ul'
            out.append('<li>'+inline(m.group(1))+'</li>'); continue
        m=re.match(r'^\d+\.\s+(.+)$',s)
        if m:
            flush_para()
            if list_type!='ol': close_list(); out.append('<ol>'); list_type='ol'
            out.append('<li>'+inline(m.group(1))+'</li>'); continue
        para.append(s)
    flush_para(); close_list()
    return '\n'.join(out)


def main():
    parser=argparse.ArgumentParser(description='Build the cookbook recipe bundle.')
    parser.add_argument('--check',action='store_true',help='Validate without writing output.')
    args=parser.parse_args()
    errors=[]; recipes=[]; titles=set()
    for path in sorted(RECIPES.glob('*.md')):
        try:
            meta,body=parse_file(path)
            title=meta.get('title','').strip(); category=meta.get('category','').strip()
            if not title: errors.append(f'{path.name}: missing title')
            if not category: errors.append(f'{path.name}: missing category')
            if title.casefold() in titles: print(f'Warning: duplicate title retained: {title} ({path.name})')
            titles.add(title.casefold())
            tags=meta.get('tags',[])
            if isinstance(tags,str): tags=[x.strip() for x in tags.split(';') if x.strip()]
            image=meta.get('image','')
            if image and not (ROOT/image).exists(): errors.append(f'{path.name}: missing image: {image}')
            rendered=markdown_to_html(body)
            plain=re.sub(r'<[^>]+>',' ',rendered)
            recipes.append({
                'title':title,'category':category,'tags':tags,'source':meta.get('source',''),
                'servings':meta.get('servings',''),'prep_time':meta.get('prep_time',''),
                'cook_time':meta.get('cook_time',''),'total_time':meta.get('total_time',''),
                'rating':meta.get('rating',''),'image':image,'html':rendered,
                'search':' '.join([title,category,' '.join(tags),plain]).lower()
            })
        except Exception as exc: errors.append(f'{path.name}: {exc}')
    recipes.sort(key=lambda r:(r['category'].casefold(),r['title'].casefold()))
    for i,r in enumerate(recipes,1): r['id']=i
    if errors:
        print('Build failed:',file=sys.stderr)
        for e in errors: print(' - '+e,file=sys.stderr)
        return 1
    print(f'Validated {len(recipes)} recipes.')
    if not args.check:
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text('window.RECIPE_DATA = '+json.dumps(recipes,ensure_ascii=False)+';\n',encoding='utf-8')
        print(f'Wrote {OUTPUT.relative_to(ROOT)}')
    return 0

if __name__=='__main__': raise SystemExit(main())
